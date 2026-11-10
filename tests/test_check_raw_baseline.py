"""scripts.check_raw_baseline (T013) tren du lieu TONG HOP; chua thay lan chay raw that.

Anh co nhieu ngau nhien tat dinh (seed = ten anh), EXIF Orientation 6, CMYK, palette
va bien canh ngan 255/256 de test bat duoc loi o tung buoc cong thuc, khong chi mau phang.
"""

import csv
import hashlib
import random
from io import BytesIO

import PIL
import pytest
from PIL import Image, ImageOps

from scripts.check_raw_baseline import main

# (ten, ext, kich thuoc, kieu)
IMAGES = [
    ("genimage/real/a", "png", (300, 280), "rgb"),
    ("genimage/real/rot", "jpg", (300, 280), "exif6"),  # exif_transpose phai doi anh
    ("genimage/real/cmyk", "tiff", (310, 290), "cmyk"),  # convert RGB phai chay
    ("genimage/real/pal", "png", (290, 300), "palette"),
    ("genimage/real/small", "png", (100, 120), "rgb"),  # code cu phong to len 256
    ("genimage/real/edge255", "png", (255, 300), "rgb"),  # nho: bi loai
    ("genimage/real/edge256", "png", (256, 300), "rgb"),  # du lon: phai giu
    ("cifake/train/real/b", "png", (32, 32), "rgb"),
]
SMALL = ["genimage/real/small.png", "genimage/real/edge255.png"]
FIELDS = ["raw_path", "source", "width", "height", "reason", "norm_version"]


def _make(path, name, size, kind):
    rng = random.Random(name)
    w, h = size
    if kind == "cmyk":
        Image.frombytes("CMYK", size, rng.randbytes(w * h * 4)).save(path)
        return
    image = Image.frombytes("RGB", size, rng.randbytes(w * h * 3))
    if kind == "palette":
        image = image.convert("P", palette=Image.Palette.ADAPTIVE, colors=64)
    if kind == "exif6":
        exif = Image.Exif()
        exif[0x0112] = 6
        image.save(path, exif=exif)
    else:
        image.save(path)


def _jpeg(path, resize):  # viet lai cong thuc cu, doc lap voi script
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        if resize:
            im = ImageOps.fit(im, (256, 256), Image.Resampling.BICUBIC)
        out = BytesIO()
        im.save(out, "JPEG", quality=95)
        return out.getvalue()


def _csv(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def _relabel(world, **changes):
    """Ghi lai labels.csv va cap nhat sha trong header baseline (de chi test 1 loi)."""
    rows = [{**r, **changes} for r in csv.DictReader((world / "labels.csv").open())]
    _csv(world / "labels.csv", rows)
    sha = hashlib.sha256((world / "labels.csv").read_bytes()).hexdigest()
    base = world / "baseline.sha256"
    lines = [
        f"# labels_csv_sha256: {sha}" if x.startswith("# labels_csv") else x
        for x in base.read_text().splitlines()
    ]
    base.write_text("\n".join(lines) + "\n")


@pytest.fixture
def world(tmp_path):
    raw, labels, lines = tmp_path / "raw", [], []
    for name, ext, size, kind in IMAGES:
        path = raw / f"{name}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        _make(path, name, size, kind)
        old = f"data/processed/{name}.jpg"
        digest = hashlib.sha256(_jpeg(path, name.startswith("genimage"))).hexdigest()
        lines.append(f"{digest}  {old}")
        labels.append(
            {
                "filepath": old,
                "label": 0,
                "source": "s",
                "split": "train",
                "raw_path": f"data/raw/{name}.{ext}",
                "norm_version": "1",
            }
        )
    _csv(tmp_path / "labels.csv", labels)
    sha = hashlib.sha256((tmp_path / "labels.csv").read_bytes()).hexdigest()
    head = [
        "# prepare_data_commit: " + "a" * 40,
        f"# pillow: {PIL.__version__}",
        f"# labels_csv_sha256: {sha}",
    ]
    (tmp_path / "baseline.sha256").write_text("\n".join(head + lines) + "\n")
    _csv(
        tmp_path / "rejected_small.csv",
        [
            dict(zip(FIELDS, [f"data/raw/{p}", "s", 1, 1, "small", "1"], strict=True))
            for p in SMALL
        ],
    )
    return tmp_path


def _run(w, small=True, raw=None):
    argv = [
        "--raw-dir",
        str(raw or w / "raw"),
        "--labels",
        str(w / "labels.csv"),
        "--baseline",
        str(w / "baseline.sha256"),
    ]
    if small:
        argv += ["--rejected-small", str(w / "rejected_small.csv")]
    return main(argv)


def _rejected(world):
    return list(csv.DictReader((world / "rejected_small.csv").open()))


def test_consistent_world_passes_and_reports_counts(world, capsys):
    assert _run(world) == 0
    out = capsys.readouterr().out
    assert "OK 8, FAILED 0, missing 0, of 8" in out
    assert "Small (<256px, upscaled by legacy code): 2" in out


@pytest.mark.parametrize("name", ["a.png", "rot.jpg", "cmyk.tiff", "pal.png"])
def test_sha_mismatch_is_caught_for_each_image_kind(world, capsys, name):
    path = world / "raw/genimage/real" / name
    _make(
        path, "other", Image.open(path).size, "rgb" if name != "cmyk.tiff" else "cmyk"
    )
    assert _run(world) == 1
    captured = capsys.readouterr()
    assert "FAILED 1" in captured.out and name in captured.err


def test_edge_256_is_kept_and_255_is_small(world):
    # 256 trong labels, khong trong rejected: dung. Day 256 vao rejected: sai.
    rows = _rejected(world) + [
        dict(
            zip(
                FIELDS,
                ["data/raw/genimage/real/edge256.png", "s", 1, 1, "x", "1"],
                strict=True,
            )
        )
    ]
    _csv(world / "rejected_small.csv", rows)
    assert _run(world) == 1


def test_edge_255_missing_from_rejected_is_caught(world, capsys):
    _csv(world / "rejected_small.csv", _rejected(world)[:1])  # chi con 'small'
    assert _run(world) == 1
    assert "edge255.png" in capsys.readouterr().err


def test_small_image_not_rejected_is_caught(world, capsys):
    rows = [{**_rejected(world)[0], "raw_path": "data/raw/genimage/real/a.png"}]
    _csv(world / "rejected_small.csv", rows)
    assert _run(world) == 1
    err = capsys.readouterr().err
    assert "not in rejected_small" in err and "not small" in err


def test_wrong_normalization_version_in_rejected_is_caught(world, capsys):
    _csv(
        world / "rejected_small.csv",
        [{**r, "norm_version": "2"} for r in _rejected(world)],
    )
    assert _run(world) == 1
    assert "rejected_small norm_version '2'" in capsys.readouterr().err


def test_wrong_normalization_version_in_labels_is_caught(world, capsys):
    _relabel(world, norm_version="2")
    assert _run(world) == 1
    assert "labels norm_version '2'" in capsys.readouterr().err


def test_missing_raw_file_is_counted_and_fails(world, capsys):
    (world / "raw/cifake/train/real/b.png").unlink()
    assert _run(world) == 1
    captured = capsys.readouterr()
    assert "missing 1" in captured.out and "b.png" in captured.err


def test_missing_raw_dir_exits_2_with_guide(world, capsys):
    assert _run(world, raw=world / "nope") == 2
    err = capsys.readouterr().err
    assert str(world / "nope") in err and "git archive" in err


def test_labels_changed_after_baseline_is_caught(world, capsys):
    path = world / "labels.csv"
    path.write_text(path.read_text().replace("train", "val"))
    assert _run(world) == 1
    assert "labels.csv" in capsys.readouterr().err


def test_baseline_labels_row_count_mismatch_is_caught(world, capsys):
    base = world / "baseline.sha256"
    base.write_text(base.read_text() + "0" * 64 + "  data/processed/extra.jpg\n")
    assert _run(world) == 1
    assert "differ" in capsys.readouterr().err


def test_baseline_header_missing_fields_is_caught(world, capsys):
    path = world / "baseline.sha256"
    path.write_text(path.read_text().replace("# pillow", "# x"))
    assert _run(world) == 1
    assert "lacks 'pillow'" in capsys.readouterr().err


def test_corrupt_raw_exits_3(world):
    (world / "raw/genimage/real/a.png").write_bytes(b"junk")
    assert _run(world) == 3


def test_without_rejected_small_warns_loudly_and_skips_small_check(world, capsys):
    assert _run(world, small=False) == 0
    err = capsys.readouterr().err
    assert "WARNING" in err and "--rejected-small" in err and "KHONG kiem" in err


def test_with_rejected_small_no_skip_warning(world, capsys):
    assert _run(world) == 0
    assert "KHONG kiem" not in capsys.readouterr().err


def test_pillow_warning_repeated_next_to_failed_line(world, capsys):
    base = world / "baseline.sha256"
    base.write_text(
        base.read_text().replace(f"# pillow: {PIL.__version__}", "# pillow: 0.0.1")
    )
    _make(world / "raw/genimage/real/a.png", "other", (300, 280), "rgb")
    assert _run(world) == 1
    out = capsys.readouterr().out
    assert "FAILED 1" in out and "Pillow" in out and "0.0.1" in out


def test_pillow_difference_alone_is_only_a_warning(world, capsys):
    base = world / "baseline.sha256"
    base.write_text(
        base.read_text().replace(f"# pillow: {PIL.__version__}", "# pillow: 0.0.1")
    )
    assert _run(world) == 0
    assert "Pillow" in capsys.readouterr().err
