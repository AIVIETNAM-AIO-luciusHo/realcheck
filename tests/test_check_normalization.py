"""scripts.check_normalization sobre du lieu TONG HOP trong tmp_path.

Khong co baseline that trong repo nen chi kiem logic bang thu muc tho, labels,
rejected_small.csv va baseline sha256 tong hop duoc dung bang normalize_image.
"""

import csv
import hashlib

import pytest
from PIL import Image

from models.normalize import normalize_image
from scripts.check_normalization import main


def _write_csv(path, rows, fields):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def world(tmp_path):
    """raw: 2 kept images (genimage + cifake), 1 small rejected."""
    raw = tmp_path / "raw"
    for name, size, color in [
        ("genimage/real/a.png", (300, 280), "red"),
        ("cifake/train/real/b.png", (32, 32), "green"),
        ("genimage/real/small.png", (100, 100), "blue"),
    ]:
        path = raw / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, color).save(path)
    baseline_lines, labels = ["# commit abc, Pillow x"], []
    for name, source, resize in [
        ("genimage/real/a", "genimage_real", True),
        ("cifake/train/real/b", "cifake_real", False),
    ]:
        with Image.open(raw / f"{name}.png") as image:
            jpeg = normalize_image(image, resize=resize).jpeg
        old = f"data/processed/{name}.jpg"
        baseline_lines.append(f"{hashlib.sha256(jpeg).hexdigest()}  {old}")
        labels.append(
            {
                "filepath": old,
                "label": 0,
                "source": source,
                "split": "train",
                "raw_path": f"data/raw/{name}.png",
                "norm_version": "1",
            }
        )
    processed = tmp_path / "processed"
    processed.mkdir()
    _write_csv(tmp_path / "labels.csv", labels, labels[0])
    (tmp_path / "baseline.sha256").write_text("\n".join(baseline_lines) + "\n")
    _write_csv(
        processed / "rejected_small.csv",
        [
            {
                "raw_path": "data/raw/genimage/real/small.png",
                "source": "genimage_real",
                "width": 100,
                "height": 100,
                "reason": "small",
                "norm_version": "1",
            }
        ],
        ["raw_path", "source", "width", "height", "reason", "norm_version"],
    )
    return tmp_path


def _run(world, raw=None):
    return main(
        [
            "--raw-dir",
            str(raw or world / "raw"),
            "--labels",
            str(world / "labels.csv"),
            "--baseline",
            str(world / "baseline.sha256"),
            "--rejected-dir",
            str(world / "processed"),
        ]
    )


def test_consistent_data_exits_zero(world, capsys):
    assert _run(world) == 0
    assert "compared 2" in capsys.readouterr().out


def test_hash_mismatch_exits_nonzero_and_names_image(world, capsys):
    Image.new("RGB", (300, 280), "yellow").save(world / "raw/genimage/real/a.png")
    assert _run(world) == 1
    assert "a.png" in capsys.readouterr().err


def test_missing_raw_dir_exits_nonzero_and_names_path(world, capsys):
    missing = world / "no-such-raw"
    assert _run(world, missing) != 0
    assert str(missing) in capsys.readouterr().err


def test_missing_raw_image_needed_for_comparison_is_reported(world, capsys):
    (world / "raw/cifake/train/real/b.png").unlink()
    assert _run(world) == 1
    err = capsys.readouterr().err
    assert "b.png" in err and "Raw image missing" in err


def test_lost_image_is_reported(world, capsys):
    extra = world / "raw/genimage/real/extra.png"
    Image.new("RGB", (300, 300), "pink").save(extra)
    assert _run(world) == 1
    err = capsys.readouterr().err
    assert "Lost" in err and "extra.png" in err


def test_image_in_labels_and_rejected_is_reported(world, capsys):
    rejected = world / "processed/rejected_small.csv"
    rows = list(csv.DictReader(rejected.open()))
    rows.append({**rows[0], "raw_path": "data/raw/genimage/real/a.png"})
    _write_csv(rejected, rows, rows[0])
    assert _run(world) == 1
    assert "both labels and rejected" in capsys.readouterr().err


def test_duplicate_rejection_record_is_reported(world, capsys):
    rejected = world / "processed/rejected_small.csv"
    rows = list(csv.DictReader(rejected.open()))
    _write_csv(rejected, rows + rows, rows[0])
    assert _run(world) == 1
    assert "more than one rejection" in capsys.readouterr().err


def test_missing_baseline_exits_nonzero_and_names_path(world, capsys):
    (world / "baseline.sha256").unlink()
    assert _run(world) != 0
    assert "baseline.sha256" in capsys.readouterr().err


# ---- hardening: gaps found by independent testing ----


def _append_label(world, name, size, color="orange"):
    raw = world / "raw" / f"{name}.png"
    raw.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(raw)
    rows = list(csv.DictReader((world / "labels.csv").open()))
    rows.append(
        {
            **rows[0],
            "filepath": f"data/processed/{name}.jpg",
            "raw_path": f"data/raw/{name}.png",
        }
    )
    _write_csv(world / "labels.csv", rows, rows[0])


def _add_rejected(world, kind, raw_path, reason="small"):
    path = world / "processed" / f"rejected_{kind}.csv"
    fields = ["raw_path", "source", "width", "height", "reason", "norm_version"]
    rows = list(csv.DictReader(path.open())) if path.exists() else []
    rows.append(
        dict(zip(fields, [raw_path, "genimage_real", 1, 1, reason, "1"], strict=True))
    )
    _write_csv(path, rows, fields)


def test_label_row_without_baseline_line_is_reported(world, capsys):
    _append_label(world, "genimage/real/nobase", (300, 300))
    assert _run(world) == 1
    err = capsys.readouterr().err
    assert "No baseline entry" in err and "nobase" in err


def test_malformed_baseline_line_is_reported_with_number_and_text(world, capsys):
    path = world / "baseline.sha256"
    path.write_text(path.read_text() + "not-a-hash data/processed/x.jpg\n")
    assert _run(world) == 1
    err = capsys.readouterr().err
    assert "line 4" in err and "not-a-hash data/processed/x.jpg" in err


def test_small_image_in_labels_without_record_is_error(world, capsys):
    _append_label(world, "genimage/real/tiny", (100, 100))
    assert _run(world) == 1
    assert "too small" in capsys.readouterr().err


def test_rejected_small_record_for_non_small_image_is_error(world, capsys):
    _add_rejected(world, "small", "data/raw/genimage/real/a.png")
    assert _run(world) == 1
    assert "not small" in capsys.readouterr().err


def test_rejected_record_for_missing_raw_image_is_error(world, capsys):
    _add_rejected(world, "invalid", "data/raw/genimage/real/ghost.png", "bad")
    assert _run(world) == 1
    assert "ghost.png" in capsys.readouterr().err


def test_corrupt_raw_image_is_reported_with_path_and_own_exit_code(world, capsys):
    (world / "raw/genimage/real/a.png").write_bytes(b"not an image")
    assert _run(world) == 3
    assert "a.png" in capsys.readouterr().err


def test_windows_separators_in_raw_path_are_normalized(world):
    rows = list(csv.DictReader((world / "labels.csv").open()))
    rows[0]["raw_path"] = rows[0]["raw_path"].replace("/", "\\")
    _write_csv(world / "labels.csv", rows, rows[0])
    assert _run(world) == 0


def test_nothing_compared_is_error_even_without_other_errors(world, capsys):
    base = world / "baseline.sha256"
    base.write_text(base.read_text().replace("data/processed/", "data/other/"))
    assert _run(world) == 1
    assert "nothing was compared" in capsys.readouterr().err


def test_explicit_rejected_small_path_is_used(world):
    moved = world / "elsewhere.csv"
    (world / "processed/rejected_small.csv").rename(moved)
    argv = [
        "--raw-dir",
        str(world / "raw"),
        "--labels",
        str(world / "labels.csv"),
        "--baseline",
        str(world / "baseline.sha256"),
        "--rejected-dir",
        str(world / "processed"),
        "--rejected-small",
        str(moved),
    ]
    assert main(argv) == 0


def test_rejected_duplicate_file_accounts_for_deduplicated_image(world):
    dup = world / "raw/genimage/real/dup.png"
    Image.new("RGB", (300, 280), "red").save(dup)
    assert _run(world) == 1  # lost without a record
    _add_rejected(world, "duplicate", "data/raw/genimage/real/dup.png", "duplicate")
    assert _run(world) == 0


def test_image_in_labels_and_rejected_duplicate_is_error(world, capsys):
    _add_rejected(world, "duplicate", "data/raw/genimage/real/a.png", "duplicate")
    assert _run(world) == 1
    assert "both labels and rejected" in capsys.readouterr().err


def test_duplicate_kept_record_is_error(world, capsys):
    path = world / "labels.csv"
    rows = list(csv.DictReader(path.open()))
    _write_csv(path, rows + [rows[0]], rows[0])
    assert _run(world) == 1
    assert "more than one label" in capsys.readouterr().err


def test_duplicate_baseline_entry_is_error(world, capsys):
    path = world / "baseline.sha256"
    content = path.read_text()
    path.write_text(content + content.splitlines()[1] + "\n")
    assert _run(world) == 1
    assert "Duplicate baseline" in capsys.readouterr().err


@pytest.mark.parametrize("filename", ["labels.csv", "processed/rejected_small.csv"])
@pytest.mark.parametrize(
    "bad", ["missing_column", "empty_cell", "extra_cell", "short_row", "version"]
)
def test_malformed_csv_is_input_error(world, capsys, filename, bad):
    path = world / filename
    rows = list(csv.DictReader(path.open()))
    if bad == "missing_column":
        for row in rows:
            del row["raw_path"]
    elif bad == "empty_cell":
        rows[0]["raw_path"] = " "
    elif bad == "version":
        rows[0]["norm_version"] = "999"
    _write_csv(path, rows, rows[0])
    if bad == "extra_cell":
        lines = path.read_text().splitlines()
        lines[1] += ",unexpected"
        path.write_text("\n".join(lines) + "\n")
    elif bad == "short_row":
        lines = path.read_text().splitlines()
        lines[1] = lines[1].rsplit(",", 1)[0]
        path.write_text("\n".join(lines) + "\n")
    assert _run(world) == 2
    assert str(path) in capsys.readouterr().err


def test_explicit_missing_optional_rejection_file_is_input_error(world, capsys):
    missing = world / "missing-invalid.csv"
    assert (
        main(
            [
                "--raw-dir",
                str(world / "raw"),
                "--labels",
                str(world / "labels.csv"),
                "--baseline",
                str(world / "baseline.sha256"),
                "--rejected-dir",
                str(world / "processed"),
                "--rejected-invalid",
                str(missing),
            ]
        )
        == 2
    )
    assert str(missing) in capsys.readouterr().err


@pytest.mark.parametrize(
    "raw_path", ["../outside.png", "/outside.png", "C:/outside.png"]
)
def test_raw_path_outside_root_is_input_error(world, capsys, raw_path):
    path = world / "labels.csv"
    rows = list(csv.DictReader(path.open()))
    rows[0]["raw_path"] = raw_path
    _write_csv(path, rows, rows[0])
    assert _run(world) == 2
    assert "raw_path" in capsys.readouterr().err
