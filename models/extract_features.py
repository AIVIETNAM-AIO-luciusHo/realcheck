"""Extract CLIP features from versioned processed images, preserving CSV order."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

from models.clip_input import FEATURE_DIM, encode_images, feature_contract, load_encoder
from models.data_sources import SOURCE_LABELS
from models.normalize import NORMALIZATION_VERSION


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_labels(path: Path) -> list[dict[str, str]]:
    """Validate the manifest; paths are relative to the repository working dir."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"filepath", "label", "source", "split", "raw_path", "norm_version"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(
                "labels.csv needs norm_version; regenerate with prepare_data"
            )
        rows = list(reader)
    if not rows:
        raise ValueError("Empty labels manifest")
    seen = set()
    raw_seen = set()
    for row in rows:
        if None in row or any(row.get(key) is None for key in required):
            raise ValueError("Malformed labels row")
        source = row["source"]
        if source not in SOURCE_LABELS:
            raise ValueError(f"Unknown source: {source}")
        if row["label"] != str(SOURCE_LABELS[source]):
            raise ValueError(f"Label/source mismatch: {row['filepath']}")
        if row["split"] not in {"train", "val", "test"}:
            raise ValueError("Unknown split")
        if row["norm_version"] != NORMALIZATION_VERSION:
            raise ValueError("Stale normalization version in labels")
        filepath = Path(row["filepath"]).resolve()
        if not row["filepath"].strip() or filepath in seen:
            raise ValueError("Empty or duplicate image path in labels")
        seen.add(filepath)
        raw_path = Path(row["raw_path"]).resolve()
        if not row["raw_path"].strip() or raw_path in raw_seen:
            raise ValueError("Empty or duplicate raw_path in labels")
        raw_seen.add(raw_path)
    return rows


def extract_features(
    labels: Path, output_dir: Path, batch_size: int = 32, encoder=None
) -> dict:
    """Write features.npy then manifest.json; incomplete output is never reusable."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    labels_hash = sha256_file(labels)
    rows = read_labels(labels)
    for row in rows:
        if not Path(row["filepath"]).is_file():
            raise FileNotFoundError(row["filepath"])
    encoder = encoder if encoder is not None else load_encoder()
    features = np.empty((len(rows), FEATURE_DIM), dtype=np.float32)
    image_hashes = []
    content_splits = {}
    for start in range(0, len(rows), batch_size):
        images = []
        for row in rows[start : start + batch_size]:
            path = Path(row["filepath"])
            image_hashes.append(sha256_file(path))
            with Image.open(path) as image:
                expected = (
                    (32, 32) if row["source"].startswith("cifake_") else (256, 256)
                )
                if (
                    image.format != "JPEG"
                    or image.mode != "RGB"
                    or image.size != expected
                ):
                    raise ValueError(f"Not a normalized JPEG: {path}")
                pixels = image.copy()
            content_hash = hashlib.sha256(pixels.tobytes()).hexdigest()
            previous = content_splits.setdefault(
                content_hash, (row["split"], row["label"])
            )
            if previous != (row["split"], row["label"]):
                raise ValueError(f"Duplicate pixels cross splits or labels: {path}")
            images.append(pixels)
        features[start : start + len(images)] = encode_images(images, encoder)
        print(f"CLIP: {start + len(images)}/{len(rows)}", flush=True)
    if sha256_file(labels) != labels_hash:
        raise ValueError("Labels changed during extraction; discard this run")
    output_dir.mkdir(parents=True, exist_ok=True)
    feature_path = output_dir / "features.npy"
    with (output_dir / "features.tmp").open("wb") as stream:
        np.save(stream, features, allow_pickle=False)
    (output_dir / "features.tmp").replace(feature_path)
    manifest = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "labels_norm_version": NORMALIZATION_VERSION,
        "rows": len(rows),
        "order": [row["filepath"] for row in rows],
        "labels_sha256": labels_hash,
        "image_sha256": image_hashes,
        "features_sha256": sha256_file(feature_path),
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def load_features(
    labels: Path, feature_dir: Path
) -> tuple[np.ndarray, list[dict], dict]:
    """Refuse stale model, normalization, row order, labels, images or array data."""
    rows = read_labels(labels)
    manifest = json.loads((feature_dir / "manifest.json").read_text(encoding="utf-8"))
    expected = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "labels_norm_version": NORMALIZATION_VERSION,
        "rows": len(rows),
        "order": [row["filepath"] for row in rows],
        "labels_sha256": sha256_file(labels),
        "image_sha256": [sha256_file(Path(row["filepath"])) for row in rows],
        "features_sha256": sha256_file(feature_dir / "features.npy"),
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise ValueError(f"Stale or corrupt features: {key}; extract again")
    features = np.load(feature_dir / "features.npy", allow_pickle=False)
    if (
        features.shape != (len(rows), FEATURE_DIM)
        or features.dtype != np.float32
        or not np.isfinite(features).all()
        or not np.allclose(np.linalg.norm(features, axis=1), 1.0, atol=1e-5)
    ):
        raise ValueError("Invalid feature array")
    return features, rows, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/features"))
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    extract_features(args.labels, args.output_dir, args.batch_size)


if __name__ == "__main__":
    main()
