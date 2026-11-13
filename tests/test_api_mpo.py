"""Issue #95: API nhận ảnh MPO (iPhone), chỉ chấm khung đầu; ảnh động/đa khung khác vẫn bị từ chối."""

import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.settings import Settings
from models.normalize import normalize_image

URL = "/v1/analyze"
RED, GREEN = (200, 30, 30), (30, 200, 30)


class Recorder:
    """Chụp ảnh scorer nhận (kích thước, mode, pixel) và đếm số lần gọi."""

    def __init__(self):
        self.seen = []

    def __call__(self, image):
        self.seen.append((image.format, image.size, image.mode, image.tobytes()))
        return 0.5


def post(data, scorer=None, settings=None, name="a.jpg"):
    scorer = scorer or Recorder()
    client = TestClient(
        create_app(scorer=scorer, settings=settings), raise_server_exceptions=False
    )
    return client.post(URL, files={"file": (name, data, "image/jpeg")}), scorer


def mpo(first=(320, 240), second=(160, 120), extra=0):
    """Khung đầu đỏ, các khung phụ xanh (kích thước khác để phát hiện nhầm khung)."""
    frames = [Image.new("RGB", first, RED)] + [
        Image.new("RGB", second, GREEN) for _ in range(1 + extra)
    ]
    buf = io.BytesIO()
    frames[0].save(buf, "MPO", save_all=True, append_images=frames[1:])
    return buf.getvalue()


def jpeg_first_frame(size=(320, 240)):
    buf = io.BytesIO()
    Image.new("RGB", size, RED).save(buf, "JPEG")
    return buf.getvalue()


def animated(fmt):
    frames = [Image.new("RGB", (300, 300), c) for c in (RED, GREEN)]
    buf = io.BytesIO()
    frames[0].save(buf, fmt, save_all=True, append_images=frames[1:])
    return buf.getvalue()


def error_code(r):
    return r.json()["error"]["code"]


def test_fixture_that_su_la_mpo_nhieu_khung():
    with Image.open(io.BytesIO(mpo())) as im:
        assert im.format == "MPO"
        assert im.n_frames == 2


def test_mpo_hop_le_200_va_scorer_nhan_dung_khung_dau():
    r, scorer = post(mpo())
    assert r.status_code == 200, r.text
    assert len(scorer.seen) == 1
    fmt, size, mode, pixels = scorer.seen[0]
    assert (fmt, size, mode) == ("MPO", (320, 240), "RGB")
    # pixel giống hệt khung đầu giải mã độc lập, không lẫn khung phụ xanh
    with Image.open(io.BytesIO(mpo())) as ref:
        ref.seek(0)
        ref.load()
        assert pixels == ref.tobytes()


def test_mpo_nhieu_khung_khong_xu_ly_khung_khac():
    r, scorer = post(mpo(extra=3))
    assert r.status_code == 200, r.text
    assert len(scorer.seen) == 1
    assert scorer.seen[0][1] == (320, 240)


def test_mpo_qua_chuan_hoa_that_ra_cung_anh_voi_jpeg_khung_dau():
    """normalize_image (chuẩn hóa chung) không phân biệt MPO với JPEG cùng khung đầu."""
    out = []

    def scorer(image):
        out.append(normalize_image(image))
        return 0.5

    assert post(mpo(first=(400, 300)), scorer)[0].status_code == 200
    assert post(jpeg_first_frame((400, 300)), scorer)[0].status_code == 200
    a, b = out
    assert a.image.size == b.image.size
    assert a.image.tobytes() == b.image.tobytes()


def test_anh_dong_va_da_khung_khac_van_bi_tu_choi():
    for fmt, name in (("GIF", "a.gif"), ("WEBP", "a.webp"), ("PNG", "a.png")):
        r, scorer = post(animated(fmt), name=name)
        assert (r.status_code, error_code(r)) == (415, "UNSUPPORTED_FORMAT"), fmt
        assert scorer.seen == [], fmt


def test_mpo_hong_la_invalid_image():
    data = mpo()
    r, scorer = post(data[: len(data) // 3])
    assert (r.status_code, error_code(r)) == (400, "INVALID_IMAGE")
    assert scorer.seen == []


def test_file_gia_duoi_jpg_khong_phai_anh_la_invalid_image():
    r, scorer = post(b"day khong phai anh MPO", name="a.jpg")
    assert (r.status_code, error_code(r)) == (400, "INVALID_IMAGE")
    assert scorer.seen == []


def test_mpo_qua_lon_van_bi_chan():
    r, scorer = post(mpo(), settings=Settings(max_pixels=1000))
    assert (r.status_code, error_code(r)) == (413, "TOO_MANY_PIXELS")
    r, _ = post(mpo(), settings=Settings(max_side=100))
    assert (r.status_code, error_code(r)) == (413, "TOO_MANY_PIXELS")
    r, _ = post(mpo(), settings=Settings(max_file_bytes=100))
    assert (r.status_code, error_code(r)) == (413, "FILE_TOO_LARGE")
    assert scorer.seen == []


def test_mpo_giai_ma_dung_mot_lan(monkeypatch):
    calls = []
    original = Image.open
    monkeypatch.setattr(
        Image, "open", lambda *a, **k: calls.append(1) or original(*a, **k)
    )
    r, scorer = post(mpo())
    assert r.status_code == 200
    assert len(calls) == 1
    assert len(scorer.seen) == 1
