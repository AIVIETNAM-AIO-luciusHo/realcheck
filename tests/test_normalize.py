"""T006: hop dong cua models.normalize.normalize_image (anh tong hop Pillow)."""

import hashlib
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps

from models.normalize import NORMALIZATION_VERSION, normalize_image

PINNED_SHA256 = "b012e84998568148075b27ae77637987123ec386fde9e64d150f92955350e3fe"


def _photo(size=(400, 300)) -> Image.Image:
    pixels = np.arange(size[1] * size[0] * 3, dtype=np.uint32).reshape(*size[::-1], 3)
    return Image.fromarray((pixels % 251).astype("uint8"))


def test_image_equals_decoded_jpeg_pixels():
    result = normalize_image(_photo())
    with Image.open(BytesIO(result.jpeg)) as decoded:
        np.testing.assert_array_equal(np.asarray(result.image), np.asarray(decoded))
    assert result.image.size == (256, 256) and result.image.mode == "RGB"
    assert result.version == NORMALIZATION_VERSION


def test_jpeg_matches_legacy_pillow_recipe():
    # Legacy recipe rewritten from the old prepare_data docstring, on synthetic pixels.
    # It is NOT a substitute for the real-baseline check (scripts.check_normalization).
    photo = _photo()
    legacy = ImageOps.fit(photo.convert("RGB"), (256, 256), Image.Resampling.BICUBIC)
    buffer = BytesIO()
    legacy.save(buffer, "JPEG", quality=95)
    assert normalize_image(photo).jpeg == buffer.getvalue()


def test_same_bytes_in_same_jpeg_out():
    buffer = BytesIO()
    _photo().save(buffer, "PNG")
    outputs = []
    for _ in range(2):
        with Image.open(BytesIO(buffer.getvalue())) as image:
            outputs.append(normalize_image(image).jpeg)
    assert outputs[0] == outputs[1]


def test_parameters_pinned_by_fingerprint_next_to_version():
    # Changing size, filter or quality changes this hash and must bump the version.
    # The hash depends on the Pillow version pinned in requirements.txt.
    jpeg = normalize_image(_photo()).jpeg
    assert NORMALIZATION_VERSION == "1"
    assert hashlib.sha256(jpeg).hexdigest() == PINNED_SHA256


def test_input_image_is_not_mutated():
    photo = _photo()
    before = photo.tobytes()
    normalize_image(photo)
    assert photo.size == (400, 300) and photo.tobytes() == before
