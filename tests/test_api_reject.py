"""T025 (spec 001): API từ chối ảnh quá nhỏ và ảnh không giải mã được, theo D05.

Mã lỗi đã duyệt (docs/decisions/realcheck-baseline.md, D05 approved 2026-11-04):
INVALID_IMAGE 400, IMAGE_TOO_SMALL 422. Hợp đồng C4: API không tự kiểm ngưỡng kích
thước, chỉ bắt ImageTooSmall do chuẩn hóa chung ném ra.

Khác test_analyze.py (scorer giả tự kiểm MIN_SIDE), scorer ở đây gọi chính
models.normalize.normalize_image, nên ImageTooSmall đến từ module ML thật. Hàm này chỉ
cần Pillow, không nạp CLIP.
"""

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.errors import ERROR_TABLE
from app.main import create_app
from app.schemas import ErrorCode
from models.normalize import MIN_SIDE, normalize_image

URL = "/v1/analyze"
APP_DIR = Path(__file__).resolve().parents[1] / "app"


class NormalizingScorer:
    """Scorer giả chạy chuẩn hóa thật rồi trả điểm cố định; đếm số lần được gọi."""

    def __init__(self):
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        normalize_image(image)
        return 0.5


@pytest.fixture
def scorer():
    return NormalizingScorer()


def post(scorer, data, name="a.jpg"):
    client = TestClient(create_app(scorer=scorer), raise_server_exceptions=False)
    return client.post(URL, files={"file": (name, data, "application/octet-stream")})


def encode(size, fmt="JPEG", **save_kwargs):
    buf = io.BytesIO()
    Image.effect_noise(size, 40).convert("RGB").save(buf, fmt, **save_kwargs)
    return buf.getvalue()


def assert_rejected(response, status, code):
    """Chỉ có envelope lỗi: không verdict, không score."""
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["message"] == ERROR_TABLE[ErrorCode(code)][1]
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize("size", [(255, 600), (600, 255), (255, 255), (1, 1)])
def test_canh_ngan_duoi_256_bi_tu_choi_bang_image_too_small_that(scorer, size):
    assert_rejected(post(scorer, encode(size)), 422, "IMAGE_TOO_SMALL")
    assert scorer.calls == 1  # C4: API không tự chặn trước, ngưỡng nằm trong models


@pytest.mark.parametrize("size", [(256, 256), (256, 900), (900, 256)])
def test_canh_ngan_256_hop_le_qua_chuan_hoa_that(scorer, size):
    r = post(scorer, encode(size))
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"verdict", "score", "exif", "reason"}


def test_png_canh_255_cung_bi_tu_choi(scorer):
    assert_rejected(
        post(scorer, encode((255, 400), "PNG"), "a.png"), 422, "IMAGE_TOO_SMALL"
    )


def test_orientation_khong_lam_lot_anh_qua_nho(scorer):
    """Cạnh ngắn tính trên ảnh gốc; xoay 90 độ không đổi cạnh ngắn."""
    exif = Image.Exif()
    exif[0x0112] = 6
    data = encode((255, 600), exif=exif.tobytes())
    assert_rejected(post(scorer, data), 422, "IMAGE_TOO_SMALL")


def test_thong_bao_neu_canh_ngan_toi_thieu_lay_tu_models():
    message = ERROR_TABLE[ErrorCode.IMAGE_TOO_SMALL][1]
    assert f"{MIN_SIDE} px" in message
    assert MIN_SIDE == 256


def _broken_inputs():
    jpeg, png = encode((400, 400)), encode((400, 400), "PNG")
    return {
        "text_gia_jpg": (b"day khong phai anh" * 20, "a.jpg"),
        "jpeg_cat_cut": (jpeg[: len(jpeg) // 2], "a.jpg"),
        "png_cat_cut": (png[: len(png) // 2], "a.png"),
        "chi_co_header_jpeg": (jpeg[:20], "a.jpg"),
        "png_hong_giua_file": (png[:200] + b"\0" * 200 + png[400:], "a.png"),
    }


@pytest.mark.parametrize("case", list(_broken_inputs()))
def test_anh_khong_giai_ma_duoc_bi_tu_choi_truoc_khi_chay_model(scorer, case):
    data, name = _broken_inputs()[case]
    assert_rejected(post(scorer, data, name), 400, "INVALID_IMAGE")
    assert scorer.calls == 0


def test_api_khong_lap_lai_nguong_kich_thuoc():
    """MIN_SIDE chỉ được dùng cho câu thông báo; app/ không so cạnh ảnh với ngưỡng."""
    hits = []
    for path in sorted(APP_DIR.glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            uses_threshold = "MIN_SIDE" in line or re.search(r"\b256\b", line)
            allowed = path.name == "errors.py" and (
                line.startswith("from models.normalize import MIN_SIDE")
                or "{MIN_SIDE} px" in line
            )
            if uses_threshold and not allowed:
                hits.append(f"{path.name}:{number}: {line.strip()}")
    assert hits == []
