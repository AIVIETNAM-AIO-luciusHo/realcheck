"""Sinh ảnh mẫu tổng hợp, tất định, cho scripts/smoke_api.py (KAN-29).

Chạy từ gốc repo:
    python -m scripts.make_fixtures --out .cache/smoke-fixtures

Không dùng dữ liệu thật. Chạy hai lần cho cùng sha256. `.cache/` đã bị gitignore.
"""

import argparse
import io
from pathlib import Path

import numpy as np
from PIL import Image

SEED = 20261105
LIMIT = 5_242_880  # D06: tối đa byte của file
EXIF_MAKE, EXIF_MODEL = "RealCheckCam", "Synthetic-1"


def _photo(width: int, height: int) -> Image.Image:
    """Gradient cộng nhiễu khối thô: nén được, không đơn sắc."""
    rng = np.random.RandomState(SEED)
    x = np.linspace(0, 255, width, dtype=np.float32)[None, :, None]
    y = np.linspace(0, 255, height, dtype=np.float32)[:, None, None]
    base = np.concatenate([x + 0 * y, y + 0 * x, (x + y) / 2], axis=2)
    blocks = rng.randint(-20, 21, size=(height // 50 + 1, width // 50 + 1, 3))
    noise = blocks.repeat(50, 0).repeat(50, 1)[:height, :width]
    return Image.fromarray(np.clip(base + noise, 0, 255).astype(np.uint8), "RGB")


def _jpeg(img: Image.Image, exif: Image.Exif | None = None, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, exif=exif or Image.Exif())
    return buf.getvalue()


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=9)
    return buf.getvalue()


def _multiframe(fmt: str) -> bytes:
    frames = [Image.new("RGB", (300, 300), c) for c in ("red", "blue")]
    buf = io.BytesIO()
    frames[0].save(buf, fmt, save_all=True, append_images=frames[1:], duration=100)
    return buf.getvalue()


def _pad_to(data: bytes, size: int) -> bytes:
    # JPEG hợp lệ + byte 0 sau EOI; Pillow bỏ qua phần đệm cuối file.
    assert len(data) <= size
    return data + b"\0" * (size - len(data))


def build() -> dict[str, bytes]:
    exif = Image.Exif()
    exif[0x010F], exif[0x0110] = EXIF_MAKE, EXIF_MODEL
    big = _photo(4000, 3000)
    rot = Image.Exif()
    rot[0x0112] = 6
    valid_1k = _jpeg(_photo(1024, 1024))
    good = _jpeg(_photo(512, 512))
    return {
        "ok_4000x3000_exif.jpg": _jpeg(big, exif),
        "ok_4000x3000_noexif.jpg": _jpeg(big),
        "ok_orientation6.jpg": _jpeg(_photo(600, 400), rot),
        "ok_valid.png": _png(_photo(512, 384)),
        "ok_256x256.png": _png(_photo(256, 256)),
        "small_200x200.jpg": _jpeg(_photo(200, 200)),
        "small_255x400.jpg": _jpeg(_photo(255, 400)),
        "empty.jpg": b"",
        "fake_text.jpg": "Đây không phải ảnh.\n".encode(),
        "truncated.jpg": good[: len(good) // 2],
        "multiframe.png": _multiframe("PNG"),  # APNG
        "multiframe.gif": _multiframe("GIF"),
        "limit_5242880.jpg": _pad_to(valid_1k, LIMIT),
        "over_5242881.jpg": _pad_to(valid_1k, LIMIT + 1),
        # Đơn sắc nên file nhỏ dù 36 MP / cạnh 10001 (D07: 24 MP, cạnh 10000).
        "many_pixels_6000x6000.png": _png(Image.new("L", (6000, 6000), 128)),
        "many_side_10001x300.png": _png(Image.new("L", (10001, 300), 128)),
    }


def generate(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, data in build().items():
        paths.append(out / name)
        paths[-1].write_bytes(data)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path(".cache/smoke-fixtures"))
    args = parser.parse_args(argv)
    for path in generate(args.out):
        print(f"{path.stat().st_size:>10}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
