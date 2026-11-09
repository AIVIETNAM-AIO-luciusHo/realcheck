"""Kiểm TĨNH Dockerfile và .dockerignore (PR #38); không chạy docker, chỉ thư viện chuẩn.

Giới hạn: chỉ kiểm Dockerfile MỘT stage. Nhiều hơn một FROM thì test đỏ có chủ ý (fail-safe,
không phân tích nửa vời USER/COPY --from của từng stage); đổi sang multi-stage phải cập nhật
file này. Danh sách COPY cho phép cũng cố ý chặt: thêm COPY mới phải sửa test.
Chưa kiểm: build thật, user đọc được file mount, healthcheck với model thật (ticket B3).
"""

import ast
import fnmatch
import json
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# app/README.md: nạp + warmup CLIP khoảng 30 giây, healthcheck chờ >= 1 phút
MIN_WARMUP_S = 60
MIN_INTERVAL_S = 10


def _logical_lines(path: Path) -> list[str]:
    """Nối dòng tiếp nối bằng dấu gạch chéo ngược, bỏ chú thích và dòng trống."""
    text = re.sub(r"\\\s*\n", " ", path.read_text(encoding="utf-8"))
    lines = [re.sub(r"\s+", " ", line.strip()) for line in text.splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


@pytest.fixture(scope="module")
def dockerfile() -> list[str]:
    lines = _logical_lines(ROOT / "Dockerfile")
    assert len(_of(lines, "FROM")) == 1, (
        "Dockerfile nhiều stage: test này chỉ kiểm Dockerfile một stage, "
        "hãy cập nhật tests/test_docker_static.py"
    )
    return lines


@pytest.fixture(scope="module")
def ignored() -> list[str]:
    return _logical_lines(ROOT / ".dockerignore")


def _of(lines: list[str], instruction: str) -> list[str]:
    prefix = instruction + " "
    return [line[len(prefix) :] for line in lines if line.upper().startswith(prefix)]


def _env(lines: list[str]) -> dict[str, str]:
    pairs = {}
    for item in _of(lines, "ENV"):
        for token in shlex.split(item):
            key, sep, value = token.partition("=")
            if sep:
                pairs[key] = value
    return pairs


def _index(lines: list[str], instruction: str) -> int:
    for i, line in enumerate(lines):
        if line.upper().startswith(instruction + " "):
            return i
    raise AssertionError(f"Dockerfile thiếu lệnh {instruction}")


def _duration_s(text: str) -> float:
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h)", text)
    assert match, f"không hiểu thời lượng {text!r}"
    return float(match[1]) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[match[2]]


def _expand_args(lines: list[str], text: str) -> str:
    """Thay ${ARG} hoặc $ARG bằng giá trị mặc định của ARG (nháy được bỏ)."""
    args = {}
    for item in _of(lines, "ARG"):
        key, sep, value = item.partition("=")
        if sep:
            args[key] = value.strip("\"'")
    return re.sub(r"\$\{?(\w+)\}?", lambda m: args.get(m[1], m[0]), text)


def _final_image(lines: list[str]) -> str:
    froms = _of(lines, "FROM")
    assert froms, "Dockerfile thiếu FROM"
    image = next(t for t in froms[0].split() if not t.startswith("--"))
    return _expand_args(lines, image)


def test_base_image_khop_phien_ban_python_cua_ci(dockerfile):
    ci_versions = set(
        re.findall(
            r'python-version:\s*"?([\d.]+)"?',
            (ROOT / ".github/workflows/ci.yml").read_text(),
        )
    )
    assert len(ci_versions) == 1, (
        f"ci.yml cần đúng một phiên bản Python, thấy {ci_versions}"
    )
    assert _final_image(dockerfile) == f"python:{ci_versions.pop()}-slim", (
        "base image phải là python:<phiên bản trong ci.yml>-slim"
    )


def test_user_khong_phai_root_va_dat_truoc_cmd(dockerfile):
    users = [_expand_args(dockerfile, u) for u in _of(dockerfile, "USER")]
    assert users and users[-1].split(":")[0] not in {"root", "0"}, (
        f"USER cuối cùng không được là root: {users}"
    )
    assert _index(dockerfile, "USER") < _index(dockerfile, "CMD"), (
        "USER phải đặt trước CMD"
    )
    for run in _of(dockerfile, "RUN"):
        uid = re.search(r"useradd\b.*?(?:--uid[ =]|-u )(\d+)", run)
        assert not uid or uid[1] != "0", f"useradd tạo user uid 0 (root): {run}"


def test_healthcheck_goi_health_va_start_period_du_warmup(dockerfile):
    checks = _of(dockerfile, "HEALTHCHECK")
    assert len(checks) == 1, "cần đúng một HEALTHCHECK"
    check = re.sub(r"\s#.*", "", checks[0])  # bỏ chú thích cuối dòng
    assert re.search(r"/health(?![\w/.-])", check), (
        f"HEALTHCHECK phải gọi đúng đường dẫn /health (không phải /healthz): {check}"
    )
    start = re.search(r"--start-period[ =](\S+)", check)
    assert start, "HEALTHCHECK thiếu --start-period"
    assert _duration_s(start[1]) >= MIN_WARMUP_S, (
        f"start-period {start[1]} ngắn hơn warmup {MIN_WARMUP_S}s ghi trong app/README.md"
    )
    interval = re.search(r"--interval[ =](\S+)", check)
    assert interval and _duration_s(interval[1]) >= MIN_INTERVAL_S, (
        f"--interval phải >= {MIN_INTERVAL_S}s để không dồn tải /health: {check}"
    )


def test_expose_khop_cong_cua_uvicorn(dockerfile):
    cmds = _of(dockerfile, "CMD")
    assert len(cmds) == 1, "cần đúng một CMD"
    try:
        tokens = json.loads(cmds[0])
    except ValueError:
        tokens = shlex.split(cmds[0])  # dạng shell
    joined = " ".join(tokens)
    assert "uvicorn" in tokens and "app.main:app" in tokens, (
        f"CMD phải chạy uvicorn: {joined}"
    )
    port = re.search(r"--port[ =](\d+)", joined)
    assert port, f"CMD thiếu --port: {joined}"
    exposed = _of(dockerfile, "EXPOSE")
    assert [e.split("/")[0] for e in exposed] == [port[1]] == ["8000"], (
        f"EXPOSE {exposed} lệch --port {port[1]}"
    )


def test_bien_moi_truong_model_va_cache_offline(dockerfile):
    env = _env(dockerfile)
    assert env.get("REALCHECK_MODEL_PATH") == "/models/clip_probe.joblib"
    assert env.get("HF_HOME") == "/hf-cache"
    assert env.get("HF_HUB_OFFLINE") == "1", (
        "HF_HUB_OFFLINE phải bằng 1 để không tải lúc chạy"
    )
    assert env.get("PIP_NO_CACHE_DIR") == "1", "PIP_NO_CACHE_DIR=1 giữ image nhỏ"


def test_torch_ghim_dung_phien_ban_va_dung_index_cpu(dockerfile):
    pinned = re.findall(
        r"^torch==(\S+)$",
        (ROOT / "models/requirements-ml.txt").read_text(),
        re.MULTILINE,
    )
    assert len(pinned) == 1, (
        f"requirements-ml.txt cần đúng một dòng torch==, thấy {pinned}"
    )
    runs = _of(dockerfile, "RUN")
    torch_runs = [i for i, r in enumerate(runs) if "torch==" in r]
    assert len(torch_runs) == 1, f"cần đúng một RUN cài torch, thấy {len(torch_runs)}"
    run = runs[torch_runs[0]]
    versions = re.findall(r"torch==([^\s]+)", run)
    assert [v.split("+")[0] for v in versions] == pinned, (
        f"torch trong Dockerfile {versions} lệch requirements-ml.txt ({pinned[0]})"
    )
    assert re.search(
        r"--(extra-)?index-url[ =]https://download\.pytorch\.org/whl/cpu\b", run
    ), "torch phải lấy từ index CPU"
    ml_runs = [i for i, r in enumerate(runs) if "requirements-ml.txt" in r]
    assert ml_runs, "không RUN nào cài requirements-ml.txt"
    assert torch_runs[0] < ml_runs[0] or (
        torch_runs[0] == ml_runs[0]
        and run.index("torch==") < run.index("requirements-ml.txt")
    ), "torch phải cài trước requirements-ml.txt, nếu không pip kéo bản CUDA"


def _copy_sources(dockerfile) -> list[str]:
    sources = []
    for item in _of(dockerfile, "COPY") + _of(dockerfile, "ADD"):
        parts = [t for t in item.split() if not t.startswith("--")]
        sources += [src.removeprefix("./") for src in parts[:-1]]
    return sources


def test_copy_chi_gom_app_models_py_va_requirements(dockerfile):
    allowed = {"requirements.txt", "models/requirements-ml.txt", "app/", "models/*.py"}
    sources = {
        s.rstrip("/") + "/" if s.rstrip("/") == "app" else s
        for s in _copy_sources(dockerfile)
    }
    assert sources == allowed, (
        f"COPY lệch: thừa {sources - allowed}, thiếu {allowed - sources}"
    )


@pytest.mark.parametrize(
    "banned", ["data", ".cache", ".env", "tests", "*.joblib", "scripts", ".git"]
)
def test_copy_khong_dua_du_lieu_model_hay_bi_mat_vao_image(dockerfile, banned):
    for source in _copy_sources(dockerfile):
        parts = Path(source).parts
        assert banned not in parts and not fnmatch.fnmatch(Path(source).name, banned), (
            f"COPY {source} đưa {banned} vào image"
        )
        assert source not in {".", "./"}, "COPY . kéo cả repo vào image"


def _ignore_forms(entry: str) -> set[str]:
    """Các cách viết tương đương của một mẫu .dockerignore: /x, x/, **/x."""
    entry = entry.strip("/")
    return {entry, entry.removeprefix("**/")}


def test_dockerignore_chan_du_lieu_cache_bi_mat_model_va_git(ignored):
    patterns = set().union(*(_ignore_forms(e) for e in ignored))
    for required in ["data", ".cache", ".env", ".git"]:
        assert required in patterns, f".dockerignore thiếu {required!r}"
    assert patterns & {"models/*.joblib", "*.joblib"} or "models/**" in ignored, (
        ".dockerignore thiếu models/*.joblib"
    )


def test_dockerignore_khong_phu_dinh_mau_bat_buoc(ignored):
    required = ["data", ".cache", ".env", ".git", "models"]
    for entry in (e[1:] for e in ignored if e.startswith("!")):
        forms = _ignore_forms(entry)
        hit = [
            f
            for f in forms
            if ".joblib" in f or any(f == r or f.startswith(r + "/") for r in required)
        ]
        assert not hit, (
            f".dockerignore phủ định mẫu bắt buộc, kéo lại vào image: !{entry}"
        )


def _local_imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
            names |= {f"{node.module}.{a.name}" for a in node.names}
    return {
        n
        for n in names
        if (ROOT / (n.replace(".", "/") + ".py")).is_file() and n.startswith("models.")
    }


def test_moi_module_models_ma_score_can_nam_trong_mau_copy(dockerfile):
    assert "models/*.py" in _copy_sources(dockerfile)
    needed, todo = set(), ["models.score"]
    while todo:
        name = todo.pop()
        if name not in needed:
            needed.add(name)
            todo += _local_imports(ROOT / (name.replace(".", "/") + ".py"))
    assert {"models.score", "models.clip_input", "models.normalize"} <= needed, (
        f"phân tích import hỏng, chỉ thấy {sorted(needed)}"
    )
    for name in sorted(needed):
        path = name.replace(".", "/") + ".py"
        assert fnmatch.fnmatch(path, "models/*.py"), (
            f"{path} không khớp mẫu COPY models/*.py"
        )
