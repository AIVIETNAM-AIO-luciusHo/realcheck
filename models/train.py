"""Train only on train, select C on validation, optionally evaluate locked test."""

import argparse
import hashlib
import json
import warnings
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)

from models.clip_input import feature_contract
from models.extract_features import load_features, sha256_file
from models.normalize import NORMALIZATION_VERSION
from models.run_info import run_info


def metrics(y: np.ndarray, probabilities: np.ndarray, binary_threshold: float) -> dict:
    """Binary metrics use ALL samples; uncertainty is reported separately."""
    prediction = (probabilities >= binary_threshold).astype(int)
    uncertain = (probabilities >= 0.3) & (probabilities <= 0.7)
    real = y == 0
    decided = ~uncertain
    return {
        "n": len(y),
        "accuracy": float(accuracy_score(y, prediction)),
        "precision": float(precision_score(y, prediction, zero_division=0)),
        "recall": float(recall_score(y, prediction, zero_division=0)),
        "auroc": float(roc_auc_score(y, probabilities))
        if len(np.unique(y)) == 2
        else None,
        "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
        "uncertain_n": int(uncertain.sum()),
        "uncertain_rate": float(uncertain.mean()),
        "decided_accuracy": float(accuracy_score(y[decided], prediction[decided]))
        if decided.any()
        else None,
        "decided_n": int(decided.sum()),
        "false_positive_rate": float(prediction[real].mean()) if real.any() else None,
        "likely_ai_false_positive_rate": float((probabilities[real] > 0.7).mean())
        if real.any()
        else None,
    }


def train(
    labels: Path,
    feature_dir: Path,
    dataset: str,
    output: Path,
    *,
    binary_threshold: float,
    evaluate_test: bool = False,
) -> dict:
    """Persist probe + provenance + checksums; return measured evaluation only."""
    if dataset not in {"cifake", "genimage"}:
        raise ValueError("dataset must be cifake or genimage")
    if not 0 < binary_threshold < 1:
        raise ValueError("binary_threshold must be between 0 and 1")
    features, rows, manifest = load_features(labels, feature_dir)
    selected = np.array([row["source"].startswith(dataset + "_") for row in rows])
    x = features[selected]
    rows = [row for row, keep in zip(rows, selected) if keep]
    y = np.array([int(row["label"]) for row in rows])
    sources = np.array([row["source"] for row in rows])
    splits = np.array([row["split"] for row in rows])
    masks = {split: splits == split for split in ("train", "val", "test")}
    for split, mask in masks.items():
        if set(y[mask].tolist()) != {0, 1}:
            raise ValueError(f"{dataset}/{split} needs both classes")
    candidates = []
    best = None
    # Fixed before test evaluation; ties prefer the smaller C (stronger regularization).
    for c in (0.01, 0.1, 1.0, 10.0, 100.0):
        probe = LogisticRegression(C=c, max_iter=2000, random_state=42)
        with warnings.catch_warnings():
            warnings.simplefilter("error", ConvergenceWarning)
            probe.fit(x[masks["train"]], y[masks["train"]])
        ai_column = int(np.flatnonzero(probe.classes_ == 1)[0])
        val_probability = probe.predict_proba(x[masks["val"]])[:, ai_column]
        val_metrics = metrics(y[masks["val"]], val_probability, binary_threshold)
        candidates.append({"C": c, "validation_accuracy": val_metrics["accuracy"]})
        if best is None or val_metrics["accuracy"] > best[0]:
            best = (val_metrics["accuracy"], probe, c)
    _, probe, best_c = best
    ai_column = int(np.flatnonzero(probe.classes_ == 1)[0])
    metadata = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "dataset": dataset,
        "labels_sha256": manifest["labels_sha256"],
        "features_sha256": manifest["features_sha256"],
        "seed": 42,
        "C": best_c,
        "split_counts": {s: int(m.sum()) for s, m in masks.items()},
    }
    dependencies = {}
    for package in (
        "numpy",
        "pillow",
        "scikit-learn",
        "joblib",
        "torch",
        "transformers",
        "sentence-transformers",
    ):
        try:
            dependencies[package] = version(package)
        except PackageNotFoundError:
            dependencies[package] = "not-installed"
    thresholds = {"binary": binary_threshold, "low": 0.3, "high": 0.7}
    bundle = {
        "probe": probe,
        "metadata": metadata,
        "thresholds": thresholds,
        "dependencies": dependencies,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    joblib.dump(bundle, temporary)
    temporary.replace(output)
    model_hash = sha256_file(output)
    output.with_suffix(output.suffix + ".sha256").write_text(
        model_hash + "\n", encoding="ascii"
    )
    report = {
        "dataset": {"version": dataset, "hash": manifest["labels_sha256"]},
        "model": {
            "version": feature_contract()["clip_model_id"] + "+LogisticRegression",
            "hash": model_hash,
        },
        "profile": {
            "version": NORMALIZATION_VERSION,
            "hash": hashlib.sha256(
                json.dumps(
                    {**feature_contract(), "norm_version": NORMALIZATION_VERSION},
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        },
        "metadata": metadata,
        "dependencies": dependencies,
        "thresholds": thresholds,
        "threshold_status": "initial_experiment_not_release_approval",
        "selection": {
            "metric": "validation_accuracy",
            "candidates": candidates,
            "C": best_c,
        },
        "split_counts": metadata["split_counts"],
        "test": None,
        "by_source": [],
        "limitations": [
            "CIFAKE is a smoke test only",
            "Independent data QA required before release",
            "Validation selected C; GenImage test remains unevaluated unless explicitly requested",
            "File size, smoothness and JPEG history shortcuts remain possible; T027 not implemented",
        ],
    }
    for split in ["val", "test"] if evaluate_test else ["val"]:
        mask = masks[split]
        probability = probe.predict_proba(x[mask])[:, ai_column]
        report[split] = metrics(y[mask], probability, binary_threshold)
        groups = [
            {
                "name": source,
                **metrics(
                    y[mask][sources[mask] == source],
                    probability[sources[mask] == source],
                    binary_threshold,
                ),
            }
            for source in sorted(set(sources[mask]))
        ]
        report[split + "_by_source"] = groups
        if split == "test":
            report["by_source"] = groups
    report["created_at"] = datetime.now(UTC).isoformat()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--features", type=Path, default=Path("data/features"))
    parser.add_argument("--dataset", choices=["cifake", "genimage"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--binary-threshold",
        type=float,
        required=True,
        help="Explicit experiment choice (D08); never tune on test",
    )
    parser.add_argument("--evaluate-test", action="store_true")
    args = parser.parse_args()
    provenance = run_info("models.train")
    started = perf_counter()
    report = train(
        args.labels,
        args.features,
        args.dataset,
        args.output,
        binary_threshold=args.binary_threshold,
        evaluate_test=args.evaluate_test,
    )
    provenance["elapsed_seconds"] = perf_counter() - started
    provenance["finished_at"] = report["created_at"]
    report["run"] = provenance
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "dataset": args.dataset,
                "C": report["selection"]["C"],
                "val": report["val"],
                "test": report["test"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
