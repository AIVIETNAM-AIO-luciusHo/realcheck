"""Batch-1 offline cost of e571 or a locked ADV-12 layers candidate; not an HTTP SLO test."""

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import joblib
import numpy as np
import psutil
from PIL import Image

from models.extract_features import sha256_file
from models.normalize import normalize_image
from models.run_info import environment, peak_rss_mib, run_info
from scripts.adv12_run import make_embed, read_rows, versions
from scripts.perf_report import percentile


def load_predictor(args):
    if args.device == "cuda":
        import torch

        if not torch.cuda.is_available():
            raise ValueError("CUDA is not available")
    if args.feature_manifest is None:
        from models.score import load_scorer

        return load_scorer(args.model, device=args.device)
    if (
        sha256_file(args.model)
        != args.model.with_suffix(".joblib.sha256").read_text().strip()
    ):
        raise ValueError("Model checksum mismatch")
    manifest = json.loads(args.feature_manifest.read_text(encoding="utf-8"))
    bundle = joblib.load(args.model)
    if (
        manifest["encoder"] != "layers"
        or manifest["image_column"] != "raw_path"
        or manifest["labels_sha256"] != sha256_file(args.labels)
        or bundle["metadata"]["features_sha256"] != manifest["features_sha256"]
        or bundle["metadata"]["feature_dim"] != manifest["shape"][1]
    ):
        raise ValueError("Candidate/feature manifest mismatch")
    probe = bundle["probe"]
    if set(probe.classes_.tolist()) != {0, 1}:
        raise ValueError("Candidate needs real=0 and AI=1")
    embed = make_embed(
        SimpleNamespace(
            encoder="layers",
            layers=manifest["layers"],
            model_id=manifest["model_id"],
            revision=manifest["revision"],
            device=args.device,
        )
    )
    column = int(np.flatnonzero(probe.classes_ == 1)[0])

    def predict(image):
        features = embed([normalize_image(image).image])
        probability = np.asarray(probe.predict_proba(features))
        if (
            probability.shape != (1, 2)
            or not np.isfinite(probability).all()
            or (probability < 0).any()
            or (probability > 1).any()
            or not np.allclose(probability.sum(axis=1), 1)
        ):
            raise ValueError("Invalid candidate probabilities")
        return float(probability[0, column])

    return predict


def run(args, loader=None):
    if args.output.exists():
        raise FileExistsError("Benchmark output already exists")
    if args.warmup < 0:
        raise ValueError("warmup must be >= 0")
    labels_hash = sha256_file(args.labels)
    ids_bytes = args.sample_ids.read_bytes()
    rows = {r["filepath"]: r for r in read_rows(args.labels) if r["split"] == "val"}
    ids = json.loads(ids_bytes)
    if (
        not isinstance(ids, list)
        or not ids
        or any(not isinstance(i, str) for i in ids)
        or len(set(ids)) != len(ids)
        or any(i not in rows for i in ids)
        or any(not rows[i]["source"].startswith("genimage_") for i in ids)
    ):
        raise ValueError("sample IDs must be unique GenImage validation IDs")
    inputs = {i: sha256_file(Path(rows[i]["raw_path"])) for i in ids}
    env, code = environment(), run_info("scripts.benchmark_adv12")
    report = {
        "status": "started",
        "kind": "offline_batch1_not_http_slo",
        "run_id": code["id"],
        "code_commit": code["git_commit"],
        "dirty": code["git_dirty"],
        "versions": versions(),
        "environment": {k: env[k] for k in ("python", "packages_sha256")},
        "platform": platform.platform(),
        "device": args.device,
        "cpu_thread_policy": 4 if args.device == "cpu" else None,
        "thread_env": {
            k: os.environ.get(k)
            for k in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS")
        },
        "batch_size": 1,
        "labels_sha256": labels_hash,
        "sample_ids_sha256": hashlib.sha256(ids_bytes).hexdigest(),
        "model_sha256": sha256_file(args.model),
        "warmup_count": args.warmup,
        "feature_manifest_sha256": sha256_file(args.feature_manifest)
        if args.feature_manifest
        else None,
        "rss_before_load_mib": psutil.Process().memory_info().rss / 2**20,
        "samples": [],
        "timing_scope": "read/decode raw + normalization + encoder + LR; SHA preflight warms OS file cache",
        "memory_scope": "process RSS; peak is OS high-water mark for entire fresh process, not GPU VRAM",
        "independent_qa_approved": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        try:
            start = time.perf_counter()
            predict = (loader or load_predictor)(args)
            report["load_ms"] = (time.perf_counter() - start) * 1000
            report["rss_after_load_mib"] = psutil.Process().memory_info().rss / 2**20
            for index in range(args.warmup + len(ids)):
                sample_id = (
                    ids[index % len(ids)]
                    if index < args.warmup
                    else ids[index - args.warmup]
                )
                start = time.perf_counter()
                with Image.open(rows[sample_id]["raw_path"]) as image:
                    image.load()
                    score = predict(image)
                elapsed = (time.perf_counter() - start) * 1000
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError("Invalid score")
                if index >= args.warmup:
                    report["samples"].append(
                        {
                            "sample_id": sample_id,
                            "latency_ms": elapsed,
                            "raw_sha256": inputs[sample_id],
                            "source": rows[sample_id]["source"],
                        }
                    )
            if any(sha256_file(Path(rows[i]["raw_path"])) != inputs[i] for i in ids):
                raise ValueError("Input changed during benchmark")
            for path, key in (
                (args.labels, "labels_sha256"),
                (args.sample_ids, "sample_ids_sha256"),
                (args.model, "model_sha256"),
                (args.feature_manifest, "feature_manifest_sha256"),
            ):
                if path is not None and sha256_file(path) != report[key]:
                    raise ValueError("Artifact changed during benchmark")
            latencies = sorted(r["latency_ms"] for r in report["samples"])
            report["latency_ms"] = {
                f"p{p}": percentile(latencies, p) for p in (50, 95, 99)
            }
            report["status"] = "complete"
        except Exception as exc:
            report.update(status="failed", error_type=type(exc).__name__)
            raise
        finally:
            report["rss_end_mib"] = psutil.Process().memory_info().rss / 2**20
            report["peak_rss_process_mib"] = peak_rss_mib()
            output.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument(
        "--feature-manifest",
        type=Path,
        help="omit for serving-compatible e571 baseline",
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument(
        "--sample-ids", type=Path, required=True, help="JSON list pinned before the run"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    try:
        run(parser.parse_args(argv))
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
