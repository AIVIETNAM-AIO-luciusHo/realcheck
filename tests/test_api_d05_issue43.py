"""Khóa năm câu trả lời issue #43 (D05 làm rõ, 2026-11-11) bằng test chặt, mỗi ca đúng một kết quả.

Câu 1: thiếu phần file là 422 MISSING_FILE; INVALID_REQUEST luôn 422, kể cả multipart hỏng.
Câu 2: thứ tự request -> bytes -> model/slot -> giải mã -> score(); bước vi phạm đầu tiên thắng.
Câu 3: chuỗi exif "<Make> <Model>", bỏ lặp hãng, tối đa 64 ký tự mỗi giá trị.
Câu 4: lỗi không cần giải mã (400, 413) đứng trước 503; lỗi giải mã đứng sau 503.
Câu 5: score phải là float (Python hoặc numpy); str, int, bool, None, mảng nhiều phần tử là 500 MODEL_ERROR.
"""

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.settings import Settings
from app.verdict import MISSING_EXIF
from models.normalize import ImageTooSmall

URL = "/v1/analyze"


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (120, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


def client_for(scorer, settings=None):
    app = create_app(scorer=scorer, settings=settings)
    return TestClient(app, raise_server_exceptions=False)


class Spy:
    """Đếm số lần score() được gọi; trả giá trị cố định."""

    def __init__(self, value=0.5):
        self.value = value
        self.calls = 0

    def __call__(self, image):
        self.calls += 1
        return self.value


def encode(size=(300, 300), fmt="JPEG", **save_kwargs):
    buf = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buf, fmt, **save_kwargs)
    return buf.getvalue()


def exif_of(make=None, model=None):
    exif = Image.Exif()
    if make is not None:
        exif[0x010F] = make
    if model is not None:
        exif[0x0110] = model
    return exif.tobytes()


def post_file(client, data, name="a.jpg"):
    return client.post(URL, files={"file": (name, data, "image/jpeg")})


def apng(size=(300, 300)):
    buf = io.BytesIO()
    frames = [Image.new("RGB", size, c) for c in ("red", "blue")]
    frames[0].save(buf, "PNG", save_all=True, append_images=frames[1:])
    return buf.getvalue()


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_multipart_hong_la_422_invalid_request_va_khong_goi_model():
    calls = []
    client = client_for(lambda image: calls.append(1) or 0.5)
    r = client.post(
        URL,
        content=b"--x\r\nkhong phai multipart\r\n",
        headers={"content-type": "multipart/form-data; boundary=yyy"},
    )
    assert_error(r, 422, "INVALID_REQUEST")
    assert calls == []


@pytest.mark.parametrize(
    "value",
    [0.5, np.float32(0.5), np.float64(0.5), np.array(0.5)],
    ids=["float", "np_float32", "np_float64", "np_0d"],
)
def test_score_float_duoc_nhan(value):
    r = client_for(lambda image: value).post(URL, files={"file": ("a.jpg", jpeg())})
    assert r.status_code == 200, r.text
    assert r.json()["score"] == 0.5


@pytest.mark.parametrize(
    "value",
    ["0.5", 0, 1, True, False, None, np.int64(1), np.bool_(True), np.array([0.5])],
    ids=["str", "int0", "int1", "true", "false", "none", "np_int", "np_bool", "np_1d"],
)
def test_score_khong_phai_float_la_model_error(value):
    r = client_for(lambda image: value).post(URL, files={"file": ("a.jpg", jpeg())})
    assert_error(r, 500, "MODEL_ERROR")
    assert "verdict" not in r.text


# ---------- Câu 1: MISSING_FILE và INVALID_REQUEST ----------


def test_body_json_la_422_missing_file():
    spy = Spy()
    r = client_for(spy).post(URL, json={"file": "abc"})
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


def test_file_la_truong_chu_trong_multipart_la_422_missing_file():
    spy = Spy()
    r = client_for(spy).post(URL, data={"file": "abc"}, files={"x": ("a", b"b")})
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


def test_file_la_truong_chu_form_urlencoded_la_422_missing_file():
    spy = Spy()
    assert_error(client_for(spy).post(URL, data={"file": "abc"}), 422, "MISSING_FILE")
    assert spy.calls == 0


def test_content_type_text_plain_la_422_missing_file():
    spy = Spy()
    r = client_for(spy).post(
        URL, content=b"abc", headers={"content-type": "text/plain"}
    )
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


def test_sai_ten_truong_la_422_missing_file():
    spy = Spy()
    r = client_for(spy).post(URL, files={"image": ("a.jpg", jpeg(), "image/jpeg")})
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


def test_multipart_thieu_boundary_la_422_invalid_request():
    spy = Spy()
    r = client_for(spy).post(
        URL, content=b"x", headers={"content-type": "multipart/form-data"}
    )
    assert_error(r, 422, "INVALID_REQUEST")
    assert spy.calls == 0


# ---------- Câu 2: thứ tự kiểm tra, mỗi cặp liền kề ----------


def test_thu_tu_hai_file_sai_ten_truong_la_missing_file_khong_phai_multiple():
    spy = Spy()
    r = client_for(spy).post(
        URL,
        files=[
            ("a", ("a.jpg", jpeg(), "image/jpeg")),
            ("b", ("b.jpg", jpeg(), "image/jpeg")),
        ],
    )
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


def test_thu_tu_nhieu_file_trong_do_co_file_rong_la_multiple_khong_phai_empty():
    spy = Spy()
    r = client_for(spy).post(
        URL,
        files=[
            ("file", ("a.jpg", b"", "image/jpeg")),
            ("file", ("b.jpg", jpeg(), "image/jpeg")),
        ],
    )
    assert_error(r, 422, "MULTIPLE_FILES")
    assert spy.calls == 0


def test_thu_tu_nhieu_file_qua_lon_la_multiple_khong_phai_too_large():
    spy = Spy()
    data = jpeg()
    r = client_for(spy, Settings(max_file_bytes=len(data) - 1)).post(
        URL,
        files=[
            ("file", ("a.jpg", data, "image/jpeg")),
            ("file", ("b.jpg", data, "image/jpeg")),
        ],
    )
    assert_error(r, 422, "MULTIPLE_FILES")
    assert spy.calls == 0


def test_thu_tu_thieu_file_thang_model_chua_san_sang():
    r = client_for(None).post(URL, files={"x": ("a.jpg", b"", "image/jpeg")})
    assert_error(r, 422, "MISSING_FILE")


def test_thu_tu_file_rong_thang_model_chua_san_sang():
    assert_error(post_file(client_for(None), b""), 400, "EMPTY_FILE")


def test_thu_tu_file_qua_lon_thang_model_chua_san_sang():
    data = jpeg()
    client = client_for(None, Settings(max_file_bytes=len(data) - 1))
    assert_error(post_file(client, data), 413, "FILE_TOO_LARGE")


def test_thu_tu_model_chua_san_sang_thang_loi_giai_ma():
    assert_error(post_file(client_for(None), b"khong phai anh"), 503, "MODEL_NOT_READY")


def test_thu_tu_het_slot_thang_loi_giai_ma_va_khong_goi_model():
    spy = Spy()
    app = create_app(scorer=spy)
    assert app.state.inference._slots.acquire(blocking=False)
    client = TestClient(app, raise_server_exceptions=False)
    assert_error(post_file(client, b"khong phai anh"), 503, "SERVICE_BUSY")
    assert spy.calls == 0


def test_thu_tu_model_chua_san_sang_thang_het_slot():
    app = create_app(scorer=None)
    assert app.state.inference._slots.acquire(blocking=False)
    client = TestClient(app, raise_server_exceptions=False)
    assert_error(post_file(client, jpeg()), 503, "MODEL_NOT_READY")


def test_thu_tu_gif_nho_la_415_khong_phai_422():
    spy = Spy()
    r = post_file(client_for(spy), encode((100, 100), "GIF"), "a.gif")
    assert_error(r, 415, "UNSUPPORTED_FORMAT")
    assert spy.calls == 0


def test_thu_tu_anh_cat_cut_nho_la_400_khong_phai_422():
    spy = Spy()
    buf = io.BytesIO()
    Image.effect_noise((100, 100), 80).convert("RGB").save(buf, "PNG")
    data = buf.getvalue()
    assert_error(
        post_file(client_for(spy), data[: len(data) // 2], "a.png"),
        400,
        "INVALID_IMAGE",
    )
    assert spy.calls == 0


def test_thu_tu_qua_nhieu_pixel_thang_anh_nho():
    spy = Spy()
    r = post_file(client_for(spy, Settings(max_pixels=1000)), encode((100, 100)))
    assert_error(r, 413, "TOO_MANY_PIXELS")
    assert spy.calls == 0


def test_thu_tu_dinh_dang_sai_thang_qua_nhieu_pixel():
    spy = Spy()
    r = post_file(
        client_for(spy, Settings(max_pixels=1000)), encode((100, 100), "GIF"), "a.gif"
    )
    assert_error(r, 415, "UNSUPPORTED_FORMAT")
    assert spy.calls == 0


def test_thu_tu_qua_nhieu_pixel_thang_nhieu_khung_hinh():
    spy = Spy()
    r = post_file(client_for(spy, Settings(max_pixels=1000)), apng(), "a.png")
    assert_error(r, 413, "TOO_MANY_PIXELS")
    assert spy.calls == 0


def test_thu_tu_nhieu_khung_hinh_thang_loi_giai_ma():
    spy = Spy()
    data = apng()
    r = post_file(client_for(spy), data[: len(data) - 20], "a.png")
    assert_error(r, 415, "UNSUPPORTED_FORMAT")
    assert spy.calls == 0


def test_thu_tu_anh_nho_thang_score_tra_sai_kieu():
    """ImageTooSmall bị bắt trước khi kiểm kiểu của giá trị trả về."""
    calls = []

    def small_first(image):
        calls.append(image.size)
        raise ImageTooSmall(*image.size)

    r = post_file(client_for(small_first), encode((200, 200)))
    assert_error(r, 422, "IMAGE_TOO_SMALL")
    assert calls == [(200, 200)]


# ---------- Câu 3: chuỗi exif ----------


@pytest.mark.parametrize(
    ("make", "model", "expected"),
    [
        ("Canon", "EOS 5D", "Canon EOS 5D"),
        ("Canon", "Canon EOS 5D", "Canon EOS 5D"),
        ("NIKON CORPORATION", "NIKON D750", "NIKON D750"),
        ("CANON", "canon eos 5d", "canon eos 5d"),
        ("Canon Inc", "EOS 5D", "Canon Inc EOS 5D"),
        ("Canon", None, "Canon"),
        (None, "EOS 5D", "EOS 5D"),
        ("Canon", "", "Canon"),
        ("", "EOS 5D", "EOS 5D"),
        ("  Canon\t ", " EOS\n\x015D ", "Canon EOS 5D"),
        ("   ", "\t", MISSING_EXIF),
        (None, None, MISSING_EXIF),
        ("", "", MISSING_EXIF),
    ],
)
def test_exif_chuoi_hang_va_model(make, model, expected):
    spy = Spy()
    r = post_file(client_for(spy), encode(exif=exif_of(make, model)))
    assert r.status_code == 200, r.text
    assert r.json()["exif"] == expected
    assert spy.calls == 1


def test_exif_khong_co_exif_la_chuoi_mac_dinh():
    r = post_file(client_for(Spy()), encode())
    assert r.status_code == 200
    assert r.json()["exif"] == MISSING_EXIF == "Không có thông tin máy chụp"


@pytest.mark.parametrize(
    ("make", "model", "expected"),
    [
        (None, "A" * 100, "A" * 64),
        ("M" * 100, None, "M" * 64),
        ("M" * 64, "A" * 64, "M" * 64 + " " + "A" * 64),
        ("M" * 100, "x" * 100, "M" * 64 + " " + "x" * 64),
        (None, "A" * 63 + "  B", "A" * 63),
    ],
    ids=["model_100", "make_100", "moi_gia_tri_64", "ca_hai_100", "cat_roi_rstrip"],
)
def test_exif_cat_64_ky_tu_moi_gia_tri(make, model, expected):
    r = post_file(client_for(Spy()), encode(exif=exif_of(make, model)))
    assert r.status_code == 200, r.text
    assert r.json()["exif"] == expected


def test_exif_cat_64_ky_tu_truoc_khi_bo_lap_hang():
    make = "Canon"
    model = "Canon " + "x" * 100
    r = post_file(client_for(Spy()), encode(exif=exif_of(make, model)))
    assert r.json()["exif"] == ("Canon " + "x" * 100)[:64]


def test_exif_doc_loi_la_chuoi_mac_dinh():
    from app.uploads import read_exif

    class Broken:
        def getexif(self):
            raise OSError("exif hong")

    class NonString:
        def getexif(self):
            return {0x010F: 123, 0x0110: b"EOS"}

    assert read_exif(Broken()) == MISSING_EXIF
    assert read_exif(NonString()) == MISSING_EXIF


# ---------- Câu 4: model chưa sẵn sàng ----------


def test_loader_loi_van_503_cho_anh_hop_le_va_400_cho_file_rong():
    calls = []

    def bad_loader():
        calls.append(1)
        raise RuntimeError("khong nap duoc")

    with TestClient(create_app(loader=bad_loader), raise_server_exceptions=False) as c:
        assert_error(post_file(c, jpeg()), 503, "MODEL_NOT_READY")
        assert_error(post_file(c, b""), 400, "EMPTY_FILE")
        assert_error(post_file(c, b"text"), 503, "MODEL_NOT_READY")
    assert calls == [1]


def test_loader_chua_chay_xong_scorer_none_thu_tu_van_dung():
    calls = []

    def never_loader():
        calls.append(1)
        raise AssertionError("loader khong duoc chay khi lifespan chua bat dau")

    client = TestClient(create_app(loader=never_loader), raise_server_exceptions=False)
    data = jpeg()
    # Không dùng `with`: lifespan chưa chạy nên scorer vẫn là None, như lúc đang nạp.
    assert_error(post_file(client, b""), 400, "EMPTY_FILE")
    assert_error(post_file(client, b"text"), 503, "MODEL_NOT_READY")
    assert_error(post_file(client, data), 503, "MODEL_NOT_READY")
    assert_error(client.post(URL), 422, "MISSING_FILE")
    assert calls == []
