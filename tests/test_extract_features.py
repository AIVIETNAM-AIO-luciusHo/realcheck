"""T008: manifest cua extract_features va tu choi cache cu (mock CLIP, khong torch)."""

import csv
import json

import numpy as np
import pytest
from PIL import Image

import models.extract_features as ef
from models.clip_input import FEATURE_DIM
from models.extract_features import extract_features, load_features
from models.normalize import NORMALIZATION_VERSION, normalize_image


class StubEncoder:
    def encode(self, images, **kwargs):
        vectors = np.ones((len(images), FEATURE_DIM), dtype=np.float32)
        vectors[:, 0] = [np.asarray(im).mean() + 1 for im in images]
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


@pytest.fixture
def built(tmp_path):
    rows = []
    for n in range(4):
        path = tmp_path / f"img{n}.jpg"
        path.write_bytes(
            normalize_image(Image.new("RGB", (300, 300), (n * 50, 9, 9))).jpeg
        )
        label = n % 2
        rows.append(
            {
                "filepath": str(path),
                "label": str(label),
                "source": "genimage_sd14" if label else "genimage_real",
                "split": "train" if n < 2 else "val",
                "raw_path": f"raw{n}.png",
                "norm_version": NORMALIZATION_VERSION,
            }
        )
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    features = tmp_path / "features"
    manifest = extract_features(labels, features, batch_size=3, encoder=StubEncoder())
    return labels, features, manifest


def _edit_manifest(features, **changes):
    path = features / "manifest.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), **changes}))


def test_manifest_records_version_and_row_count(built):
    _, features, manifest = built
    on_disk = json.loads((features / "manifest.json").read_text())
    assert on_disk == manifest
    assert manifest["norm_version"] == NORMALIZATION_VERSION
    assert manifest["labels_norm_version"] == NORMALIZATION_VERSION
    assert manifest["rows"] == 4
    assert np.load(features / "features.npy").shape == (4, FEATURE_DIM)


def test_fresh_manifest_loads(built):
    labels, features, _ = built
    array, rows, _ = load_features(labels, features)
    assert array.shape == (4, FEATURE_DIM) and len(rows) == 4


@pytest.mark.parametrize("key", ["norm_version", "labels_norm_version"])
def test_load_rejects_manifest_with_other_version(built, key):
    labels, features, _ = built
    _edit_manifest(features, **{key: "0"})
    with pytest.raises(ValueError, match=key):
        load_features(labels, features)


def test_load_rejects_when_code_version_moved_on(built, monkeypatch):
    labels, features, _ = built
    monkeypatch.setattr(ef, "NORMALIZATION_VERSION", "2")
    with pytest.raises(ValueError):
        load_features(labels, features)


def test_load_rejects_manifest_rows_differing_from_labels(built):
    labels, features, _ = built
    _edit_manifest(features, rows=3)
    with pytest.raises(ValueError, match="rows"):
        load_features(labels, features)


def test_load_rejects_labels_with_fewer_rows_than_manifest(built):
    labels, features, _ = built
    lines = labels.read_text().splitlines()
    labels.write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="rows"):
        load_features(labels, features)


def test_extract_refuses_labels_without_norm_version(built, tmp_path):
    labels, _, _ = built
    old = tmp_path / "old.csv"
    with labels.open() as src, old.open("w", newline="") as dst:
        reader = csv.DictReader(src)
        fields = [f for f in reader.fieldnames if f != "norm_version"]
        writer = csv.DictWriter(dst, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(reader)
    with pytest.raises(ValueError, match="norm_version"):
        extract_features(old, tmp_path / "out", encoder=StubEncoder())
