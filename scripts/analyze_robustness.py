"""ADV-08: validate a locked handoff and analyze saved predictions, without inference."""

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from models.extract_features import sha256_file
from models.run_info import run_info
from models.train import metrics

MODEL_SHA256 = "e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494"
CLIP_ID = "sentence-transformers/clip-ViT-B-32"
CLIP_REVISION = "327ab6726d33c0e22f920c83f2ff9e4bd38ca37f"
THRESHOLDS = {"binary": 0.5, "low": 0.3, "high": 0.7}
BOOTSTRAP = {"replicates": 2000, "seed": 42, "confidence": 0.95}
VERDICTS = ("likely_real", "uncertain", "likely_ai")
EXPECTED_COHORTS = {
    "parents",
    "jpeg90",
    "jpeg70",
    "jpeg50",
    "rotate",
    "crop",
    "downscale",
    "brightness",
    "phone",
    "ai_new",
    "zalo",
}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _no_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=_no_constant)


def _jsonl(path):
    return [
        json.loads(line, parse_constant=_no_constant)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(value):
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(c in "0123456789abcdef" for c in value)
    )


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _commit(value):
    return (
        isinstance(value, str)
        and len(value) == 40
        and all(c in "0123456789abcdef" for c in value)
    )


def verdict(score):
    return VERDICTS[0] if score < 0.3 else VERDICTS[2] if score > 0.7 else VERDICTS[1]


def validate_handoff(protocol_path, manifest_path, *, decode=False, observations=None):
    """Verify bytes/lineage, never deserialize a model or run an encoder.

    Paths in protocol are relative to protocol; image paths are relative to manifest.
    Image decode/size problems remain explicit failures for a partial report.
    """
    protocol_path, manifest_path = Path(protocol_path), Path(manifest_path)
    protocol = _json(protocol_path)
    _require(isinstance(protocol, dict), "Protocol must be an object")
    _require(protocol.get("schema_version") == 1, "Unsupported protocol schema")
    _require(protocol.get("status") == "locked", "Protocol is not locked")
    for key in ("manifest_lock_ref", "split_review_ref", "parent_exposure"):
        _require(_text(protocol.get(key)), f"Missing handoff evidence: {key}")
    runner = protocol.get("runner", {})
    _require(isinstance(runner, dict), "Runner evidence must be an object")
    _require(_commit(runner.get("commit")), "Missing runner commit")
    _require(_text(runner.get("handoff_ref")), "Missing runner handoff reference")
    _require(_text(runner.get("tests_ref")), "Missing runner test evidence")
    _require(_commit(protocol.get("analysis_commit")), "Missing analysis commit")
    env = protocol.get("environment")
    _require(
        isinstance(env, dict)
        and set(env) == {"python", "packages_sha256"}
        and _text(env["python"])
        and _sha(env["packages_sha256"]),
        "Missing environment: python and packages_sha256 (python -m models.run_info)",
    )
    _require(protocol.get("thresholds") == THRESHOLDS, "Thresholds are not locked")
    _require(protocol.get("bootstrap") == BOOTSTRAP, "Bootstrap config is not locked")
    profile = {
        "clip_model_id": CLIP_ID,
        "clip_revision": CLIP_REVISION,
        "normalization_version": "1",
    }
    _require(protocol.get("profile") == profile, "Incompatible locked profile")
    snapshots = {protocol_path: sha256_file(protocol_path)}
    artifacts = protocol["artifacts"]
    for name in ("model", "model_manifest", "manifest"):
        artifact = artifacts[name]
        path = (protocol_path.parent / artifact["path"]).resolve()
        _require(_sha(artifact["sha256"]), f"Invalid {name} SHA256")
        _require(sha256_file(path) == artifact["sha256"], f"{name} checksum mismatch")
        snapshots[path] = artifact["sha256"]
        if name == "manifest":
            _require(path == manifest_path.resolve(), "CLI manifest differs from lock")
    _require(artifacts["model"]["sha256"] == MODEL_SHA256, "Wrong locked model")
    model_path = (protocol_path.parent / artifacts["model"]["path"]).resolve()
    sidecar = model_path.with_suffix(model_path.suffix + ".sha256")
    _require(
        sidecar.read_text(encoding="ascii").strip() == MODEL_SHA256, "Bad raw sidecar"
    )
    snapshots[sidecar] = sha256_file(sidecar)
    model_manifest = _json(protocol_path.parent / artifacts["model_manifest"]["path"])
    _require(isinstance(model_manifest, dict), "Model manifest must be an object")
    for key, expected in {
        **profile,
        "model_sha256": MODEL_SHA256,
        "thresholds": THRESHOLDS,
    }.items():
        _require(model_manifest.get(key) == expected, f"Model manifest mismatch: {key}")

    cohorts = protocol.get("cohorts")
    _require(isinstance(cohorts, list) and bool(cohorts), "No registered cohorts")
    registered = {}
    for cohort in cohorts:
        _require(isinstance(cohort, dict), "Cohort must be an object")
        name = cohort["name"]
        _require(_text(name) and name not in registered, "Duplicate/empty cohort")
        _require(cohort["status"] in {"present", "missing"}, "Bad cohort status")
        _require(
            _text(cohort.get("reason")) if cohort["status"] == "missing" else True,
            "Missing cohort needs a reason",
        )
        if cohort["status"] == "present":
            _require(
                type(cohort["n_expected"]) is int and cohort["n_expected"] > 0,
                "Present cohort needs an actual positive count",
            )
            transform = cohort["transform"]
            _require(
                isinstance(transform, dict)
                and _text(transform.get("kind"))
                and isinstance(transform.get("params"), dict),
                "Transformation parameters are required",
            )
        registered[name] = cohort
    _require(
        EXPECTED_COHORTS <= registered.keys(),
        "Expected cohorts must be present or explicitly missing",
    )

    rows = _jsonl(manifest_path)
    _require(bool(rows), "Empty robustness manifest")
    by_id, groups, counts, images, byte_groups = {}, {}, defaultdict(int), {}, {}
    for row in rows:
        _require(isinstance(row, dict), "Manifest row must be an object")
        for field in ("sample_id", "path", "source", "cohort", "group_id"):
            _require(_text(row.get(field)), f"Missing manifest field: {field}")
        sid, group = row["sample_id"], row["group_id"]
        _require(sid not in by_id, "Duplicate sample_id")
        _require(type(row.get("label")) is int and row["label"] in (0, 1), "Bad label")
        _require(row.get("split") == "test", "Robustness rows must be test")
        _require(
            not row["source"].lower().startswith("cifake"),
            "CIFAKE is not a robustness cohort",
        )
        cohort = registered.get(row["cohort"])
        _require(
            cohort is not None and cohort["status"] == "present", "Unregistered cohort"
        )
        _require(
            row.get("transform") == cohort["transform"], "Transform differs from lock"
        )
        _require(
            row.get("parent_id") is None or _text(row["parent_id"]), "Bad parent_id"
        )
        _require(
            row["transform"]["kind"] in {"original", "zalo"} or row.get("parent_id"),
            "Transformed row needs an explicit parent",
        )
        _require(_sha(row.get("sha256")), "Invalid image SHA256")
        _require(
            row["sha256"] not in byte_groups or byte_groups[row["sha256"]] == group,
            "Exact duplicates must share group_id",
        )
        byte_groups[row["sha256"]] = group
        path = (manifest_path.parent / row["path"]).resolve()
        _require(sha256_file(path) == row["sha256"], "Image checksum mismatch")
        snapshots[path] = row["sha256"]
        if decode:
            try:
                with Image.open(path) as image:
                    image.load()
                    if min(image.size) < 256:
                        images[sid] = "IMAGE_TOO_SMALL"
                    if observations is not None:
                        oriented = ImageOps.exif_transpose(image).convert("RGB")
                        observations[sid] = {
                            "size": list(oriented.size),
                            "pixel_sha256": hashlib.sha256(
                                str(oriented.size).encode() + oriented.tobytes()
                            ).hexdigest(),
                        }
            except (OSError, ValueError, Image.DecompressionBombError):
                images[sid] = "INVALID_IMAGE"
        _require(
            group not in groups or groups[group] == row["label"],
            "Conflicting group labels",
        )
        groups[group] = row["label"]
        counts[row["cohort"]] += 1
        by_id[sid] = row
    for row in rows:
        parent = row.get("parent_id")
        if parent:
            _require(
                row["transform"]["kind"] != "original", "Original cannot be a child"
            )
            _require(parent in by_id, "Missing parent")
            _require(parent != row["sample_id"], "Self parent")
            _require(
                by_id[parent]["parent_id"] is None,
                "Parent must be a root (no chains/cycles)",
            )
            for key in ("label", "group_id", "source"):
                _require(row[key] == by_id[parent][key], f"Parent/child differ: {key}")
    for name, cohort in registered.items():
        expected = cohort["n_expected"] if cohort["status"] == "present" else 0
        _require(counts[name] == expected, f"Cohort count mismatch: {name}")

    history = protocol.get("history")
    _require(isinstance(history, list) and bool(history), "Missing split history")
    history_splits = {group: "test" for group in groups}
    for item in history:
        path = (protocol_path.parent / item["path"]).resolve()
        _require(
            _sha(item["sha256"]) and sha256_file(path) == item["sha256"],
            "History checksum mismatch",
        )
        snapshots[path] = item["sha256"]
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            _require(
                {"group_id", "split"} <= set(reader.fieldnames or []),
                "History needs group_id/split",
            )
            for old in reader:
                _require(
                    _text(old["group_id"]) and old["split"] in {"train", "val", "test"},
                    "Bad history row",
                )
                _require(
                    old["group_id"] not in history_splits
                    or history_splits[old["group_id"]] == old["split"],
                    "Group overlaps train/val/test history",
                )
                history_splits[old["group_id"]] = old["split"]
    return protocol, rows, snapshots, images


def observed_transforms(rows, observations):
    """Expose clamped/no-op variants without excluding any samples or tuning."""
    by_id = {row["sample_id"]: row for row in rows}
    cohorts = {}
    for row in rows:
        parent_id, sid = row["parent_id"], row["sample_id"]
        if not parent_id or sid not in observations or parent_id not in observations:
            continue
        child, parent = observations[sid], observations[parent_id]
        cohort = cohorts.setdefault(
            row["cohort"],
            {
                "n_pairs_observed": 0,
                "n_same_size": 0,
                "n_identical_oriented_rgb": 0,
                "n_clamped_geometry": 0,
                "geometry_examples": [],
            },
        )
        same_size = child["size"] == parent["size"]
        identical = child["pixel_sha256"] == parent["pixel_sha256"]
        cohort["n_pairs_observed"] += 1
        cohort["n_same_size"] += int(same_size)
        cohort["n_identical_oriented_rgb"] += int(identical)
        kind, params = row["transform"]["kind"], row["transform"]["params"]
        if kind in {"center_crop", "crop", "downscale"}:
            requested = params.get("scale" if kind == "downscale" else "keep")
            clamped = (
                isinstance(requested, (float, int))
                and not isinstance(requested, bool)
                and 0 < requested < 1
                and same_size
            )
            cohort["n_clamped_geometry"] += int(clamped)
            if len(cohort["geometry_examples"]) < 20:
                cohort["geometry_examples"].append(
                    {
                        "sample_id": sid,
                        "parent_id": by_id[parent_id]["sample_id"],
                        "parent_size": parent["size"],
                        "child_size": child["size"],
                        "effective_short_side_ratio": min(child["size"])
                        / min(parent["size"]),
                        "requested_ratio": requested,
                        "identical_oriented_rgb": identical,
                    }
                )
    return cohorts


def preflight_report(protocol_path, manifest_path):
    """A hash-bound technical receipt, never an authorization to open test data."""
    observations = {}
    protocol, rows, snapshots, failures = validate_handoff(
        protocol_path, manifest_path, decode=True, observations=observations
    )
    report = {
        "schema_version": 1,
        "kind": "adv08_preflight",
        "status": "ready" if not failures else "image_errors",
        "ready_scope": "available_cohorts_only",
        "preflight_is_not_run_authorization": True,
        "run": _provenance(protocol),
        "n_total": len(rows),
        "image_failures": failures,
        "missing_cohorts": [
            c["name"] for c in protocol["cohorts"] if c["status"] == "missing"
        ],
        "model_sha256": MODEL_SHA256,
        "model_manifest_sha256": protocol["artifacts"]["model_manifest"]["sha256"],
        "manifest_sha256": protocol["artifacts"]["manifest"]["sha256"],
        "protocol_sha256": sha256_file(protocol_path),
        "runner": protocol["runner"],
        "environment": protocol["environment"],
        "thresholds": THRESHOLDS,
        "profile": protocol["profile"],
        "inference_performed": False,
        "observed_transforms": observed_transforms(rows, observations),
    }
    for path, expected in snapshots.items():
        _require(sha256_file(path) == expected, "Input changed during preflight")
    _require(
        not _has_personal_path(json.dumps(report)), "Preflight contains a personal path"
    )
    return report


def read_predictions(path, rows, protocol):
    """Require one explicit outcome per sample and bind every score to this lock."""
    expected = {row["sample_id"]: row for row in rows}
    predictions = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {
            "sample_id",
            "group_id",
            "parent_id",
            "label",
            "status",
            "score",
            "verdict",
            "error_code",
            "model_sha256",
            "manifest_sha256",
            "protocol_sha256",
        }
        _require(
            required <= set(reader.fieldnames or []), "Incomplete predictions schema"
        )
        for prediction in reader:
            sid = prediction["sample_id"]
            _require(
                sid in expected and sid not in predictions,
                "Unknown/duplicate prediction ID",
            )
            row = expected[sid]
            for key, value in (
                ("group_id", row["group_id"]),
                ("parent_id", row["parent_id"] or ""),
                ("label", str(row["label"])),
            ):
                _require(prediction[key] == value, f"Prediction lineage differs: {key}")
            for key in ("model_sha256", "manifest_sha256", "protocol_sha256"):
                _require(
                    prediction[key] == protocol[key],
                    f"Prediction identity differs: {key}",
                )
            _require(prediction["status"] in {"ok", "error"}, "Bad prediction status")
            if prediction["status"] == "ok":
                score = float(prediction["score"])
                _require(np.isfinite(score) and 0 <= score <= 1, "Invalid score")
                _require(
                    prediction["verdict"] == verdict(score), "Verdict/score mismatch"
                )
                _require(
                    not prediction["error_code"], "Successful prediction has an error"
                )
                prediction["score"] = score
            else:
                _require(
                    not prediction["score"]
                    and not prediction["verdict"]
                    and _text(prediction["error_code"]),
                    "Failed prediction needs an error, no invented score",
                )
                _require(
                    re.fullmatch(r"[A-Z][A-Z0-9_]*", prediction["error_code"]),
                    "Use an error code, not a private path/traceback",
                )
            predictions[sid] = prediction
    _require(set(predictions) == set(expected), "Missing prediction IDs")
    return predictions


def _counts(y, scores, weights):
    ai = scores >= 0.5
    return np.array(
        [
            weights.sum(),
            weights[(y == 1) & ai].sum(),
            weights[(y == 0) & ai].sum(),
            weights[(y == 1) & ~ai].sum(),
            weights[(y == 0) & ~ai].sum(),
            weights[(scores >= 0.3) & (scores <= 0.7)].sum(),
        ],
        dtype=float,
    )


def _values(counts):
    n, tp, fp, fn, tn, uncertain = counts
    return {
        "accuracy": (tp + tn) / n if n else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "uncertain_rate": uncertain / n if n else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "false_negative_rate": fn / (fn + tp) if fn + tp else None,
    }


def point_metrics(rows, predictions):
    if not rows:
        return None
    y = np.array([r["label"] for r in rows])
    scores = np.array([predictions[r["sample_id"]]["score"] for r in rows])
    result = metrics(y, scores, 0.5, 0.3, 0.7)
    values = _values(_counts(y, scores, np.ones(len(rows))))
    result["false_negative_rate"] = values["false_negative_rate"]
    result["defined"] = {key: value is not None for key, value in values.items()}
    result["denominators"] = {
        "precision": int((scores >= 0.5).sum()),
        "recall": int((y == 1).sum()),
        "false_positive_rate": int((y == 0).sum()),
    }
    return result


def _paired_values(children, parents, predictions, weights):
    cy = np.array([r["label"] for r in children])
    cs = np.array([predictions[r["sample_id"]]["score"] for r in children])
    ps = np.array([predictions[r["sample_id"]]["score"] for r in parents])
    child_values = _values(_counts(cy, cs, weights))
    parent_values = _values(_counts(cy, ps, weights))
    flips = np.array([verdict(c) != verdict(p) for c, p in zip(cs, ps)])
    result = {"flip_rate": float(weights @ flips / weights.sum())}
    result["accuracy_degradation"] = (
        parent_values["accuracy"] - child_values["accuracy"]
    )
    for key in (
        "precision",
        "recall",
        "uncertain_rate",
        "false_positive_rate",
        "false_negative_rate",
    ):
        c, p = child_values[key], parent_values[key]
        result["delta_" + key] = c - p if c is not None and p is not None else None
    return result


def bootstrap(rows, predictions, parents=None):
    """Stratified cluster bootstrap: one draw moves all rows/pairs in a group."""
    keys = (
        list(_values(np.zeros(6)))
        if parents is None
        else list(_paired_values(rows, parents, predictions, np.ones(len(rows))))
    )
    grouped = defaultdict(list)
    for i, row in enumerate(rows):
        grouped[row["group_id"]].append(i)
    result = {
        key: {"interval": None, "n_boot_valid": 0, "reason": "fewer_than_two_groups"}
        for key in keys
    }
    if len(grouped) < 2:
        return result
    # Multi-source duplicate groups stay intact in a composite source stratum.
    strata = defaultdict(list)
    for group in sorted(grouped):
        members = grouped[group]
        source = tuple(sorted({rows[i]["source"] for i in members}))
        strata[(source, rows[members[0]]["label"])].append(group)
    draws = {key: [] for key in keys}
    rng = np.random.default_rng(BOOTSTRAP["seed"])
    y = np.array([r["label"] for r in rows])
    scores = np.array([predictions[r["sample_id"]]["score"] for r in rows])
    original = (
        _values(_counts(y, scores, np.ones(len(rows))))
        if parents is None
        else _paired_values(rows, parents, predictions, np.ones(len(rows)))
    )
    for _ in range(BOOTSTRAP["replicates"]):
        weights = np.zeros(len(rows))
        for stratum in sorted(strata):
            groups = strata[stratum]
            for index in rng.integers(0, len(groups), size=len(groups)):
                weights[grouped[groups[index]]] += 1
        values = (
            _values(_counts(y, scores, weights))
            if parents is None
            else _paired_values(rows, parents, predictions, weights)
        )
        for key, value in values.items():
            if value is not None:
                draws[key].append(float(value))
    for key, values in draws.items():
        valid = len(values)
        defined = original[key] is not None
        reason = (
            None
            if defined and valid == BOOTSTRAP["replicates"]
            else "undefined_metric_or_bootstrap_replicate"
        )
        interval = (
            np.quantile(values, [0.025, 0.975]).tolist() if reason is None else None
        )
        result[key] = {"interval": interval, "n_boot_valid": valid, "reason": reason}
    return result


def summarize(rows, predictions, by_id):
    valid = [r for r in rows if predictions[r["sample_id"]]["status"] == "ok"]
    paired = [
        r
        for r in valid
        if r["parent_id"] and predictions[r["parent_id"]]["status"] == "ok"
    ]
    parents = [by_id[r["parent_id"]] for r in paired]
    failures = [
        {
            "sample_id": r["sample_id"],
            "error_code": predictions[r["sample_id"]]["error_code"],
        }
        for r in rows
        if predictions[r["sample_id"]]["status"] == "error"
    ]
    pairing = {
        "n_pairs": len(paired),
        "n_unpaired_or_failed_parent": len(rows) - len(paired),
        "metrics": None,
        "parent_matched": None,
        "child_matched": None,
        "ci95": None,
        "transition_counts": None,
        "reason": "no_valid_parent_child_pairs",
    }
    if paired:
        transitions = [[0] * 3 for _ in range(3)]
        for child, parent in zip(paired, parents):
            pv = predictions[parent["sample_id"]]["verdict"]
            cv = predictions[child["sample_id"]]["verdict"]
            transitions[VERDICTS.index(pv)][VERDICTS.index(cv)] += 1
        pairing.update(
            metrics=_paired_values(paired, parents, predictions, np.ones(len(paired))),
            parent_matched=point_metrics(parents, predictions),
            child_matched=point_metrics(paired, predictions),
            ci95=bootstrap(paired, predictions, parents),
            transition_counts=transitions,
            reason=None,
        )
    return {
        "n_total": len(rows),
        "n_scored": len(valid),
        "n_failed": len(failures),
        "n_groups": len({r["group_id"] for r in rows}),
        "n_scored_groups": len({r["group_id"] for r in valid}),
        "n_real": sum(r["label"] == 0 for r in rows),
        "n_ai": sum(r["label"] == 1 for r in rows),
        "metrics": point_metrics(valid, predictions),
        "ci95": bootstrap(valid, predictions) if valid else None,
        "pairing": pairing,
        "failures": failures,
    }


def _provenance(protocol):
    run = run_info("scripts.analyze_robustness")
    _require(
        run["git_commit"] == protocol["analysis_commit"],
        "Analysis source differs from lock",
    )
    _require(run["git_dirty"] is False, "Analysis requires a clean Git checkout")
    # Publish reproducibility without leaking interpreter/cwd machine paths.
    return {
        key: value
        for key, value in run.items()
        if key not in {"command", "working_directory"}
    }


def analyze(protocol_path, manifest_path, predictions_path):
    observations = {}
    protocol, rows, snapshots, image_failures = validate_handoff(
        protocol_path, manifest_path, decode=True, observations=observations
    )
    provenance = _provenance(protocol)
    snapshots[Path(predictions_path)] = sha256_file(predictions_path)
    identity = {
        "model_sha256": MODEL_SHA256,
        "manifest_sha256": protocol["artifacts"]["manifest"]["sha256"],
        "protocol_sha256": sha256_file(protocol_path),
    }
    predictions = read_predictions(predictions_path, rows, identity)
    _require(
        all(predictions[sid]["status"] == "error" for sid in image_failures),
        "An invalid image has a successful prediction",
    )
    by_id = {r["sample_id"]: r for r in rows}
    reports = []
    for cohort in protocol["cohorts"]:
        selected = [r for r in rows if r["cohort"] == cohort["name"]]
        if cohort["status"] == "missing":
            reports.append(
                {
                    "name": cohort["name"],
                    "status": "missing",
                    "reason": cohort["reason"],
                    "n_total": 0,
                    "n_scored": 0,
                    "n_failed": 0,
                    "n_groups": 0,
                    "n_real": 0,
                    "n_ai": 0,
                    "metrics": None,
                    "ci95": None,
                    "pairing": None,
                    "by_source": [],
                }
            )
            continue
        report = {
            "name": cohort["name"],
            "transform": cohort["transform"],
            "status": "partial"
            if any(predictions[r["sample_id"]]["status"] == "error" for r in selected)
            else "complete",
            **summarize(selected, predictions, by_id),
        }
        report["by_source"] = [
            {
                "source": source,
                **summarize(
                    [r for r in selected if r["source"] == source], predictions, by_id
                ),
            }
            for source in sorted({r["source"] for r in selected})
        ]
        reports.append(report)
    for path, expected in snapshots.items():
        _require(sha256_file(path) == expected, "Input changed during analysis")
    report = {
        "schema_version": 1,
        "task": "ADV-08 / GitHub #52",
        "status": "complete_pending_independent_review"
        if all(r["status"] == "complete" for r in reports)
        else "incomplete",
        "run": provenance,
        "created_at": datetime.now(UTC).isoformat(),
        **identity,
        "predictions_sha256": snapshots[Path(predictions_path)],
        "thresholds": THRESHOLDS,
        "profile": protocol["profile"],
        "bootstrap": BOOTSTRAP,
        "runner": protocol["runner"],
        "environment": protocol["environment"],
        "parent_exposure": protocol["parent_exposure"],
        "observed_transforms": observed_transforms(rows, observations),
        "transition_order": list(VERDICTS),
        "cohorts": reports,
        "independent_qa_approved": False,
        "release_approved": False,
        "limitations": [
            "No global accuracy across original images, variants or datasets",
            "Intervals describe stratified group resampling, not new independent images",
            "Missing cohorts and failed predictions prevent complete evaluation",
            "Accuracy degradation is parent minus child; other deltas are child minus parent",
            "Robustness changes are observations, not proof of JPEG or metadata shortcut causality",
            "No 90% OOD quality threshold, model selection or threshold tuning",
            "Clamped crop/downscale can leave parent pixels unchanged; inspect observed_transforms before interpreting zero flips",
        ],
    }
    _require(
        not _has_personal_path(json.dumps(report)),
        "Report contains a personal path; use relative evidence references",
    )
    return report


def _has_personal_path(text):
    return re.search(
        r"[A-Za-z]:[\\/]+(?:Users|home)[\\/]+|/(?:home|Users)/", text, re.IGNORECASE
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check handoff/images only; no predictions or inference",
    )
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists")
    if args.preflight == bool(args.predictions):
        parser.error("Choose --preflight or supply --predictions")
    try:
        if args.preflight:
            report = preflight_report(args.protocol, args.manifest)
            code = 0 if report["status"] == "ready" else 1
        else:
            report = analyze(args.protocol, args.manifest, args.predictions)
            code = 0 if report["status"] == "complete_pending_independent_review" else 1
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as exc:
        reason = (
            str(exc)
            if not isinstance(exc, OSError)
            else "Required input file is missing or unreadable"
        )
        report = {
            "status": "invalid_handoff",
            "error_type": type(exc).__name__,
            "reason": "Invalid input; see local stderr"
            if _has_personal_path(reason)
            else reason,
            "inference_performed": False,
        }
        # OSError strings can contain personal paths; keep diagnostics local to stderr.
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    print(f"{report['status']}: {args.output.name}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
