"""T020: nguong 256 px, ngoai le resize=False, khong bao gio phong to."""

import pytest
from PIL import Image

from models.normalize import ImageTooSmall, normalize_image


@pytest.mark.parametrize("size", [(255, 600), (600, 255), (255, 255), (1, 1)])
def test_short_side_below_256_raises_with_original_size(size):
    with pytest.raises(ImageTooSmall) as error:
        normalize_image(Image.new("RGB", size))
    assert (error.value.width, error.value.height) == size
    assert "256" in str(error.value)


@pytest.mark.parametrize("size", [(256, 256), (256, 900), (900, 256)])
def test_short_side_of_256_passes_without_upscaling(size):
    result = normalize_image(Image.new("RGB", size, "teal"))
    assert result.image.size == (256, 256)


def test_resize_false_keeps_32x32_and_is_not_rejected():
    result = normalize_image(Image.new("RGB", (32, 32), "red"), resize=False)
    assert result.image.size == (32, 32)
    assert result.jpeg[:2] == b"\xff\xd8"


def test_resize_false_never_resizes_larger_images_either():
    assert normalize_image(Image.new("RGB", (300, 200)), resize=False).image.size == (
        300,
        200,
    )


def test_rejection_does_not_modify_input():
    image = Image.new("RGB", (100, 100), "red")
    with pytest.raises(ImageTooSmall):
        normalize_image(image)
    assert image.size == (100, 100)
