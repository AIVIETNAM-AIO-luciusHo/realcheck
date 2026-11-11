"""T017 (spec 001): API truyền đúng ảnh gốc đã giải mã vào score, không xử lý pixel.

Hợp đồng C2/C4 trong specs/001-unified-image-normalization/contracts/interfaces.md:
API giải mã một lần, đọc EXIF từ ảnh gốc trước khi scorer chạy, gọi score(ảnh gốc);
KHÔNG resize, nén hay chuẩn hóa. test_analyze.py đã kiểm kích thước ảnh scorer nhận;
file này kiểm chính đối tượng ảnh: kiểu, pixel, format, mode, EXIF và số lần giải mã.

Dùng create_app(scorer=<giả>) + TestClient, ảnh tổng hợp bằng Pillow, không model thật.
"""

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app

URL = "/v1/analyze"
APP_DIR = Path(__file__).resolve().parents[1] / "app"
EXIF_MAKE, EXIF_MODEL, EXIF_ORIENTATION = 0x010F, 0x0110, 0x0112


class RecordingScorer:
    """Chụp lại ảnh scorer nhận ngay lúc được gọi, trước khi API làm gì tiếp."""

    def __init__(self):
        self.seen = []

    def __call__(self, image):
        self.seen.append(
            {
                "is_pil": isinstance(image, Image.Image),
                "format": image.format,
                "mode": image.mode,
                "size": image.size,
                "pixels": image.tobytes(),
                "exif": dict(image.getexif()),
            }
        )
        return 0.5


def post(scorer, data, name="a.jpg"):
    client = TestClient(create_app(scorer=scorer), raise_server_exceptions=False)
    return client.post(URL, files={"file": (name, data, "application/octet-stream")})


def encode(image, fmt, **save_kwargs):
    buf = io.BytesIO()
    image.save(buf, fmt, **save_kwargs)
    return buf.getvalue()


def exif_with(make=None, model=None, orientation=None):
    exif = Image.Exif()
    for tag, value in (
        (EXIF_MAKE, make),
        (EXIF_MODEL, model),
        (EXIF_ORIENTATION, orientation),
    ):
        if value is not None:
            exif[tag] = value
    return exif.tobytes()


def decoded(data):
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return image.format, image.mode, image.size, image.tobytes()


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_scorer_nhan_pil_image_trung_tung_pixel_voi_file_goc(fmt):
    """Pixel giống hệt bản tự giải mã: API không resize, không nén lại, không đổi màu."""
    data = encode(Image.effect_noise((420, 300), 60).convert("RGB"), fmt)
    scorer = RecordingScorer()
    r = post(scorer, data, f"a.{fmt.lower()}")
    assert r.status_code == 200, r.text
    assert len(scorer.seen) == 1
    seen = scorer.seen[0]
    want_format, want_mode, want_size, want_pixels = decoded(data)
    assert seen["is_pil"]
    assert (seen["format"], seen["mode"], seen["size"]) == (
        want_format,
        want_mode,
        want_size,
    )
    assert seen["pixels"] == want_pixels


@pytest.mark.parametrize(
    ("mode", "fmt"),
    [("RGBA", "PNG"), ("L", "PNG"), ("L", "JPEG"), ("CMYK", "JPEG"), ("P", "PNG")],
)
def test_api_khong_doi_mode_mau_truoc_khi_goi_scorer(mode, fmt):
    """Chuyển RGB là việc của chuẩn hóa chung trong score(), không phải của API."""
    data = encode(Image.new(mode, (300, 300)), fmt)
    scorer = RecordingScorer()
    assert post(scorer, data).status_code == 200
    assert scorer.seen[0]["mode"] == mode
    assert scorer.seen[0]["pixels"] == decoded(data)[3]


def test_scorer_nhan_exif_goc_gom_orientation():
    """Scorer cần orientation để tự xoay; API không xoay và không bỏ EXIF."""
    data = encode(
        Image.new("RGB", (400, 300)),
        "JPEG",
        exif=exif_with("Canon", "EOS 5D", orientation=6),
    )
    scorer = RecordingScorer()
    assert post(scorer, data).status_code == 200
    exif = scorer.seen[0]["exif"]
    assert exif[EXIF_ORIENTATION] == 6
    assert (exif[EXIF_MAKE], exif[EXIF_MODEL]) == ("Canon", "EOS 5D")
    assert scorer.seen[0]["size"] == (400, 300)


def test_exif_duoc_doc_truoc_khi_scorer_lam_mat_metadata():
    """Chuẩn hóa thật xóa EXIF; scorer giả xóa trên chính ảnh nhận được để mô phỏng."""

    def stripping_scorer(image):
        image.getexif().clear()
        image.info.pop("exif", None)
        return 0.5

    data = encode(
        Image.new("RGB", (300, 300)), "JPEG", exif=exif_with("Canon", "EOS 5D")
    )
    r = post(stripping_scorer, data)
    assert r.status_code == 200, r.text
    assert r.json()["exif"] == "Canon EOS 5D"


def test_anh_duoc_giai_ma_dung_mot_lan_moi_request(monkeypatch):
    original_open = Image.open
    calls = []

    def counting_open(*args, **kwargs):
        calls.append(1)
        return original_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", counting_open)
    data = encode(Image.new("RGB", (300, 300)), "JPEG")
    scorer = RecordingScorer()
    assert post(scorer, data).status_code == 200
    assert len(calls) == 1
    assert len(scorer.seen) == 1


FORBIDDEN_PIXEL_OPS = re.compile(
    r"\.resize\(|\.thumbnail\(|\.save\(|\.convert\(|\.crop\(|\.transpose\(|"
    r"\bImageOps\b|\bnormalize_image\b|\bexif_transpose\b"
)


def test_app_khong_co_buoc_xu_ly_pixel_rieng():
    """Chuẩn hóa chỉ nằm trong models/ (C1, C4); app/ không resize, nén hay xoay."""
    hits = [
        f"{path.name}:{number}: {line.strip()}"
        for path in sorted(APP_DIR.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN_PIXEL_OPS.search(line)
    ]
    assert hits == []
