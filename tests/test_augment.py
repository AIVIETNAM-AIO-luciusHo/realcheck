"""models/augment.py: tất định theo seed, ảnh nhỏ không lỗi, chất lượng JPEG đúng bảng lượng tử."""

import io

import numpy as np
import pytest
from PIL import Image

from models import augment


def photo(size=(64, 48), seed=0, mode="RGB"):
    rng = np.random.default_rng(seed)
    base = np.linspace(0, 255, size[0])[None, :, None] * np.ones((size[1], 1, 3))
    arr = np.clip(base + rng.normal(0, 25, (size[1], size[0], 3)), 0, 255).astype(
        np.uint8
    )
    return Image.fromarray(arr, "RGB").convert(mode)


def same(a, b):
    return a.size == b.size and a.convert("RGB").tobytes() == b.convert("RGB").tobytes()


@pytest.mark.parametrize("quality", [20, 50, 95])
def test_jpeg_quality_dung_bang_luong_tu(quality):
    img = photo()
    out = augment.jpeg_recompress(img, quality)
    ref = Image.open(io.BytesIO(augment.encode_jpeg(img, quality)))
    assert out.quantization == ref.quantization
    # bảng lượng tử giảm khi chất lượng tăng
    assert np.mean(augment.jpeg_recompress(img, 95).quantization[0]) < np.mean(
        augment.jpeg_recompress(img, 20).quantization[0]
    )
    assert out.size == img.size and out.mode == "RGB"


@pytest.mark.parametrize("quality", [0, 101, 50.5, True, "80"])
def test_quality_khong_hop_le(quality):
    with pytest.raises(ValueError, match="quality"):
        augment.jpeg_recompress(photo(), quality)


def test_downscale_upscale_giu_kich_thuoc_va_mat_chi_tiet():
    img = photo((64, 64))
    out = augment.downscale_upscale(img, 0.5)
    assert out.size == img.size
    assert not same(out, img)
    assert same(
        augment.downscale_upscale(img, 1.0), augment.downscale_upscale(img, 1.0)
    )
    for bad in (0, -0.1, 1.5):
        with pytest.raises(ValueError, match="factor"):
            augment.downscale_upscale(img, bad)


def test_cung_seed_cung_byte_khac_seed_khac():
    img = photo()
    a, b = augment.screenshot_like(img, 7), augment.screenshot_like(img, 7)
    assert same(a, b)
    assert not same(a, augment.screenshot_like(img, 8))
    r1, ap1 = augment.apply_random(img, 123, 1.0)
    r2, ap2 = augment.apply_random(img, 123, 1.0)
    assert same(r1, r2) and ap1 == ap2


@pytest.mark.parametrize("size", [(1, 1), (2, 3), (7, 5), (8, 8), (255, 9)])
def test_anh_nho_khong_loi(size):
    img = photo(size)
    for out in (
        augment.jpeg_recompress(img, 30),
        augment.downscale_upscale(img, 0.5),
        augment.screenshot_like(img, 1),
        augment.apply_random(img, 5, 1.0)[0],
    ):
        assert out.size == size and out.mode == "RGB"


@pytest.mark.parametrize("mode", ["L", "RGBA", "P"])
def test_mode_khac_duoc_doi_sang_rgb(mode):
    out, _ = augment.apply_random(photo(mode=mode), 3, 1.0)
    assert out.mode == "RGB"


def test_apply_random_ghi_dung_cac_phep_da_ap():
    img = photo()
    none, applied0 = augment.apply_random(img, 9, 0.0)
    assert applied0 == [] and same(none, img)
    _, applied = augment.apply_random(img, 9, 1.0)
    assert [a["op"] for a in applied] == [
        "jpeg_recompress",
        "downscale_upscale",
        "screenshot_like",
    ]
    assert 30 <= applied[0]["quality"] <= 90 and applied[1]["factor"] in (
        0.5,
        0.67,
        0.75,
    )
    with pytest.raises(ValueError, match="p phải"):
        augment.apply_random(img, 1, 1.5)


def test_apply_random_dung_lai_duoc_tu_danh_sach():
    img = photo()
    out, applied = augment.apply_random(img, 11, 1.0)
    rebuilt = img
    for a in applied:
        if a["op"] == "jpeg_recompress":
            rebuilt = augment.jpeg_recompress(rebuilt, a["quality"])
        elif a["op"] == "downscale_upscale":
            rebuilt = augment.downscale_upscale(rebuilt, a["factor"])
        else:
            rebuilt = augment.screenshot_like(rebuilt, a["seed"])
    assert same(out, rebuilt)


def test_khong_sua_anh_dau_vao():
    img = photo()
    before = img.tobytes()
    augment.apply_random(img, 4, 1.0)
    assert img.tobytes() == before


def test_size_ratio_ghi_vao_ban_ghi_va_info():
    img = photo((96, 96))
    out, applied = augment.apply_random(img, 21, 1.0)
    assert all(
        isinstance(a["size_ratio"], float) and a["size_ratio"] > 0 for a in applied
    )
    assert augment.jpeg_recompress(img, 40).info["size_ratio"] == pytest.approx(
        augment.size_ratio(img, augment.jpeg_recompress(img, 40))
    )
    # ratio của chuỗi là tích gần đúng của ratio từng phép (cùng định nghĩa, chỉ khác sai số mã hóa)
    assert augment.size_ratio(img, out) == pytest.approx(
        np.prod([a["size_ratio"] for a in applied]), rel=0.15
    )


def test_nen_lai_chat_luong_cao_hon_nguon_lam_tang_dung_luong():
    low = augment.jpeg_recompress(photo((96, 96)), 20)  # nguồn đã nén nặng
    high = augment.jpeg_recompress(low, 90)
    assert (
        high.info["size_ratio"] > 1
    )  # nén lại ở chất lượng cao hơn làm tăng dung lượng


def test_nen_lai_bo_exif_va_icc():
    img = photo((64, 64))
    exif = img.getexif()
    exif[271] = "Make"
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", exif=exif.tobytes())
    with Image.open(io.BytesIO(buffer.getvalue())) as src:
        assert 271 in src.getexif()
        out = augment.jpeg_recompress(src, 80)
    assert 271 not in out.getexif() and "icc_profile" not in out.info
