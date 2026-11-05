"""Fixture của scripts/make_fixtures.py: thuộc tính đúng và sinh tất định."""

import hashlib
import io

import pytest
from PIL import Image

from scripts import make_fixtures
from scripts.smoke_api import FIXTURE_FILES


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    out = tmp_path_factory.mktemp("fx")
    make_fixtures.generate(out)
    return out


def _open(fx, name):
    return Image.open(fx / name)


def test_covers_every_file_smoke_api_needs(fx):
    assert {p.name for p in fx.iterdir()} >= set(FIXTURE_FILES) | {"ok_valid.png"}


@pytest.mark.parametrize(
    ("name", "size"),
    [
        ("ok_4000x3000_exif.jpg", (4000, 3000)),
        ("ok_4000x3000_noexif.jpg", (4000, 3000)),
        ("small_200x200.jpg", (200, 200)),
        ("small_255x400.jpg", (255, 400)),
        ("ok_256x256.png", (256, 256)),
        ("many_pixels_6000x6000.png", (6000, 6000)),
        ("many_side_10001x300.png", (10001, 300)),
    ],
)
def test_dimensions(fx, name, size):
    assert _open(fx, name).size == size


def test_big_jpegs_stay_under_size_limit(fx):
    for name in ("ok_4000x3000_exif.jpg", "ok_4000x3000_noexif.jpg"):
        assert (fx / name).stat().st_size < make_fixtures.LIMIT


def test_exif_present_and_absent(fx):
    exif = _open(fx, "ok_4000x3000_exif.jpg").getexif()
    assert (exif[0x010F], exif[0x0110]) == ("RealCheckCam", "Synthetic-1")
    assert not _open(fx, "ok_4000x3000_noexif.jpg").getexif()


def test_orientation_6(fx):
    assert _open(fx, "ok_orientation6.jpg").getexif()[0x0112] == 6


def test_empty_and_fake_text(fx):
    assert (fx / "empty.jpg").stat().st_size == 0
    with pytest.raises(OSError, match="cannot identify"):
        _open(fx, "fake_text.jpg")


def test_truncated_jpeg_fails_on_load(fx):
    with pytest.raises(OSError, match="image file is truncated"):
        _open(fx, "truncated.jpg").load()


@pytest.mark.parametrize("name", ["multiframe.png", "multiframe.gif"])
def test_multiframe(fx, name):
    assert _open(fx, name).n_frames == 2


def test_exact_limit_bytes_and_still_valid(fx):
    at, over = fx / "limit_5242880.jpg", fx / "over_5242881.jpg"
    assert at.stat().st_size == 5_242_880
    assert over.stat().st_size == 5_242_881
    for path in (at, over):
        with Image.open(io.BytesIO(path.read_bytes())) as img:
            img.load()
            assert img.format == "JPEG"


def test_deterministic_sha256(fx, tmp_path):
    make_fixtures.generate(tmp_path)

    def digests(d):
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in d.iterdir()}

    assert digests(tmp_path) == digests(fx)
