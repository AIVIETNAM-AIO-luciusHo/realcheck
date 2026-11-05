"""Đánh giá model đã khóa trên một split, xuất báo cáo cho trang đánh giá (T013).

Không train và không chọn ngưỡng: công thức dùng lại models.train.metrics, ngưỡng lấy
từ model. Phải ghi rõ --split để không vô tình mở tập test; tập test chỉ chạy một lần
sau khi đã khóa model và ngưỡng, không ghi đè báo cáo đã có.

Cách chạy (từ thư mục gốc repo):
    python -m scripts.evaluate --split val --output artifacts/evaluation-val.json
    python -m scripts.evaluate --split test --output artifacts/evaluation.json
"""

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np

from models.clip_input import feature_contract
from models.extract_features import load_features, sha256_file
from models.normalize import NORMALIZATION_VERSION
from models.run_info import run_info
from models.score import Scorer
from models.train import metrics

ACCURACY_TARGET = 0.90
# models.train.metrics đang cố định vùng Chưa chắc ở các ngưỡng này
METRIC_UNCERTAIN_RANGE = {"low": 0.3, "high": 0.7}


def load_locked_model(path: Path, manifest: dict) -> tuple[dict, str]:
    """Đọc model tin cậy; từ chối nếu tệp, phiên bản hoặc dữ liệu train không khớp."""
    model_hash = sha256_file(path)
    expected_hash = path.with_suffix(path.suffix + ".sha256").read_text().strip()
    if model_hash != expected_hash:
        raise ValueError("Model checksum mismatch")
    bundle = joblib.load(path)
    expected = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "labels_sha256": manifest["labels_sha256"],
        "features_sha256": manifest["features_sha256"],
    }
    for key, value in expected.items():
        if bundle["metadata"].get(key) != value:
            raise ValueError(f"Model does not match this data: {key}; retrain first")
    thresholds = bundle["thresholds"]
    if any(thresholds[key] != value for key, value in METRIC_UNCERTAIN_RANGE.items()):
        raise ValueError("Model thresholds differ from models.train.metrics")
    return bundle, model_hash


def evaluate(labels: Path, feature_dir: Path, model_path: Path, split: str) -> dict:
    features, rows, manifest = load_features(labels, feature_dir)
    bundle, model_hash = load_locked_model(model_path, manifest)
    dataset = bundle["metadata"]["dataset"]
    keep = np.array(
        [
            row["source"].startswith(f"{dataset}_") and row["split"] == split
            for row in rows
        ]
    )
    selected = [row for row, kept in zip(rows, keep) if kept]
    y = np.array([int(row["label"]) for row in selected])
    if set(y.tolist()) != {0, 1}:
        raise ValueError(f"{dataset}/{split} needs both classes")
    sources = np.array([row["source"] for row in selected])
    ai_column = Scorer(bundle["probe"], None).ai_column
    scores = bundle["probe"].predict_proba(features[keep])[:, ai_column]
    binary = bundle["thresholds"]["binary"]
    overall = metrics(y, scores, binary)
    by_source = [
        {
            "name": source,
            **metrics(y[sources == source], scores[sources == source], binary),
        }
        for source in sorted(set(sources.tolist()))
    ]
    report = {
        "dataset": {"version": dataset, "hash": manifest["labels_sha256"]},
        "model": {
            "version": feature_contract()["clip_model_id"] + "+LogisticRegression",
            "hash": model_hash,
        },
        # Cùng cách tính với báo cáo của models.train
        "profile": {
            "version": NORMALIZATION_VERSION,
            "hash": hashlib.sha256(
                json.dumps(
                    {**feature_contract(), "norm_version": NORMALIZATION_VERSION},
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        },
        "thresholds": bundle["thresholds"],
        "split": split,
        split: overall,
        f"{split}_by_source": by_source,
        "created_at": datetime.now(UTC).isoformat(),
    }
    if split == "test":
        report["by_source"] = by_source
        report["accuracy_target"] = {
            "value": ACCURACY_TARGET,
            "passed": overall["accuracy"] >= ACCURACY_TARGET,
        }
    else:
        report.update(test=None, by_source=[])
    return report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["val", "test"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--features", type=Path, default=Path("data/features"))
    parser.add_argument("--model", type=Path, default=Path("models/clip_probe.joblib"))
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    provenance = run_info("scripts.evaluate")
    report = evaluate(args.labels, args.features, args.model, args.split)
    report["run"] = provenance
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    result = report[args.split]
    print(f"Đã ghi {args.output}")
    print(
        f"{args.split}: n={result['n']} accuracy={result['accuracy']:.4f} "
        f"chưa chắc={result['uncertain_rate']:.2%}"
    )


if __name__ == "__main__":
    main()
