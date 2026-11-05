"""Exercise data CLIs with synthetic files, including real process-pool workers."""

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from models.normalize import NORMALIZATION_VERSION
from scripts import check_data, check_normalization, prepare_data

ROOT = Path(__file__).resolve().parents[1]


def cli(module, *args):
    return subprocess.run(
        [sys.executable, "-m", module, *map(str, args)],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def save_noise(path, size, seed):
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.random.default_rng(seed).integers(
        0, 256, (size[1], size[0], 3), dtype=np.uint8
    )
    Image.fromarray(pixels).save(path)


def test_prepare_and_check_data_cli_rejections_splits_and_overwrite(tmp_path):
    raw, output, labels = (
        tmp_path / "raw",
        tmp_path / "processed",
        tmp_path / "labels.csv",
    )
    for label, source in enumerate(("real", "sd14")):
        for n in range(10):
            save_noise(
                raw / "genimage" / source / f"{n}.png", (300, 280), label * 10 + n
            )
    for split_index, split in enumerate(("train", "test")):
        for label, source in enumerate(("real", "ai")):
            for n in range(2):
                save_noise(
                    raw / "cifake" / split / source / f"{n}.png",
                    (32, 32),
                    30 + split_index * 4 + label * 2 + n,
                )
    small = raw / "genimage/real/small.png"
    save_noise(small, (255, 300), 100)
    invalid = raw / "genimage/sd14/corrupt.png"
    invalid.write_bytes(b"not an image")
    args = (
        "--raw-dir",
        raw,
        "--output-dir",
        output,
        "--labels",
        labels,
        "--workers",
        1,
    )
    result = cli("scripts.prepare_data", *args)
    assert result.returncode == 0, result.stdout + result.stderr
    df = pd.read_csv(labels, dtype={"norm_version": str})
    assert len(df) == 28 and df.norm_version.eq(NORMALIZATION_VERSION).all()
    genimage = df[df.source.str.startswith("genimage_")]
    assert genimage.groupby("split").size().to_dict() == {
        "train": 14,
        "val": 4,
        "test": 2,
    }
    original_test = df[df.raw_path.str.contains("cifake/test", regex=False)]
    assert len(original_test) == 4 and original_test.split.eq("test").all()
    rejected_small = pd.read_csv(output / "rejected_small.csv")
    rejected_invalid = pd.read_csv(output / "rejected_invalid.csv")
    assert rejected_small.raw_path.tolist() == [small.as_posix()]
    assert rejected_invalid.raw_path.tolist() == [invalid.as_posix()]
    assert rejected_small.iloc[0][["width", "height"]].tolist() == [255, 300]
    assert not (output / "genimage/real/small.jpg").exists()
    assert not (output / "genimage/sd14/corrupt.jpg").exists()
    accepted = set(df.raw_path)
    rejected = set(rejected_small.raw_path) | set(rejected_invalid.raw_path)
    assert accepted.isdisjoint(rejected)
    assert accepted | rejected == {p.as_posix() for p in raw.rglob("*.png")}
    checked = cli("scripts.check_data", "--labels", labels)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    before = labels.read_bytes()
    refused = cli("scripts.prepare_data", *args)
    assert refused.returncode != 0 and "Output already exists" in refused.stderr
    assert labels.read_bytes() == before
    # A corrupt processed file must be a reported failure, not an uncaught traceback.
    Path(df.iloc[0].filepath).write_bytes(b"corrupt processed jpeg")
    checked = cli("scripts.check_data", "--labels", labels)
    assert checked.returncode == 1 and "FAIL" in checked.stdout
    assert "Traceback" not in checked.stderr


def test_prepare_records_decompression_bomb_separately(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    path = raw / "genimage/real/bomb.png"
    save_noise(path, (300, 280), 1)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    output = tmp_path / "processed"
    result = prepare_data.process_one((str(path), str(raw), str(output)))
    assert result["rejection"] == "invalid"
    assert "DecompressionBombError" in result["reason"]
    assert not output.exists()


def test_prepare_does_not_hide_output_io_failure(tmp_path, monkeypatch):
    raw = tmp_path / "raw"
    path = raw / "genimage/real/good.png"
    save_noise(path, (300, 280), 1)

    def fail_write(self, data):
        raise PermissionError("output is read-only")

    monkeypatch.setattr(Path, "write_bytes", fail_write)
    with pytest.raises(PermissionError, match="read-only"):
        prepare_data.process_one((str(path), str(raw), str(tmp_path / "processed")))


def test_prepare_duplicate_hashes_remove_conflicting_labels():
    df = pd.DataFrame(
        {"hash": ["same", "same", "mixed", "mixed", "unique"], "label": [0, 0, 0, 1, 1]}
    )
    kept = prepare_data.drop_duplicates(df)
    assert kept.index.tolist() == [0, 4]


def test_prepare_records_duplicates_and_leaves_no_lost_image(tmp_path):
    raw, output, labels = (
        tmp_path / "raw",
        tmp_path / "processed",
        tmp_path / "labels.csv",
    )
    real, sd14 = raw / "genimage/real", raw / "genimage/sd14"
    for source, offset in ((real, 0), (sd14, 10)):
        for n in range(4):
            save_noise(source / f"{n}.png", (300, 280), offset + n)
    # Trùng cùng nhãn (giữ a_first.png), và cùng ảnh mang hai nhãn (bỏ cả hai)
    save_noise(real / "a_first.png", (300, 280), 50)
    save_noise(real / "b_copy.png", (300, 280), 50)
    save_noise(real / "conflict.png", (320, 290), 60)
    save_noise(sd14 / "conflict.png", (320, 290), 60)
    result = cli(
        "scripts.prepare_data",
        *("--raw-dir", raw, "--output-dir", output, "--labels", labels),
        *("--workers", 1),
    )
    assert result.returncode == 0, result.stdout + result.stderr

    records = pd.read_csv(output / "rejected_duplicate.csv")
    assert records.columns.tolist() == prepare_data.REJECTED_COLUMNS
    reasons = dict(zip(records.raw_path, records.reason))
    first, copy = (real / "a_first.png").as_posix(), (real / "b_copy.png").as_posix()
    assert first in reasons[copy]
    for image in (real / "conflict.png", sd14 / "conflict.png"):
        assert "different label" in reasons[image.as_posix()]
    assert len(reasons) == 3
    assert records[["width", "height"]].drop_duplicates().shape[0] == 2
    assert records.norm_version.astype(str).eq(NORMALIZATION_VERSION).all()

    df = pd.read_csv(labels, dtype={"norm_version": str})
    assert first in set(df.raw_path) and set(df.raw_path).isdisjoint(reasons)
    assert all(Path(path).is_file() for path in df.filepath)
    assert not (output / "genimage/real/b_copy.jpg").exists()
    assert not (output / "genimage/real/conflict.jpg").exists()
    assert not (output / "genimage/sd14/conflict.jpg").exists()

    rejected = records.astype(str).to_dict("records")
    rows = df.astype(str).to_dict("records")
    assert check_normalization.check_inventory(rows, rejected, raw) == []
    # Chứng minh checker bắt lỗi nếu thiếu bản ghi, tức lỗi cũ sẽ bị phát hiện
    errors = check_normalization.check_inventory(rows, [], raw)
    assert sum(error.startswith("Lost") for error in errors) == 3


def test_prepare_writes_empty_duplicate_file_when_no_duplicates(tmp_path):
    raw, output = tmp_path / "raw", tmp_path / "processed"
    for source, offset in (("real", 0), ("sd14", 10)):
        for n in range(3):
            save_noise(raw / "genimage" / source / f"{n}.png", (300, 280), offset + n)
    result = cli(
        "scripts.prepare_data",
        *("--raw-dir", raw, "--output-dir", output),
        *("--labels", tmp_path / "labels.csv", "--workers", 1),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    records = pd.read_csv(output / "rejected_duplicate.csv")
    assert records.empty and records.columns.tolist() == prepare_data.REJECTED_COLUMNS


@pytest.mark.parametrize("norm_version", [None, "old", ""])
def test_check_data_cli_requires_current_norm_version(tmp_path, norm_version):
    row = {
        "filepath": "missing.jpg",
        "label": 0,
        "source": "genimage_real",
        "split": "train",
        "raw_path": "missing.png",
    }
    if norm_version is not None:
        row["norm_version"] = norm_version
    labels = tmp_path / "labels.csv"
    pd.DataFrame([row]).to_csv(labels, index=False)
    result = cli("scripts.check_data", "--labels", labels)
    assert result.returncode == 1
    assert "norm_version" in result.stdout
    assert "Traceback" not in result.stderr


def test_check_images_reports_decompression_bomb(tmp_path, monkeypatch):
    path = tmp_path / "bomb.png"
    save_noise(path, (300, 280), 1)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 1)
    monkeypatch.setattr(check_data, "failures", [])
    hashes = check_data.check_images(
        pd.DataFrame([{"filepath": str(path), "source": "genimage_real"}])
    )
    assert hashes == [None]
    assert check_data.failures
