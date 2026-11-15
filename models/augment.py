"""Tăng cường ảnh tất định theo seed cho thí nghiệm ADV-12 (#144). THỬ NGHIỆM, không dùng cho model phục vụ.

Không sửa `normalize_image` hay đường train hiện tại: các hàm ở đây nhận và trả `PIL.Image` RGB cùng kích thước,
rồi người dùng tự đưa qua `normalize_image` như mọi ảnh khác. Cùng ảnh, cùng tham số và cùng seed thì cùng pixel
(trên cùng phiên bản Pillow). `apply_random` trả kèm danh sách phép đã áp dụng để ghi vào manifest.
"""

from io import BytesIO

import numpy as np
from PIL import Image

SCREENSHOT_RESAMPLES = (
    Image.Resampling.BILINEAR,
    Image.Resampling.BICUBIC,
    Image.Resampling.LANCZOS,
)


def encode_jpeg(image: Image.Image, quality: int) -> bytes:
    """JPEG bytes của ảnh (RGB) ở chất lượng 1 đến 100."""
    if (
        not isinstance(quality, int)
        or isinstance(quality, bool)
        or not 1 <= quality <= 100
    ):
        raise ValueError("quality phải là số nguyên trong [1, 100]")
    with BytesIO() as buffer:
        image.convert("RGB").save(buffer, "JPEG", quality=quality)
        return buffer.getvalue()


def size_ratio(before: Image.Image, after: Image.Image) -> float:
    """Dung lượng JPEG chất lượng 95 (như `normalize_image`) của `after` chia cho của `before`.

    Đo dung lượng sau chuẩn hóa, thứ có thể thành shortcut: nén lại ở chất lượng thấp thường làm nhỏ đi, nhưng nén lại
    ở chất lượng cao hơn nguồn (hoặc một ảnh đã nén nặng) có thể làm TĂNG dung lượng (tỉ lệ > 1).
    """
    return len(encode_jpeg(after, 95)) / len(encode_jpeg(before, 95))


def jpeg_recompress(image: Image.Image, quality: int) -> Image.Image:
    """Nén lại một lần ở `quality`; trả ảnh đã giải mã (giữ `.quantization`, thêm `.info["size_ratio"]`).

    Nén lại có thể làm tăng dung lượng; EXIF và ICC của ảnh gốc bị bỏ (chuyển RGB, không giữ metadata).
    """
    decoded = Image.open(BytesIO(encode_jpeg(image, quality)))
    decoded.load()
    decoded.info["size_ratio"] = size_ratio(image, decoded)
    return decoded


def downscale_upscale(image: Image.Image, factor: float) -> Image.Image:
    """Thu nhỏ theo `factor` trong (0, 1] bằng BILINEAR rồi phóng lại kích thước gốc bằng BICUBIC."""
    if not 0 < factor <= 1:
        raise ValueError("factor phải trong (0, 1]")
    rgb = image.convert("RGB")
    width, height = rgb.size
    small = rgb.resize(
        (max(1, round(width * factor)), max(1, round(height * factor))),
        Image.Resampling.BILINEAR,
    )
    return small.resize(rgb.size, Image.Resampling.BICUBIC)


def screenshot_like(image: Image.Image, seed: int) -> Image.Image:
    """Giả ảnh chụp màn hình/chia sẻ lại: lấy mẫu lại, làm tròn màu (5 hoặc 6 bit mỗi kênh), nén JPEG chất lượng 60 đến 90."""
    rng = np.random.default_rng(seed)
    scale = float(rng.uniform(0.5, 0.9))
    resample = SCREENSHOT_RESAMPLES[int(rng.integers(len(SCREENSHOT_RESAMPLES)))]
    bits = int(rng.integers(5, 7))
    quality = int(rng.integers(60, 91))
    rgb = image.convert("RGB")
    small = rgb.resize(
        (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))), resample
    )
    resized = small.resize(rgb.size, resample)
    shift = 8 - bits
    pixels = np.asarray(resized, dtype=np.uint8)
    rounded = ((pixels >> shift) << shift) | (1 << (shift - 1))  # lấy giữa mỗi mức
    return jpeg_recompress(Image.fromarray(rounded.astype(np.uint8), "RGB"), quality)


def apply_random(
    image: Image.Image, seed: int, p: float = 0.5
) -> tuple[Image.Image, list[dict]]:
    """Áp từng phép (theo thứ tự cố định) với xác suất `p`; trả (ảnh, danh sách phép và tham số đã áp dụng).

    Danh sách dạng `[{"op": "jpeg_recompress", "quality": 55, "size_ratio": 0.8}, ...]`, đủ để ghi vào manifest và
    dựng lại ảnh; `size_ratio` là tỉ lệ dung lượng (sau chuẩn hóa JPEG 95) của ảnh sau phép so với trước phép
    (xem `size_ratio`): > 1 nghĩa là phép làm tăng dung lượng.
    """
    if not 0 <= p <= 1:
        raise ValueError("p phải trong [0, 1]")
    rng = np.random.default_rng(seed)
    out, applied = image.convert("RGB"), []
    if rng.random() < p:
        quality = int(rng.integers(30, 91))
        before, out = out, jpeg_recompress(out, quality)
        applied.append(
            {
                "op": "jpeg_recompress",
                "quality": quality,
                "size_ratio": out.info["size_ratio"],
            }
        )
    if rng.random() < p:
        factor = float(rng.choice([0.5, 0.67, 0.75]))
        before, out = out, downscale_upscale(out, factor)
        applied.append(
            {
                "op": "downscale_upscale",
                "factor": factor,
                "size_ratio": size_ratio(before, out),
            }
        )
    if rng.random() < p:
        sub = int(rng.integers(2**31))
        before, out = out, screenshot_like(out, sub)
        applied.append(
            {
                "op": "screenshot_like",
                "seed": sub,
                "size_ratio": size_ratio(before, out),
            }
        )
    return out, applied
