"""D05 (issue #43) câu 3 và 4: EXIF Unicode ở mức hàm và nạp model không có timeout.

Qua API, Pillow ghi thẻ EXIF thành ASCII nên Unicode không đến được; test ở mức hàm bằng cách
gắn EXIF vào ảnh trong bộ nhớ. D11: nạp model lúc khởi động không có timeout (khác model_timeout_s).
"""

import asyncio
import threading

import pytest
from PIL import Image

from app.inference import InferenceService
from app.settings import Settings
from app.uploads import _clean_exif_text, read_exif
from app.verdict import MISSING_EXIF

MAKE, MODEL = 0x010F, 0x0110


def image_with(make=None, model=None):
    image = Image.new("RGB", (300, 300))
    tags = {k: v for k, v in ((MAKE, make), (MODEL, model)) if v is not None}
    image.getexif().update(tags)
    return image


@pytest.mark.parametrize(
    ("make", "model", "expected"),
    [
        ("Máy Việt", "Đời 2", "Máy Việt Đời 2"),
        ("Máy Việt", None, "Máy Việt"),
        (None, "Đời 2", "Đời 2"),
        ("ĐỜI", "đời 2", "đời 2"),  # bỏ lặp hãng không phân biệt hoa thường, cả Unicode
        ("Máy", "Máyx Việt", "Máy Máyx Việt"),  # so nguyên từ, không theo tiền tố
    ],
)
def test_exif_unicode_giu_nguyen_o_muc_ham(make, model, expected):
    assert read_exif(image_with(make, model)) == expected


def test_exif_unicode_cat_64_ky_tu_theo_ky_tu_khong_theo_byte():
    out = read_exif(image_with("Đ" * 100, "ệ" * 100))
    assert out == "Đ" * 64 + " " + "ệ" * 64
    assert len(out) == 129


def test_exif_unicode_rong_la_chuoi_mac_dinh():
    assert read_exif(image_with("\x00\n", "  ")) == MISSING_EXIF


def test_clean_exif_text_bo_ky_tu_dieu_khien_va_gop_khoang_trang():
    assert _clean_exif_text("Máy\x00 Việt\n") == "Máy Việt"
    assert _clean_exif_text("  Đời\t\t2  ") == "Đời 2"


def test_load_khong_co_timeout_luc_khoi_dong():
    """Loader treo thì load() vẫn chờ, kể cả khi model_timeout_s rất nhỏ (D11)."""

    async def go():
        release = threading.Event()
        service = InferenceService(Settings(model_timeout_s=0.05))

        def scorer(image):
            return 0.5

        def loader():
            release.wait()
            return scorer

        task = asyncio.ensure_future(service.load(loader))
        try:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.3)
            assert not task.done()
        finally:
            release.set()  # luôn nhả loader, kể cả khi assert lỗi, để thread không treo test
        assert await task is scorer
        service.close()

    asyncio.run(go())


def test_load_loi_la_chua_san_sang_khong_nem_ra_ngoai():
    def boom():
        raise FileNotFoundError("thiếu file")

    async def go():
        service = InferenceService(Settings())
        assert await service.load(boom) is None
        service.close()

    asyncio.run(go())
