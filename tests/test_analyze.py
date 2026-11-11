"""Test hợp đồng cho POST /v1/analyze (KAN-27), viết trước khi endpoint tồn tại (TDD).

Nguồn: docs/decisions/realcheck-baseline.md. D05, D06, D07 đã `approved`; hợp đồng
`score` vẫn `proposed` (chờ Kiệt, Lực). Test phải đổi cùng file decisions nếu mục đổi.
specs/001-unified-image-normalization/contracts/interfaces.md C4: API giải mã một lần,
đọc EXIF từ ảnh gốc, gọi score(ảnh gốc), bắt ImageTooSmall, KHÔNG resize hay nén.

Dùng create_app(scorer=<giả>) + TestClient, ảnh tổng hợp bằng Pillow, không mạng, không
model thật. Không dùng skip/xfail.

Không test SERVICE_BUSY (503) và MODEL_TIMEOUT (504): thuộc InferenceService (D11, D12),
ticket khác. Năm điểm D05 từng mơ hồ đã được chốt ở issue #43 và khóa ở cuối file này và ở test_api_d05_issue43.py.
"""

import io
import re

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app
from app.settings import Settings
from app.verdict import MISSING_EXIF
from models.normalize import MIN_SIDE, ImageTooSmall

URL = "/v1/analyze"
ENVELOPE_KEYS = {"code", "message", "request_id"}
SUCCESS_KEYS = {"verdict", "score", "exif", "reason"}


class SpyScorer:
    """Ghi lại số lần gọi và kích thước ảnh nhận được.

    Như score() thật (C4): ảnh có cạnh ngắn < MIN_SIDE thì raise ImageTooSmall; API không
    tự kiểm ngưỡng nên scorer vẫn được gọi và API chỉ bắt exception.
    """

    def __init__(self, value=0.5):
        self.value = value
        self.sizes = []

    def __call__(self, image):
        self.sizes.append(image.size)
        if min(image.size) < MIN_SIDE:
            raise ImageTooSmall(*image.size)
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value

    @property
    def calls(self):
        return len(self.sizes)


def make_client(scorer, settings=None):
    app = create_app(scorer=scorer, settings=settings)
    return TestClient(app, raise_server_exceptions=False)


def encode(size=(300, 300), fmt="JPEG", color=(120, 80, 40), **save_kwargs):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt, **save_kwargs)
    return buf.getvalue()


def noisy_image(size=(400, 400)):
    return Image.effect_noise(size, 80).convert("RGB")


def encode_noisy(fmt):
    buf = io.BytesIO()
    noisy_image().save(buf, fmt)
    return buf.getvalue()


def exif_bytes(make=None, model=None, orientation=None):
    exif = Image.Exif()
    if make:
        exif[0x010F] = make
    if model:
        exif[0x0110] = model
    if orientation:
        exif[0x0112] = orientation
    return exif.tobytes()


def post(client, data, name="a.jpg", mime="image/jpeg"):
    return client.post(URL, files={"file": (name, data, mime)})


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == ENVELOPE_KEYS
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


@pytest.fixture
def spy():
    return SpyScorer()


@pytest.fixture
def client(spy):
    return make_client(spy)


# ---------- 200: hợp đồng thành công (D05, AC-01) ----------


@pytest.mark.parametrize(
    ("fmt", "name", "mime"),
    [("JPEG", "a.jpg", "image/jpeg"), ("PNG", "a.png", "image/png")],
)
def test_200_bon_truong_dung_hop_dong(client, spy, fmt, name, mime):
    """Theo D05, AC-01: đúng bốn trường, không trường thừa."""
    r = post(client, encode(fmt=fmt), name, mime)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == SUCCESS_KEYS
    assert body["score"] == 0.5
    assert body["verdict"] == "uncertain"
    assert isinstance(body["exif"], str) and body["exif"]
    assert re.search(r"[^\x00-\x7f]", body["reason"]), "reason phải là tiếng Việt"
    assert spy.calls == 1


def test_200_co_header_request_id(client):
    """Theo D05: response thành công mang X-Request-ID."""
    r = post(client, encode())
    assert r.status_code == 200
    assert r.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("score", "verdict"),
    [
        (0.0, "likely_real"),
        (0.1, "likely_real"),
        (0.299999, "likely_real"),
        (0.3, "uncertain"),
        (0.5, "uncertain"),
        (0.7, "uncertain"),
        (0.700001, "likely_ai"),
        (0.9, "likely_ai"),
        (1.0, "likely_ai"),
    ],
)
def test_verdict_theo_score_tiem_vao(score, verdict):
    """Theo D05 + app/verdict.py: hai biên 0.3 và 0.7 thuộc Chưa chắc."""
    r = post(make_client(SpyScorer(score)), encode())
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] == verdict
    assert r.json()["score"] == score


# ---------- EXIF và ảnh gốc (C4) ----------


def test_exif_co_hang_va_model():
    """Theo hợp đồng C4: đọc hãng/model từ ảnh gốc."""
    data = encode(exif=exif_bytes("Canon", "EOS 5D"))
    r = post(make_client(SpyScorer()), data)
    assert r.status_code == 200, r.text
    assert "Canon" in r.json()["exif"]
    assert "EOS 5D" in r.json()["exif"]


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_khong_exif_van_tra_verdict_va_exif_mac_dinh(fmt):
    """Theo schema hiện tại: exif là chuỗi không rỗng, quy ước app.verdict.MISSING_EXIF."""
    r = post(make_client(SpyScorer(0.9)), encode(fmt=fmt))
    assert r.status_code == 200, r.text
    assert r.json()["exif"] == MISSING_EXIF
    assert r.json()["verdict"] == "likely_ai"


def test_exif_khong_doi_verdict():
    """Theo verdict.py: EXIF chỉ là bằng chứng phụ, verdict chỉ phụ thuộc score."""
    with_exif = post(
        make_client(SpyScorer(0.1)), encode(exif=exif_bytes("Canon", "EOS 5D"))
    )
    without = post(make_client(SpyScorer(0.1)), encode())
    assert with_exif.status_code == without.status_code == 200
    assert with_exif.json()["verdict"] == without.json()["verdict"] == "likely_real"


def test_orientation_khong_lam_api_resize_hay_xoay():
    """Theo C4: scorer nhận ảnh gốc (kích thước lưu), không xoay/resize."""
    spy = SpyScorer()
    data = encode((400, 300), exif=exif_bytes(orientation=6))
    r = post(make_client(spy), data)
    assert r.status_code == 200, r.text
    assert spy.sizes == [(400, 300)]


def test_api_khong_resize_anh_4000x3000():
    """Theo D07 + C4: 12 MP hợp lệ; scorer nhận đúng 4000x3000."""
    spy = SpyScorer()
    r = post(make_client(spy), encode((4000, 3000)))
    assert r.status_code == 200, r.text
    assert spy.sizes == [(4000, 3000)]


def test_scorer_nhan_dung_kich_thuoc_anh_nho_hop_le():
    """Theo C4: 256x256 không bị API đổi kích thước."""
    spy = SpyScorer()
    assert post(make_client(spy), encode((256, 256))).status_code == 200
    assert spy.sizes == [(256, 256)]


# ---------- Lỗi 400 ----------


def test_400_empty_file(spy):
    """Theo D05: file 0 byte -> 400 EMPTY_FILE."""
    assert_error(post(make_client(spy), b""), 400, "EMPTY_FILE")
    assert spy.calls == 0


def test_400_invalid_image_text_gia_jpg(spy):
    """Theo D05: text giả .jpg -> 400 INVALID_IMAGE."""
    r = post(make_client(spy), b"day khong phai anh, chi la text" * 50)
    assert_error(r, 400, "INVALID_IMAGE")
    assert spy.calls == 0


@pytest.mark.parametrize(("fmt", "name"), [("JPEG", "a.jpg"), ("PNG", "a.png")])
def test_400_invalid_image_bi_cat_cut(spy, fmt, name):
    """Theo D05: ảnh bị cắt cụt -> 400 INVALID_IMAGE, không gọi scorer."""
    data = encode_noisy(fmt)
    r = post(make_client(spy), data[: len(data) * 6 // 10], name)
    assert_error(r, 400, "INVALID_IMAGE")
    assert spy.calls == 0


# ---------- Lỗi 415 ----------


@pytest.mark.parametrize(
    ("fmt", "name"), [("GIF", "a.gif"), ("BMP", "a.bmp"), ("WEBP", "a.webp")]
)
def test_415_dinh_dang_doc_duoc_nhung_khong_phai_jpeg_png(spy, fmt, name):
    """Theo D05: ảnh hợp lệ không phải JPEG/PNG -> 415 UNSUPPORTED_FORMAT."""
    r = post(make_client(spy), encode(fmt=fmt), name, "image/jpeg")
    assert_error(r, 415, "UNSUPPORTED_FORMAT")
    assert spy.calls == 0


def test_415_png_nhieu_khung_hinh(spy):
    """Theo D05: nhiều khung hình -> 415 UNSUPPORTED_FORMAT."""
    buf = io.BytesIO()
    frames = [Image.new("RGB", (300, 300), c) for c in ("red", "blue")]
    frames[0].save(buf, "PNG", save_all=True, append_images=frames[1:])
    r = post(make_client(spy), buf.getvalue(), "a.png", "image/png")
    assert_error(r, 415, "UNSUPPORTED_FORMAT")
    assert spy.calls == 0


def test_415_gif_nhieu_khung_hinh(spy):
    """Theo D05: GIF động -> 415 UNSUPPORTED_FORMAT."""
    buf = io.BytesIO()
    frames = [Image.new("P", (300, 300), c) for c in (0, 1)]
    frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:])
    r = post(make_client(spy), buf.getvalue(), "a.gif", "image/gif")
    assert_error(r, 415, "UNSUPPORTED_FORMAT")
    assert spy.calls == 0


# ---------- Lỗi 413 ----------


def test_413_file_too_large_ranh_gioi_d06(spy):
    """Theo D06: đúng limit byte qua, limit+1 byte bị 413 FILE_TOO_LARGE."""
    data = encode()
    ok = make_client(spy, Settings(max_file_bytes=len(data)))
    assert post(ok, data).status_code == 200
    assert spy.calls == 1

    spy2 = SpyScorer()
    too_big = make_client(spy2, Settings(max_file_bytes=len(data) - 1))
    assert_error(post(too_big, data), 413, "FILE_TOO_LARGE")
    assert spy2.calls == 0


def test_413_file_too_large_gioi_han_mac_dinh_5_mib(spy):
    """Theo D06: mặc định 5.242.880 byte; thừa 1 byte -> 413.

    Ảnh PNG hợp lệ được đệm byte 0 sau IEND (Pillow bỏ qua phần đệm) để đạt đúng kích thước.
    """
    limit = 5_242_880
    base = encode(fmt="PNG")
    client = make_client(spy)
    at_limit = base + b"\0" * (limit - len(base))
    assert post(client, at_limit, "a.png", "image/png").status_code == 200

    spy2 = SpyScorer()
    over = base + b"\0" * (limit + 1 - len(base))
    r = post(make_client(spy2), over, "a.png", "image/png")
    assert_error(r, 413, "FILE_TOO_LARGE")
    assert spy2.calls == 0


def test_413_too_many_pixels_theo_tong_so_pixel(spy):
    """Theo D07: đúng max_pixels qua, vượt -> 413 TOO_MANY_PIXELS."""
    settings = Settings(max_pixels=300 * 300)
    assert post(make_client(spy, settings), encode((300, 300))).status_code == 200

    spy2 = SpyScorer()
    r = post(make_client(spy2, settings), encode((301, 300)))
    assert_error(r, 413, "TOO_MANY_PIXELS")
    assert spy2.calls == 0


def test_413_too_many_pixels_theo_canh_toi_da(spy):
    """Theo D07: cạnh dài hơn max_side -> 413 dù tổng pixel còn nhỏ."""
    settings = Settings(max_side=400)
    assert post(make_client(spy, settings), encode((400, 300))).status_code == 200

    spy2 = SpyScorer()
    r = post(make_client(spy2, settings), encode((401, 300)))
    assert_error(r, 413, "TOO_MANY_PIXELS")
    assert spy2.calls == 0


# ---------- Lỗi 422 ----------


@pytest.mark.parametrize("size", [(200, 200), (255, 400), (400, 255), (255, 255)])
def test_422_image_too_small(spy, size):
    """Theo D05: cạnh ngắn < 256 -> 422 IMAGE_TOO_SMALL."""
    assert_error(post(make_client(spy), encode(size)), 422, "IMAGE_TOO_SMALL")
    assert (
        spy.calls == 1
    )  # C4: API không tự kiểm ngưỡng, chỉ bắt ImageTooSmall từ score


def test_422_image_too_small_message_neu_256():
    """Theo C4 bước 4: thông báo nêu kích thước tối thiểu 256 px."""
    r = post(make_client(SpyScorer()), encode((200, 200)))
    assert "256" in r.json()["error"]["message"]


def test_422_image_too_small_theo_canh_ngan_sau_orientation():
    """Theo D05: 255x400 xoay bởi Orientation vẫn có cạnh ngắn 255 -> 422."""
    data = encode((255, 400), exif=exif_bytes(orientation=6))
    assert_error(post(make_client(SpyScorer()), data), 422, "IMAGE_TOO_SMALL")


@pytest.mark.parametrize("size", [(256, 256), (256, 400), (400, 256)])
def test_256_tro_len_van_qua(size):
    """Theo D05: ngưỡng là < 256, nên cạnh ngắn 256 vẫn hợp lệ."""
    assert post(make_client(SpyScorer()), encode(size)).status_code == 200


def test_422_missing_file_khong_co_truong_file(spy):
    """Theo D05: thiếu trường file -> 422 MISSING_FILE."""
    r = make_client(spy).post(URL, files={"other": ("a.jpg", encode(), "image/jpeg")})
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


def test_422_missing_file_khong_co_body(spy):
    """Theo D05: POST không body -> thiếu file -> 422 MISSING_FILE."""
    assert_error(make_client(spy).post(URL), 422, "MISSING_FILE")
    assert spy.calls == 0


def test_422_multiple_files(spy):
    """Theo D05: nhiều hơn một file -> 422 MULTIPLE_FILES."""
    data = encode()
    r = make_client(spy).post(
        URL,
        files=[
            ("file", ("a.jpg", data, "image/jpeg")),
            ("file", ("b.jpg", data, "image/jpeg")),
        ],
    )
    assert_error(r, 422, "MULTIPLE_FILES")
    assert spy.calls == 0


# ---------- Lỗi 5xx ----------


def test_503_model_not_ready_khi_scorer_none():
    """Theo D05: chưa có model -> 503 MODEL_NOT_READY."""
    assert_error(post(make_client(None), encode()), 503, "MODEL_NOT_READY")


@pytest.mark.parametrize(
    "bad",
    [
        RuntimeError("bi mat /srv/models/clip.pt"),
        float("nan"),
        float("inf"),
        float("-inf"),
        -0.000001,
        1.000001,
        None,
    ],
    ids=["raise", "nan", "inf", "-inf", "duoi0", "tren1", "none"],
)
def test_500_model_error_va_khong_lo_chi_tiet(bad):
    """Theo D05: score lỗi hoặc trả NaN/inf/ngoài [0,1]/không phải số -> 500."""
    spy = SpyScorer(bad)
    r = post(make_client(spy), encode())
    assert_error(r, 500, "MODEL_ERROR")
    assert spy.calls == 1
    for leak in ("Traceback", "RuntimeError", "/srv/models", "clip.pt", ".py"):
        assert leak not in r.text


def test_404_not_found(client):
    """Theo D05: đường dẫn không tồn tại -> 404 NOT_FOUND."""
    assert_error(client.get("/v1/khong-ton-tai"), 404, "NOT_FOUND")
    assert_error(client.post("/v1/analyze/extra"), 404, "NOT_FOUND")


def test_405_method_not_allowed_co_allow(client):
    """Theo D05: GET /v1/analyze -> 405 METHOD_NOT_ALLOWED, có Allow: POST."""
    r = client.get(URL)
    assert_error(r, 405, "METHOD_NOT_ALLOWED")
    assert "POST" in r.headers["Allow"]


# ---------- Scorer không bị gọi với đầu vào không hợp lệ ----------


@pytest.mark.parametrize(
    "case, status",
    [
        ("empty", 400),
        ("text", 400),
        ("gif", 415),
        ("no_file", 422),
        ("too_many_files", 422),
    ],
)
def test_scorer_khong_duoc_goi_voi_dau_vao_khong_hop_le(spy, case, status):
    """Theo D05: lỗi file rỗng, không phải ảnh, sai định dạng, thiếu/nhiều file dừng trước khi gọi score."""
    client = make_client(spy)
    data = encode()
    if case == "empty":
        r = post(client, b"")
    elif case == "text":
        r = post(client, b"not an image")
    elif case == "gif":
        r = post(client, encode(fmt="GIF"), "a.gif")
    elif case == "no_file":
        r = client.post(URL)
    else:
        r = client.post(
            URL,
            files=[("file", ("a.jpg", data, "image/jpeg"))] * 2,
        )
    assert r.status_code == status, r.text
    assert spy.calls == 0


# ---------- D05 đã chốt ở issue #43: khóa chặt, mỗi ca đúng một kết quả ----------
# Các test thứ tự lỗi, exif, 503 nằm ở tests/test_api_d05_issue43.py.


def test_body_json_la_422_missing_file(spy):
    """Issue #43 câu 1: body JSON không có phần file là 422 MISSING_FILE."""
    r = make_client(spy).post(URL, json={"file": "abc"})
    assert_error(r, 422, "MISSING_FILE")
    assert spy.calls == 0


@pytest.mark.parametrize(
    "value",
    ["0.5", 1, 0, True, False, None],
    ids=["chuoi", "int1", "int0", "true", "false", "none"],
)
def test_scorer_tra_kieu_khong_phai_float_la_500_model_error(value):
    """Issue #43 câu 5: chỉ float Python hoặc numpy; kiểu khác là 500 MODEL_ERROR."""
    spy = SpyScorer(value)
    r = post(make_client(spy), encode())
    assert_error(r, 500, "MODEL_ERROR")
    assert spy.calls == 1
    assert "verdict" not in r.text
