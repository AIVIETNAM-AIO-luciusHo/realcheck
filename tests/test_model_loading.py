"""Test nạp model lúc khởi động (PR #37; AC-19..AC-22; D11, D12).

Không torch, không model thật, không mạng: `models.score` được thay bằng module giả
trong sys.modules, hoặc loader/scorer giả được tiêm vào create_app. Test phụ thuộc
tên không công khai: logger "realcheck", sự kiện log "model_loaded"/"model_load_failed",
tiền tố thread "inference". Mỗi test tự dọn trạng thái (monkeypatch, subprocess).
"""

import importlib
import io
import json
import logging
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from app.inference import load_model_scorer
from app.main import create_app
from app.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
SUBPROCESS_TIMEOUT_S = 60


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("REALCHECK_"):
            monkeypatch.delenv(key)


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _post(client):
    return client.post("/v1/analyze", files={"file": ("a.png", _png(), "image/png")})


def _events(caplog) -> dict[str, dict]:
    """Các log JSON của app, theo tên sự kiện."""
    out = {}
    for record in caplog.records:
        try:
            data = json.loads(record.getMessage())
        except ValueError:
            continue
        if isinstance(data, dict) and "event" in data:
            out[data["event"]] = data
    return out


def _run_py(code: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("REALCHECK_")}
    env.update(env_extra or {})
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys; sys.path.insert(0, {str(ROOT)!r})\n{code}",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT_S,
        cwd=ROOT,
        env=env,
    )


# ---- 1. load_model_scorer -> models.score.load_scorer ----


@pytest.fixture
def fake_score(monkeypatch):
    module = types.ModuleType("models.score")
    module.DEFAULT_MODEL_PATH = Path("/default/clip_probe.joblib")
    module.calls = []

    def load_scorer(*args, **kwargs):
        module.calls.append((args, kwargs))
        return lambda image: 0.5

    module.load_scorer = load_scorer
    monkeypatch.setitem(sys.modules, "models.score", module)
    return module


def test_load_model_scorer_dung_model_path_khi_dat(fake_score):
    scorer = load_model_scorer(Settings(model_path="/custom/m.joblib"))
    assert len(fake_score.calls) == 1, "load_scorer phải được gọi đúng một lần"
    args, kwargs = fake_score.calls[0]
    assert args == (Path("/custom/m.joblib"),) and kwargs == {}, (
        f"load_scorer nhận {args} {kwargs}, cần đúng một đối số vị trí là model_path"
    )
    assert isinstance(args[0], Path)
    assert scorer(None) == 0.5, "phải trả đúng scorer mà load_scorer trả về"


def test_load_model_scorer_voi_models_score_that_bao_thieu_file(tmp_path):
    """Không dùng module giả: bắt đổi tên load_scorer/DEFAULT_MODEL_PATH ở models/score.py."""
    real = importlib.import_module("models.score")
    assert callable(real.load_scorer) and isinstance(real.DEFAULT_MODEL_PATH, Path)
    with pytest.raises(FileNotFoundError):
        load_model_scorer(Settings(model_path=tmp_path / "khong_ton_tai.joblib"))


def test_load_model_scorer_dung_default_khi_model_path_none(fake_score):
    load_model_scorer(Settings())
    assert len(fake_score.calls) == 1
    args, kwargs = fake_score.calls[0]
    assert args == (fake_score.DEFAULT_MODEL_PATH,) and kwargs == {}, (
        f"model_path None phải dùng DEFAULT_MODEL_PATH, nhận {args} {kwargs}"
    )
    assert isinstance(args[0], Path)


# ---- 2. Settings.model_path ----


def test_settings_model_path_mac_dinh_none():
    assert Settings().model_path is None


def test_settings_doc_realcheck_model_path_tu_env(monkeypatch):
    monkeypatch.setenv("REALCHECK_MODEL_PATH", "/models/x.joblib")
    path = Settings().model_path
    assert path == Path("/models/x.joblib") and isinstance(path, Path), (
        f"REALCHECK_MODEL_PATH không được đọc, nhận {path!r}"
    )


def test_settings_model_path_bat_bien():
    with pytest.raises(ValidationError):
        Settings().model_path = Path("/x")


# ---- 3. Nhánh thành công ----


def test_nap_thanh_cong_tren_worker_thread_va_dung_scorer_do(caplog):
    seen = []

    def scorer(image):
        seen.append(image.size)
        return 0.9

    def loader():
        seen.append(threading.current_thread())
        return scorer

    with (
        caplog.at_level(logging.INFO, logger="realcheck"),
        TestClient(create_app(loader=loader)) as client,
    ):
        health = client.get("/health")
        response = _post(client)

    thread = seen[0]
    assert (
        thread.name.startswith("inference") and thread is not threading.main_thread()
    ), f"loader phải chạy trên worker thread, chạy trên {thread.name}"
    assert health.status_code == 200
    assert response.status_code == 200 and response.json()["score"] == 0.9, (
        f"/v1/analyze không dùng scorer do loader trả về: {response.text}"
    )
    assert seen[1] == (300, 300), "scorer nhận ảnh gốc đã giải mã"
    event = _events(caplog).get("model_loaded")
    assert event is not None, f"thiếu log model_loaded; log: {caplog.text}"
    duration = event["duration_ms"]
    assert isinstance(duration, (int, float)) and not isinstance(duration, bool)
    assert duration >= 0
    assert "model_load_failed" not in _events(caplog)


# ---- 4. Nhánh lỗi ----

LOAD_ERRORS = [
    FileNotFoundError("/secret/dir/clip_probe.joblib.sha256"),
    ValueError("Model checksum mismatch"),
    ImportError("No module named 'torch' (/secret/dir/site-packages)"),
]


@pytest.mark.parametrize("error", LOAD_ERRORS, ids=lambda e: type(e).__name__)
def test_nap_loi_thi_503_khong_lo_chi_tiet_va_khong_chet(error, caplog):
    def loader():
        raise error

    with (
        caplog.at_level(logging.INFO, logger="realcheck"),
        TestClient(create_app(loader=loader)) as client,
    ):
        health = client.get("/health")
        first = _post(client)
        second = _post(client)  # tiến trình còn sống, vẫn trả lỗi đúng
        docs = client.get("/docs")

    assert health.status_code == 503 and health.json()["model_ready"] is False
    for response in (first, second):
        assert response.status_code == 503, f"cần 503, nhận {response.status_code}"
        body = response.json()
        assert set(body) == {"error"}
        assert body["error"]["code"] == "MODEL_NOT_READY"
        assert body["error"]["message"] and body["error"]["request_id"]
        for leak in ("/secret", "Traceback", type(error).__name__, "torch", "checksum"):
            assert leak not in response.text, f"response lộ {leak!r}: {response.text}"
    assert docs.status_code == 200
    events = _events(caplog)
    assert events["model_load_failed"]["error"] == type(error).__name__
    assert "model_loaded" not in events, "nạp lỗi mà vẫn log model_loaded"


# ---- 5. Scorer tiêm thắng loader ----


def test_scorer_tiem_truc_tiep_thang_loader_va_khong_log_nap(caplog):
    def loader():
        raise AssertionError("loader không được gọi khi đã có scorer")

    def injected(image):
        return 0.1

    with (
        caplog.at_level(logging.INFO, logger="realcheck"),
        TestClient(create_app(scorer=injected, loader=loader)) as client,
    ):
        assert client.get("/health").status_code == 200
        assert _post(client).json()["score"] == 0.1
    assert "model_loaded" not in _events(caplog)


# ---- 6. Import app.main nhẹ ----


def test_import_app_main_khong_keo_torch_numpy_hay_models_score():
    code = (
        "import app.main\n"
        "heavy = ['torch', 'numpy', 'sentence_transformers', 'transformers',"
        " 'models.score', 'models.clip_input']\n"
        "print([m for m in heavy if m in sys.modules])"
    )
    result = _run_py(code)
    assert result.returncode == 0, f"import app.main lỗi: {result.stderr}"
    assert result.stdout.strip() == "[]", (
        f"import app.main kéo module nặng: {result.stdout.strip()}"
    )


# ---- 7. Biến app mức module ----


def test_app_mac_dinh_co_loader_va_health_503_khi_khong_co_model(tmp_path):
    missing = tmp_path / "khong_ton_tai.joblib"
    code = (
        "from fastapi.testclient import TestClient\n"
        "import app.main as m\n"
        "assert m.app.state.loader is not None, 'app mức module thiếu loader'\n"
        "assert m.app.state.scorer is None\n"
        "with TestClient(m.app) as c:\n"
        "    print(c.get('/health').status_code, c.get('/docs').status_code)\n"
    )
    result = _run_py(code, {"REALCHECK_MODEL_PATH": str(missing)})
    assert result.returncode == 0, f"app mức module lỗi: {result.stderr}"
    assert result.stdout.split()[-2:] == ["503", "200"], (
        f"không có model thì /health phải 503 và /docs 200; stdout={result.stdout!r}"
    )
    failed = [
        json.loads(line)
        for line in (result.stdout + result.stderr).splitlines()
        if line.startswith("{") and '"model_load_failed"' in line
    ]
    assert failed, f"thiếu log model_load_failed: {result.stdout!r} {result.stderr!r}"
    assert failed[0]["error"] == "FileNotFoundError", (
        f"cần FileNotFoundError (thiếu file model), nhận {failed[0]['error']}: "
        "ImportError nghĩa là models.score đổi tên hoặc hỏng import"
    )
