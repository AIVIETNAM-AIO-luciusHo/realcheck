"""T018: anh lon, bang luong tu JPEG q95, JPEG dung mot lan, EXIF orientation."""

from io import BytesIO

import pytest
from PIL import Image

from models.normalize import ImageTooSmall, normalize_image


def test_phone_photo_4000x3000_becomes_256_square():
    result = normalize_image(Image.new("RGB", (4000, 3000), (10, 120, 200)))
    assert result.image.size == (256, 256)


def test_quantization_tables_match_jpeg_quality_95_not_other_qualities():
    def tables(quality):
        buffer = BytesIO()
        Image.new("RGB", (256, 256), "gray").save(buffer, "JPEG", quality=quality)
        with Image.open(BytesIO(buffer.getvalue())) as decoded:
            return decoded.quantization

    with Image.open(BytesIO(normalize_image(Image.new("RGB", (300, 300))).jpeg)) as out:
        actual = out.quantization
    assert actual[0][0] == 2  # libjpeg luminance DC step at quality 95
    assert actual == tables(95)
    assert actual != tables(90) and actual != tables(100)


def test_jpeg_is_encoded_exactly_once(monkeypatch):
    original, formats = Image.Image.save, []

    def spy(self, fp, format=None, **params):
        formats.append(format)
        return original(self, fp, format, **params)

    monkeypatch.setattr(Image.Image, "save", spy)
    normalize_image(Image.new("RGB", (800, 600)))
    assert formats == ["JPEG"]


def _oriented(orientation, size):
    # Stored image: left half red, right half blue.
    image = Image.new("RGB", size, "blue")
    image.paste("red", (0, 0, size[0] // 2, size[1]))
    image.getexif()[274] = orientation
    return image


def test_exif_orientation_6_is_rotated_before_resize_and_source_untouched():
    source = _oriented(6, (500, 300))
    pixels = normalize_image(source).image
    # Rotating 90 degrees clockwise puts the stored left (red) half on top.
    top, bottom = pixels.getpixel((128, 20)), pixels.getpixel((128, 235))
    assert top[0] > 200 and top[2] < 60
    assert bottom[2] > 200 and bottom[0] < 60
    assert source.size == (500, 300) and source.getexif()[274] == 6


def test_orientation_1_is_not_rotated():
    pixels = normalize_image(_oriented(1, (500, 300))).image
    assert pixels.getpixel((20, 128))[0] > 200
    assert pixels.getpixel((235, 128))[2] > 200


def test_short_side_is_measured_in_stored_dimensions_after_rotation_too():
    with pytest.raises(ImageTooSmall) as error:
        normalize_image(_oriented(6, (255, 1000)))
    assert (error.value.width, error.value.height) == (255, 1000)
