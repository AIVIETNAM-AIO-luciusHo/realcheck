"""Verify the real ML handoff on validation samples, without evaluating test."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
from PIL import Image

from models.extract_features import load_features, sha256_file
from models.normalize import ImageTooSmall, normalize_image
from models.run_info import run_info
from models.score import load_scorer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--features", type=Path, default=Path("data/features"))
    parser.add_argument("--model", type=Path, default=Path("models/clip_probe.joblib"))
    parser.add_argument(
        "--report", type=Path, default=Path("docs/reports/ml-integration.json")
    )
    args = parser.parse_args()
    provenance = run_info("scripts.verify_ml")
    features, rows, _ = load_features(args.labels, args.features)
    start = perf_counter()
    scorer = load_scorer(args.model)
    startup_s = perf_counter() - start
    assert not scorer.encoder.training
    assert all(not parameter.requires_grad for parameter in scorer.encoder.parameters())
    sources = sorted({r["source"] for r in rows if r["source"].startswith("genimage_")})
    if not sources:
        raise ValueError("No GenImage sources in manifest")
    results = []
    sample = None
    for source in sources:
        candidates = [
            (i, r)
            for i, r in enumerate(rows)
            if r["source"] == source and r["split"] == "val"
        ]
        if not candidates:
            raise ValueError(f"Missing validation image for {source}")
        index, row = candidates[0]
        with (
            Image.open(row["raw_path"]) as raw,
            Image.open(row["filepath"]) as processed,
        ):
            normalized = normalize_image(raw)
            assert normalized.jpeg == Path(row["filepath"]).read_bytes()
            offline_input = scorer.encoder.preprocess([processed])
            online_input = scorer.encoder.preprocess([normalized.image])
            tensor_keys = [
                key for key, value in offline_input.items() if hasattr(value, "shape")
            ]
            assert tensor_keys
            for key in tensor_keys:
                np.testing.assert_array_equal(
                    offline_input[key].cpu().numpy(), online_input[key].cpu().numpy()
                )
            expected = float(
                scorer.probe.predict_proba(features[index : index + 1])[
                    0, scorer.ai_column
                ]
            )
            started = perf_counter()
            actual = scorer(raw)
            duration = perf_counter() - started
            assert abs(actual - expected) <= 1e-5
            sample = raw.convert("RGB")
        results.append(
            {
                "source": source,
                "raw_path": row["raw_path"],
                "split": "val",
                "score": actual,
                "cached_feature_score": expected,
                "absolute_score_difference": abs(actual - expected),
                "tensor_exact_match": True,
                "scoring_seconds": duration,
            }
        )
    # A size/mode robustness smoke test, not a real-phone accuracy benchmark.
    modes = {}
    for name, image in {
        "phone_sized_synthetic_4000x3000": sample.resize((4000, 3000)),
        "grayscale": sample.convert("L"),
        "rgba": sample.convert("RGBA"),
    }.items():
        value = scorer(image)
        assert np.isfinite(value) and 0 <= value <= 1
        modes[name] = value
    try:
        scorer(Image.new("RGB", (32, 32)))
    except ImageTooSmall:
        pass
    else:
        raise AssertionError("Serving accepted a too-small image")
    report = {
        "created_at": datetime.now(UTC).isoformat(),
        "run": provenance,
        "model_sha256": sha256_file(args.model),
        "labels_sha256": sha256_file(args.labels),
        "startup_and_warmup_seconds": startup_s,
        "samples": results,
        "synthetic_size_mode_smoke": modes,
        "small_image_rejected": True,
        "clip_eval_and_frozen": True,
        "test_split_evaluated": False,
        "score_comparison_tolerance": 1e-5,
        "latency_note": "Single-process local smoke timings, not p95 or load benchmark",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
