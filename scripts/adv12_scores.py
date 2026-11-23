"""Validation-only E4 Platt / E5 equal mean; apply frozen parameters without refitting.

Protocol approval and once-only execution remain manual gates (see the #159 runbook).
Model hashes are producer declarations, not proof of the origin of a score CSV.
"""

import argparse
import csv
import json
import math
import re
import sys
from pathlib import Path

import numpy as np

from models.run_info import environment, run_info
from scripts import calibrate_scores as cs
from scripts import compare_models as cm
from scripts.adv12_run import read_rows

E0_SHA256 = "e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494"


def model_hash(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise argparse.ArgumentTypeError("model SHA256 must be 64 lowercase hex digits")
    return value


def transform(a: dict, b: dict | None, params: dict) -> dict:
    ids = cm.align(a, b if b is not None else a)
    p = np.array([a[s]["score"] for s in ids])
    if params["mode"] == "mean":
        if b is None:
            raise ValueError("mean requires --b and its declared model hash")
        values = (p + np.array([b[s]["score"] for s in ids])) / 2
    else:
        if b is not None:
            raise ValueError("Platt takes one score file")
        values = cs.sigmoid(params["a"] * cs.logit(p) + params["b"])
    return {s: {**a[s], "score": float(v)} for s, v in zip(ids, values)}


def validation_only(labels: Path, scores: dict) -> None:
    rows = read_rows(labels)
    if any(
        r["split"] == "test" or not r["source"].startswith("genimage_") for r in rows
    ):
        raise ValueError(
            "fit requires a GenImage train/val development manifest, no test"
        )
    expected = {
        r["filepath"]: {
            "label": int(r["label"]),
            "group_id": r["group_id"],
            "source": r["source"],
        }
        for r in rows
        if r["split"] == "val"
    }
    cm.align(expected, scores)
    if {r["label"] for r in scores.values()} != {0, 1}:
        raise ValueError("fit requires both classes")


def operating_ci(scores: dict, threshold: float, args) -> dict:
    """Conditional grouped bootstrap: fitted parameters/cutoff stay fixed in every draw."""
    ids = sorted(scores)
    y = np.array([scores[s]["label"] for s in ids])
    p = np.array([scores[s]["score"] for s in ids])
    groups = [scores[s]["group_id"] for s in ids]
    weights = cm.group_weights(groups, y, args.replicates, args.seed)
    out = {"threshold": threshold, "rule": "score >= threshold"}
    for name, mask, called in (
        ("fpr", y == 0, p >= threshold),
        ("fnr", y == 1, p < threshold),
        ("accuracy", np.ones(len(y), dtype=bool), (p >= threshold) == y),
    ):
        if not mask.any():
            out[name] = {"value": None, "ci95": None}
            continue
        boot = (weights @ (mask & called)) / (weights @ mask)
        out[name] = {
            "value": float(called[mask].mean()),
            "ci95": np.percentile(boot, [2.5, 97.5]).tolist(),
        }
    return out


def fit(a: dict, b: dict | None, e0: dict, args) -> tuple[dict, dict, dict]:
    validation_only(args.labels, a)
    ids = cm.align(a, b if b is not None else a)
    cm.align(a, e0)
    real = [r for r in e0.values() if r["label"] == 0]
    e0_fpr = sum(r["score"] > 0.7 for r in real) / len(real)
    if not math.isclose(args.target_fpr, e0_fpr, rel_tol=0, abs_tol=1e-15):
        raise ValueError(
            "target FPR differs from E0 validation score > 0.7; check the locked protocol"
        )
    y = np.array([a[s]["label"] for s in ids])
    p = np.array([a[s]["score"] for s in ids])
    params = {
        "schema_version": 1,
        "mode": args.mode,
        "model_sha256": [args.a_model_sha],
    }
    report = {}
    if args.mode == "platt":
        report["calibration"] = cs.calibrate(y, p, args.target_fpr)
        params.update({k: report["calibration"]["platt"][k] for k in ("a", "b")})
    else:
        params["model_sha256"].append(args.b_model_sha)
        params["weights"] = [0.5, 0.5]
    result = transform(a, b, params)
    values = np.array([result[s]["score"] for s in ids])
    params["target_fpr"] = args.target_fpr
    params["threshold"] = cs.pick_threshold(y, values, args.target_fpr)["threshold"]
    report["fixed_thresholds_A_vs_result"] = cm.compare(a, result, args)
    report["fixed_thresholds_E0_vs_result"] = cm.compare(e0, result, args)
    report["declared_e0_model_sha256"] = E0_SHA256
    if b is not None:
        report["fixed_thresholds_B_vs_result"] = cm.compare(b, result, args)
    slices = {"__all__": result}
    for source in sorted({r["source"] for r in result.values()}):
        slices[source] = {s: r for s, r in result.items() if r["source"] == source}
    report["selected_operating_point"] = {
        name: {
            "n": len(rows),
            "n_real": sum(r["label"] == 0 for r in rows.values()),
            "n_ai": sum(r["label"] == 1 for r in rows.values()),
            **operating_ci(rows, params["threshold"], args),
        }
        for name, rows in slices.items()
    }
    report["primary_accuracy_binary"] = {
        name: {
            key: sum((scores[s]["score"] >= 0.5) == r["label"] for s, r in rows.items())
            / len(rows)
            for key, scores in (("E0", e0), ("A", a), ("result", result))
        }
        for name, rows in slices.items()
    }
    report["ci_scope"] = (
        "conditional_on_fitted_parameters_and_selected_cutoff; not selection-adjusted"
    )
    report["metrics_scope"] = "fit_and_evaluate_on_same_validation; not final evidence"
    return params, result, report


def read_params(path: Path, hashes: list[str]) -> dict:
    params = json.loads(path.read_text(encoding="utf-8"))
    try:
        if params["schema_version"] != 1 or params["model_sha256"] != hashes:
            raise ValueError("parameter schema or declared model hashes mismatch")
        mode = params["mode"]
        if mode not in ("platt", "mean") or len(hashes) != (2 if mode == "mean" else 1):
            raise ValueError("invalid mode/input count")
        if not (
            0 <= params["target_fpr"] <= 1
            and 0 <= params["threshold"] <= math.nextafter(1.0, math.inf)
        ):
            raise ValueError("invalid frozen threshold/target")
        if mode == "mean" and params["weights"] != [0.5, 0.5]:
            raise ValueError("only the fixed equal mean is supported")
        if mode == "platt" and not (
            math.isfinite(params["a"])
            and params["a"] > 0
            and math.isfinite(params["b"])
        ):
            raise ValueError("invalid Platt parameters")
    except (KeyError, TypeError) as exc:
        raise ValueError("malformed frozen parameters") from exc
    return params


def write_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def execute(args) -> None:
    # Reserve a fresh directory before reading/fitting. Failed attempts remain as evidence.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    info = run_info("scripts.adv12_scores")
    for key in ("command", "working_directory"):
        info.pop(key, None)
    report = {
        "run": info,
        "probability_verified": False,
        "independent_qa_approved": False,
        "decision": "review_required; no automatic improvement or release approval",
        "protocol_gate": "manual; no protocol JSON or used-marker enforcement",
        "model_hash_scope": "declared by producer; verify score-run receipts separately",
        "environment": environment(),
        "status": "started",
    }
    try:
        paths = {"a": args.a}
        if args.b:
            paths["b"] = args.b
        paths["params" if args.command == "apply" else "labels"] = (
            args.params if args.command == "apply" else args.labels
        )
        if args.command == "fit":
            paths["e0"] = args.e0
        hashes = {k: cm.sha256_file(p) for k, p in paths.items()}
        report["input_sha256"] = hashes
        a = cm.read_scores(args.a)
        b = cm.read_scores(args.b) if args.b else None
        declared = [args.a_model_sha] + ([args.b_model_sha] if args.b else [])
        if args.command == "apply":
            params = read_params(args.params, declared)
            result = transform(a, b, params)
            report["metrics_scope"] = (
                "application_only; no refitting, threshold selection or metrics"
            )
        else:
            params, result, metrics = fit(a, b, cm.read_scores(args.e0), args)
            report.update(metrics)
            params["fit_input_sha256"] = hashes
        if any(cm.sha256_file(p) != hashes[k] for k, p in paths.items()):
            raise ValueError(
                "input changed during run; discard output and preserve failure"
            )
        write_json(args.output_dir / "params.json", params)
        score_file = args.output_dir / "scores.csv"
        with score_file.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "sample_id",
                    "label",
                    "score",
                    "group_id",
                    "source",
                    "selected_ai",
                ],
            )
            writer.writeheader()
            writer.writerows(
                {
                    "sample_id": s,
                    **r,
                    "selected_ai": int(r["score"] >= params["threshold"]),
                }
                for s, r in sorted(result.items())
            )
        report.update(
            status="completed",
            n=len(result),
            output_sha256={
                name: cm.sha256_file(args.output_dir / name)
                for name in ("params.json", "scores.csv")
            },
        )
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        raise
    finally:
        write_json(args.output_dir / "report.json", report)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("fit", "apply"):
        ap = sub.add_parser(command)
        ap.add_argument("--a", type=Path, required=True)
        ap.add_argument("--a-model-sha", type=model_hash, required=True)
        ap.add_argument("--b", type=Path)
        ap.add_argument("--b-model-sha", type=model_hash)
        ap.add_argument("--output-dir", type=Path, required=True)
        if command == "fit":
            ap.add_argument("--mode", choices=("platt", "mean"), required=True)
            ap.add_argument("--labels", type=Path, required=True)
            ap.add_argument(
                "--e0",
                type=Path,
                required=True,
                help="locked e571 validation scores for paired reference",
            )
            ap.add_argument("--target-fpr", type=float, required=True)
            ap.add_argument("--replicates", type=int, default=2000)
            ap.add_argument("--seed", type=int, default=42)
        else:
            ap.add_argument("--params", type=Path, required=True)
    args = parser.parse_args(argv)
    if bool(args.b) != bool(args.b_model_sha):
        parser.error("--b and --b-model-sha must be provided together")
    if args.command == "fit":
        if (args.mode == "mean") != bool(args.b):
            parser.error("mean requires two inputs; Platt requires one")
        if not 0 <= args.target_fpr <= 1 or args.replicates < 2 or args.seed < 0:
            parser.error("target FPR in [0,1], replicates >= 2, seed >= 0 required")
        # ADV-12 primary operating points are fixed, never CLI tuned.
        args.low, args.binary, args.high = 0.3, 0.5, 0.7
    try:
        execute(args)
    except (ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
