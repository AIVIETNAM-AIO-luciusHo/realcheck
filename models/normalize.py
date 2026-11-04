"""Versioned image normalization shared by data preparation and inference."""

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

NORMALIZATION_VERSION = "1"
MIN_SIDE = 256


class ImageTooSmall(ValueError):
    """The original image cannot be normalized without upscaling."""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        super().__init__(f"Image {width}x{height}: minimum short side is {MIN_SIDE}px")


@dataclass(frozen=True)
class NormalizedImage:
    jpeg: bytes
    image: Image.Image
    version: str


def normalize_image(image: Image.Image, resize: bool = True) -> NormalizedImage:
    """Return one JPEG encode and its decoded pixels; never mutate the input.

    ``resize=False`` is exclusively for CIFAKE data preparation, not serving.
    ImageTooSmall preserves the original dimensions for the rejection report.
    """
    if resize and min(image.size) < MIN_SIDE:
        raise ImageTooSmall(*image.size)
    normalized = ImageOps.exif_transpose(image).convert("RGB")
    if resize:
        normalized = ImageOps.fit(
            normalized, (MIN_SIDE, MIN_SIDE), Image.Resampling.BICUBIC
        )
    with BytesIO() as buffer:
        normalized.save(buffer, "JPEG", quality=95)
        jpeg = buffer.getvalue()
    with Image.open(BytesIO(jpeg)) as decoded:
        pixels = decoded.copy()
    return NormalizedImage(jpeg, pixels, NORMALIZATION_VERSION)
