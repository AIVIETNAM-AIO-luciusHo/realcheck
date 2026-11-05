"""Evaluate an existing GenImage probe only after its exact inputs are approved."""

import argparse
import csv
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from models.clip_input import feature_contract
from models.extract_features import load_features, sha256_file
from models.normalize import NORMALIZATION_VERSION
from models.run_info import run_info
from models.score import Scorer, load_bundle
from models.train import metrics

SOURCES = {"genimage_real", "genimage_sd14", "genimage_midjourney", "genimage_glide"}
EVIDENCE = ("data_qa", "metadata_audit", "holdout_review", "thresholds")


def _inputs(labels: Path, feature_dir: Path, model: Path):
    features, rows, manifest = load_features(labels, feature_dir)
    bundle = load_bundle(model)
    for key in ("labels_sha256", "features_sha256"):
        if bundle["metadata"].get(key) != manifest[key]:
            raise ValueError(f"Model was trained on different {key}; retrain")
    indices = [
        i
        for i, row in enumerate(rows)
        if row["source"] in SOURCES and row["split"] == "test"
    ]
    if {rows[i]["source"] for i in indices} != SOURCES:
        raise ValueError("GenImage test must contain all four registered sources")
    identity = {
        "schema_version": 1,
        "dataset": "genimage",
        "split": "test",
        "artifacts": {
            "labels_sha256": manifest["labels_sha256"],
            "features_sha256": manifest["features_sha256"],
            "feature_manifest_sha256": sha256_file(feature_dir / "manifest.json"),
            "model_sha256": sha256_file(model),
        },
        "profile": {**feature_contract(), "norm_version": NORMALIZATION_VERSION},
        "thresholds": bundle["thresholds"],
        "test_rows": len(indices),
    }
    return features, rows, manifest, bundle, indices, identity


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def prepare_lock(labels: Path, features: Path, model: Path, lock: Path) -> dict:
    """Prepare a proposed identity snapshot; never predict or assert QA approval."""
    *_, identity = _inputs(labels, features, model)
    proposed = {
        **identity,
        "status": "proposed",
        "approved_by": [],
        "evidence": {key: "" for key in EVIDENCE},
    }
    lock.parent.mkdir(parents=True, exist_ok=True)
    _write_json(lock, proposed)
    return proposed


def evaluate(
    labels: Path, features: Path, model: Path, lock: Path, output: Path
) -> dict:
    """No fit, threshold search, CLIP download or mutation of the trained probe."""
    protocol = json.loads(lock.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict):
        raise TypeError("Test protocol must be a JSON object")
    reviewers = protocol.get("approved_by")
    evidence = protocol.get("evidence", {})
    if (
        protocol.get("status") != "approved"
        or not isinstance(reviewers, list)
        or not reviewers
        or any(not isinstance(name, str) or not name.strip() for name in reviewers)
        or not isinstance(evidence, dict)
        or any(
            not isinstance(evidence.get(key), str) or not evidence[key].strip()
            for key in EVIDENCE
        )
    ):
        raise ValueError(
            "Test protocol needs actual approval and all QA evidence references"
        )
    x, rows, manifest, bundle, indices, identity = _inputs(labels, features, model)
    for key, expected in identity.items():
        if protocol.get(key) != expected:
            raise ValueError(f"Locked {key} differs from current inputs")
    used = lock.with_suffix(lock.suffix + ".used.json")
    if used.exists():
        raise FileExistsError(
            f"Test was already started with {lock.name}; review its evidence"
        )
    output.mkdir(parents=True, exist_ok=False)
    provenance = run_info("models.evaluate")
    lock_hash = sha256_file(lock)
    # Reserve before any prediction, including failed attempts. Do not erase to retry.
    _write_json(
        used,
        {
            "run_id": provenance["id"],
            "lock_sha256": lock_hash,
            "started_at": provenance["started_at"],
        },
    )
    _write_json(output / "protocol.json", protocol)
    scorer = Scorer(bundle["probe"], None)
    probabilities = scorer.predict_features(x[indices])
    selected = [rows[i] for i in indices]
    y = np.array([int(row["label"]) for row in selected])
    thresholds = identity["thresholds"]
    binary, low, high = (thresholds[key] for key in ("binary", "low", "high"))
    prediction_path = output / "predictions.csv"
    with prediction_path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "row_index",
                "source",
                "label",
                "score",
                "prediction",
                "uncertain",
                "image_sha256",
            ]
        )
        for index, row, probability in zip(indices, selected, probabilities):
            writer.writerow(
                [
                    index,
                    row["source"],
                    row["label"],
                    float(probability),
                    int(probability >= binary),
                    int(low <= probability <= high),
                    manifest["image_sha256"][index],
                ]
            )
    scores = metrics(y, probabilities, binary, low, high)
    by_source = []
    sources = np.array([row["source"] for row in selected])
    for source in sorted(SOURCES):
        mask = sources == source
        by_source.append(
            {"name": source, **metrics(y[mask], probabilities[mask], binary, low, high)}
        )
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "run": provenance,
        "dataset": {
            "version": "genimage",
            "hash": identity["artifacts"]["labels_sha256"],
        },
        "model": {
            "version": feature_contract()["clip_model_id"] + "+LogisticRegression",
            "hash": identity["artifacts"]["model_sha256"],
        },
        "profile": {
            "version": NORMALIZATION_VERSION,
            "hash": hashlib.sha256(
                json.dumps(identity["profile"], sort_keys=True).encode()
            ).hexdigest(),
            "contract": identity["profile"],
        },
        "thresholds": thresholds,
        "lock_sha256": lock_hash,
        "test": scores,
        "by_source": by_source,
        "quality": {
            "target_accuracy": 0.9,
            "status": "pass" if scores["accuracy"] >= 0.9 else "fail",
        },
        "predictions_sha256": sha256_file(prediction_path),
        "limitations": [
            "Quality status is not full MVP release approval",
            "Protocol references record human signoff; this command does not perform independent data/audit QA",
            "File-size, smoothness and JPEG shortcuts remain possible; constant post metadata is not proof of their absence",
            "Historical real-GLIDE file-size accuracy 84.54% is not a measurement on this locked cohort",
        ],
    }
    _write_json(output / "evaluation.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare-lock", type=Path)
    action.add_argument("--lock", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.prepare_lock:
        if args.output_dir:
            parser.error("--output-dir is only used with --lock")
        prepare_lock(args.labels, args.features, args.model, args.prepare_lock)
        print("Proposed protocol saved; test was not evaluated")
    else:
        if not args.output_dir:
            parser.error("--output-dir is required with --lock")
        report = evaluate(
            args.labels, args.features, args.model, args.lock, args.output_dir
        )
        print(
            json.dumps({"test": report["test"], "quality": report["quality"]}, indent=2)
        )
        if report["quality"]["status"] == "fail":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
