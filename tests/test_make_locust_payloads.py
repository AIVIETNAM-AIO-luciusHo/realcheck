"""Payload #123: provenance, original bytes, reproducibility and Locust compatibility."""

import csv
import hashlib
import json
import os
import random
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from scripts import make_locust_payloads as payload


def test_cli_help_on_windows_encoding():
    run = subprocess.run(
        [sys.executable, "-m", "scripts.make_locust_payloads", "--help"],
        env=os.environ | {"PYTHONIOENCODING": "cp1252"},
        capture_output=True,
        check=True,
    )
    assert "Đóng gói" in run.stdout.decode("utf-8")


def write_labels(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=sorted(payload.REQUIRED), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def dataset(tmp_path, counts):
    root = tmp_path / "raw"
    rows = []
    for source, count in counts.items():
        fmt, _, label = payload.QUOTAS[source]
        name = source.removeprefix("genimage_")
        for index in range(count):
            relative = f"genimage/{name}/{index}.{'jpg' if fmt == 'JPEG' else 'png'}"
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            width = 256 + 16 * (index % 4)
            pixels = random.Random(f"{source}/{index}").randbytes(width * 256 * 3)
            Image.frombytes("RGB", (width, 256), pixels).save(target, fmt)
            rows.append(
                {
                    "filepath": f"data/processed/genimage/{name}/{index}.jpg",
                    "raw_path": f"data/raw/{relative}",
                    "source": source,
                    "label": label,
                    "split": "train",
                    "norm_version": "1",
                    "group_id": f"{source}-{index}",
                }
            )
    labels = tmp_path / "labels.csv"
    write_labels(labels, rows)
    return labels, root, rows


@pytest.fixture
def small(tmp_path, monkeypatch):
    monkeypatch.setattr(
        payload,
        "QUOTAS",
        {source: (fmt, 2, label) for source, (fmt, _, label) in payload.QUOTAS.items()},
    )
    return dataset(tmp_path, {source: 3 for source in payload.QUOTAS})


@pytest.fixture
def packed(tmp_path):
    labels, root, _ = dataset(
        tmp_path,
        {source: count + 2 for source, (_, count, _) in payload.QUOTAS.items()},
    )
    out = tmp_path / "pack"
    report = payload.build(labels, root, out)
    return labels, root, out, report


def test_full_pack_original_bytes(packed):
    labels, root, out, report = packed
    assert sum(report["counts"].values()) == 200
    assert len(list((out / "jpeg").iterdir())) == 100
    assert len(list((out / "png").iterdir())) == 100
    assert report["labels_sha256"] == payload.digest(labels.read_bytes())
    with (out / "payload-manifest.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 200 and {r["split"] for r in rows} == {"train"}
    for row in rows:
        original = payload.raw_file(row["raw_path"], root).read_bytes()
        assert (out / row["filename"]).read_bytes() == original
        assert hashlib.sha256(original).hexdigest() == row["sha256"]
    zipped = Path(str(out) + ".zip")
    assert Path(str(zipped) + ".sha256").read_text().split()[0] == payload.digest(
        zipped.read_bytes()
    )
    assert "không dùng đánh giá độ chính xác" in (out / "README.md").read_text(
        encoding="utf-8"
    )


def test_locust_loader(packed):
    probe = subprocess.run(
        [sys.executable, "-I", "-c", "import locust.env"],
        capture_output=True,
        check=False,
    )
    if probe.returncode:
        pytest.skip("Install locust/requirements.txt for the real loader check")
    _, _, out, _ = packed
    # Follow the existing subprocess pattern: Locust monkey-patches gevent on import.
    code = """
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('lf', sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.PAYLOAD_DIR = Path(sys.argv[2]); m.MIX = 'jpeg=50,png=50'
mix = m._load_payloads()
print(json.dumps({'mix':mix, 'n':len(m._pool), 'mime':sorted({mime for _,mime in m._pool})}))
"""
    run = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            code,
            str(Path("locust/locustfile.py").resolve()),
            str(out),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    assert json.loads(run.stdout) == {
        "mix": {"jpeg": 50, "png": 50},
        "n": 200,
        "mime": ["image/jpeg", "image/png"],
    }


def test_reproducible_after_csv_reorder(small, tmp_path):
    labels, root, rows = small
    first = tmp_path / "one"
    payload.build(labels, root, first)
    pools, _ = payload.candidates(labels.read_bytes(), root)
    selected = payload.select(pools)
    write_labels(labels, rows[::-1])
    reordered, _ = payload.candidates(labels.read_bytes(), root)
    assert payload.select(reordered) == selected
    # Same exact CSV bytes produce identical manifests and ZIPs (including provenance).
    write_labels(labels, rows)
    second = tmp_path / "two"
    payload.build(labels, root, second)
    assert (
        Path(str(first) + ".zip").read_bytes()
        == Path(str(second) + ".zip").read_bytes()
    )


def test_excluded_rows_never_opened(small):
    labels, root, rows = small
    excluded = []
    for index, (source, split) in enumerate(
        [
            ("genimage_real", "test"),
            ("genimage_real", "val"),
            ("cifake_real", "train"),
            ("phone", "train"),
            ("zalo", "train"),
        ]
    ):
        excluded.append(
            rows[0]
            | {
                "source": source,
                "split": split,
                "raw_path": f"does-not-exist/{index}",
                "group_id": f"excluded-{index}",
            }
        )
    write_labels(labels, rows + excluded)
    pools, _ = payload.candidates(labels.read_bytes(), root)
    assert len(payload.select(pools)) == 8


@pytest.mark.parametrize(
    "change",
    [
        {"raw_path": "data/raw/genimage/real/../../outside.jpg"},
        {"raw_path": "C:/private.jpg"},
        {"raw_path": "data/raw/genimage/glide/0.png"},
        {"label": "1"},
        {"norm_version": "2"},
        {"split": "unknown"},
        {"filepath": "C:/private.jpg"},
    ],
)
def test_bad_metadata_fails(small, change):
    labels, root, rows = small
    rows[0].update(change)
    write_labels(labels, rows)
    with pytest.raises(ValueError):
        payload.candidates(labels.read_bytes(), root)


def test_missing_file_and_test_group_overlap(small):
    labels, root, rows = small
    write_labels(labels, rows + [rows[0] | {"split": "test"}])
    with pytest.raises(ValueError, match="overlaps test"):
        payload.candidates(labels.read_bytes(), root)
    write_labels(labels, rows)
    payload.raw_file(rows[0]["raw_path"], root).unlink()
    with pytest.raises(FileNotFoundError):
        payload.candidates(labels.read_bytes(), root)


@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "oversize",
        "corrupt",
        "fake",
        "apng",
        "small",
        "pixels",
        "side",
        "duplicate",
    ],
)
def test_bad_images_skipped(small, kind):
    labels, root, rows = small
    row = next(r for r in rows if r["source"] == "genimage_glide")
    target = payload.raw_file(row["raw_path"], root)
    if kind == "empty":
        target.write_bytes(b"")
    elif kind == "oversize":
        target.write_bytes(b"x" * (payload.MAX_BYTES + 1))
    elif kind == "corrupt":
        target.write_bytes(target.read_bytes()[:70])
    elif kind == "fake":
        Image.new("RGB", (256, 256)).save(target, "JPEG")
    elif kind == "duplicate":
        target.write_bytes((target.parent / "1.png").read_bytes())
    elif kind == "apng":
        Image.new("RGB", (256, 256), "red").save(
            target,
            "PNG",
            save_all=True,
            append_images=[Image.new("RGB", (256, 256), "blue")],
        )
    else:
        dims = {"small": (255, 256), "pixels": (5000, 5000), "side": (10001, 256)}
        Image.new("L", dims[kind]).save(target, "PNG")
    pools, skipped = payload.candidates(labels.read_bytes(), root)
    assert sum(skipped.values()) == 1
    assert len(pools["genimage_glide"]) == 2


def test_size_boundary(small):
    labels, root, rows = small
    target = payload.raw_file(rows[0]["raw_path"], root)
    data = target.read_bytes()
    target.write_bytes(data + b"\0" * (payload.MAX_BYTES - len(data)))
    pools, _ = payload.candidates(labels.read_bytes(), root)
    assert any(r["size_bytes"] == payload.MAX_BYTES for r in pools["genimage_real"])
    target.write_bytes(target.read_bytes() + b"\0")
    _, skipped = payload.candidates(labels.read_bytes(), root)
    assert skipped["empty_or_oversize"] == 1


def test_insufficient_and_existing_outputs(small, tmp_path):
    labels, root, rows = small
    write_labels(labels, rows[:1])
    out = tmp_path / "missing"
    assert (
        payload.main(
            ["--labels", str(labels), "--raw-dir", str(root), "--out", str(out)]
        )
        == 2
    )
    assert not out.exists() and not Path(str(out) + ".zip").exists()
    write_labels(labels, rows)
    payload.build(labels, root, out)
    before = Path(str(out) + ".zip").read_bytes()
    with pytest.raises(ValueError, match="already exists"):
        payload.build(labels, root, out)
    assert Path(str(out) + ".zip").read_bytes() == before


def test_archive_tamper_detected(tmp_path):
    zipped = tmp_path / "bad.zip"
    with zipfile.ZipFile(zipped, "w") as archive:
        archive.writestr("jpeg/a.jpg", b"changed")
    with pytest.raises(ValueError, match="checksum"):
        payload.verify_zip(
            zipped,
            [
                {
                    "filename": "jpeg/a.jpg",
                    "size_bytes": 3,
                    "sha256": payload.digest(b"old"),
                }
            ],
            {},
        )


def test_limits_match_api_defaults():
    from app.settings import Settings
    from models.normalize import MIN_SIDE

    defaults = Settings(_env_file=None)
    assert (
        payload.MAX_BYTES,
        payload.MAX_PIXELS,
        payload.MAX_SIDE,
        payload.MIN_SIDE,
    ) == (
        defaults.max_file_bytes,
        defaults.max_pixels,
        defaults.max_side,
        MIN_SIDE,
    )
