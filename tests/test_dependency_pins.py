"""Khóa các phiên bản được khai báo ở nhiều file (C-37, chuẩn bị cho Dependabot).

Giá trị đọc từ chính các file, không hardcode: nâng đồng thời ở mọi nơi thì test vẫn xanh,
chỉ đổi lệch một nơi mới đỏ. Bản đồ và các trường hợp phải đổi nhiều file: docs/dependency-pins.md.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REQ_FILES = [
    "requirements.txt",
    "streamlit/requirements.txt",
    "models/requirements-ml.txt",
    "scripts/requirements-data.txt",
    "locust/requirements.txt",
]
_PIN = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([^\s;#]+)", re.MULTILINE
)


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _name(raw: str) -> str:
    return re.sub(r"[-_.]+", "-", raw).lower()


def pins(rel: str) -> dict[str, str]:
    return {_name(n): v for n, v in _PIN.findall(_text(rel))}


def _all_pins() -> dict[str, dict[str, str]]:
    return {rel: pins(rel) for rel in REQ_FILES}


def test_doc_duoc_cac_ghim_khong_rong():
    # Chặn test rỗng vì regex hỏng: các gói trụ cột phải được thấy.
    allp = _all_pins()
    assert {"numpy", "scikit-learn", "pillow", "ruff"} <= set(allp["requirements.txt"])
    assert {"torch", "transformers"} <= set(allp["models/requirements-ml.txt"])
    assert "streamlit" in allp["streamlit/requirements.txt"]


def test_goi_xuat_hien_o_nhieu_file_requirements_phai_cung_phien_ban():
    seen: dict[str, dict[str, str]] = {}
    for rel, p in _all_pins().items():
        for name, ver in p.items():
            seen.setdefault(name, {})[rel] = ver
    shared = {n: m for n, m in seen.items() if len(m) > 1}
    assert shared, "không có gói dùng chung: kiểm lại danh sách file"
    bad = {n: m for n, m in shared.items() if len(set(m.values())) > 1}
    assert not bad, f"gói lệch phiên bản giữa các file requirements: {bad}"


def _ruff_versions() -> dict[str, str]:
    out = {"requirements.txt": pins("requirements.txt").get("ruff", "")}
    ci = re.findall(r"ruff==([\w.]+)", _text(".github/workflows/ci.yml"))
    assert ci, "ci.yml không còn dòng cài ruff==..."
    assert len(set(ci)) == 1, f"ci.yml có nhiều phiên bản ruff: {ci}"
    out["ci.yml"] = ci[0]
    rev = re.search(
        r"ruff-pre-commit\s*\n\s*rev:\s*v?([\w.]+)", _text(".pre-commit-config.yaml")
    )
    assert rev, ".pre-commit-config.yaml không còn hook ruff-pre-commit"
    out[".pre-commit-config.yaml"] = rev.group(1)
    return out


def test_ruff_cung_phien_ban_o_ba_noi():
    v = _ruff_versions()
    assert all(v.values()), f"thiếu phiên bản ruff: {v}"
    assert len(set(v.values())) == 1, (
        f"ruff lệch giữa requirements.txt, ci.yml, pre-commit: {v}"
    )


def _base_python(rel: str) -> str:
    m = re.search(r"^FROM\s+python:([\d.]+)-slim\b", _text(rel), re.MULTILINE)
    assert m, f"{rel}: không thấy FROM python:<phiên bản>-slim"
    return m.group(1)


def test_hai_dockerfile_cung_phien_ban_python():
    # Dockerfile gốc đã được test_docker_static khóa với ci.yml; ở đây khóa thêm UI.
    assert _base_python("streamlit/Dockerfile") == _base_python("Dockerfile")


def test_ghim_torch_dockerfile_va_requirements_ml_khop():
    # Trùng một phần test_docker_static; giữ để bản đồ đủ khi file kia đổi.
    docker = re.findall(r"torch==([\d.]+)", _text("Dockerfile"))
    assert docker and set(docker) == {pins("models/requirements-ml.txt")["torch"]}


def test_clip_revision_la_sha_day_du_o_mot_noi():
    m = re.search(
        r'^CLIP_REVISION\s*=\s*"([0-9a-f]{40})"',
        _text("models/clip_input.py"),
        re.MULTILINE,
    )
    assert m, "CLIP_REVISION phải là SHA commit 40 ký tự trong models/clip_input.py"


@pytest.mark.parametrize("rel", REQ_FILES)
def test_moi_dong_goi_deu_ghim_chinh_xac(rel):
    # Dependabot cần ghim == để đọc được phiên bản; dòng không ghim làm bản đồ trên hụt.
    for line in _text(rel).splitlines():
        s = line.split("#")[0].strip()
        if s and not s.startswith(("-", "--")):
            assert "==" in s, f"{rel}: gói không ghim ==: {s!r}"
