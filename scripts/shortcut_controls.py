"""ADV-10: locked JPEG/resample controls, train-only audit probes, validation only."""

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
from collections import Counter
from importlib.metadata import version
from io import BytesIO
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from PIL import Image, ImageOps
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from models.clip_input import CLIP_MODEL_ID, CLIP_REVISION, encode_images
from models.extract_features import sha256_file
from models.normalize import NORMALIZATION_VERSION, normalize_image
from models.run_info import run_info
from scripts.metadata_audit import CATEGORICAL, extract
from scripts.shortcut_metrics import summarize_probabilities, verdict

MODEL_SHA = "e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494"
LABELS_SHA = "4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad"
SOURCES = ("genimage_real", "genimage_glide", "genimage_midjourney", "genimage_sd14")
ARMS = ("B", "J", "R", "JR")
COUNTS = {
    source: {
        "train": 1888 if source == SOURCES[0] else 700,
        "val": 421 if source == SOURCES[0] else 150,
    }
    for source in SOURCES
}
DESIGN = {
    "arms": list(ARMS),
    "jpeg": {"quality": 95, "subsampling": 2, "progressive": False, "optimize": False},
    "resample": {"source": "genimage_glide", "size": [512, 512], "filter": "BICUBIC"},
    "order": ["exif_rgb", "resample_if_R", "jpeg_if_J", "normalization_v1"],
    "thresholds": {"binary": 0.5, "low": 0.3, "high": 0.7},
    "bootstrap": {"replicates": 2000, "seed": 42, "confidence": 0.95},
    "filesize": {
        "logreg_C": 1.0,
        "max_iter": 1000,
        "tree_depth": 3,
        "class_weight": "balanced",
    },
    "metadata": {
        "probe": "HistGradientBoostingClassifier",
        "seed": 42,
        "features": 13,
        "unknown_category": "missing",
    },
}
PACKAGES = (
    "pillow",
    "numpy",
    "pandas",
    "scikit-learn",
    "joblib",
    "torch",
    "transformers",
    "sentence-transformers",
)
LIMITATIONS = [
    "Diagnostic validation previously used for model/C selection; not an independent test.",
    "Only exact raw/pixel and supplied lineage duplicates are grouped; near-duplicates are not certified.",
    "Additional q95 JPEG does not reconstruct the unknown JPEG history of real images.",
    "GLIDE 256->512->256 is a controlled intervention, not the real-image acquisition history.",
    "Constant post metadata and A_eff=0.5 cannot establish absence of pixel/JPEG shortcuts.",
    "File-size separability does not prove CLIP directly uses file byte length.",
    "Bootstrap conditions on fitted probes and observed groups; singleton strata can yield narrow intervals.",
    "Exploratory comparisons do not establish causality or absence of all shortcuts.",
    "JPEG ghost/T027/KAN-46 deferred per issue #53; serving model/profile unchanged.",
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def invalid(value):
        raise ValueError(f"Non-finite JSON: {value}")

    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=invalid)


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def clean(value):
    """Pillow metadata has NaNs for non-JPEGs; JSON uses null, never NaN."""
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        return clean(value.item())
    return None if isinstance(value, float) and not np.isfinite(value) else value


def runtime():
    return {"python": platform.python_version(), **{p: version(p) for p in PACKAGES}}


def provenance():
    info = run_info("scripts.shortcut_controls")
    for key in ("command", "working_directory"):
        info.pop(key, None)
    require(
        info["git_commit"] is not None and info["git_dirty"] is False,
        "Commit code/tests first; a clean Git checkout is required",
    )
    return info


def relative(path, root):
    return Path(os.path.relpath(Path(path).resolve(), Path(root).resolve())).as_posix()


def load_protocol(path, *, locked=False):
    p = read_json(path)
    require(isinstance(p, dict) and p.get("schema_version") == 1, "Bad protocol schema")
    require(
        p.get("status") == ("locked" if locked else "proposed"), "Wrong protocol status"
    )
    require(
        p.get("design") == DESIGN,
        "Experiment design differs from fixed ADV-10 protocol",
    )
    require(
        p.get("profile")
        == {
            "clip_model_id": CLIP_MODEL_ID,
            "clip_revision": CLIP_REVISION,
            "normalization_version": NORMALIZATION_VERSION,
        },
        "Wrong feature/normalization profile",
    )
    require(p.get("runtime") == runtime(), "Runtime differs from protocol")
    require(
        p.get("exposure") and p.get("history_limitations"),
        "Missing exposure/history disclosure",
    )
    require(
        p.get("independent_qa_approved") is False, "Cannot self-approve independent QA"
    )
    require(p.get("expected_counts") == COUNTS, "Wrong cohort counts")
    base = Path(path).resolve().parent
    for key, expected in (("model", MODEL_SHA), ("labels", LABELS_SHA)):
        artifact = p[key]
        require(artifact["sha256"] == expected, f"Wrong {key} identity")
        require(
            sha256_file(base / artifact["path"]) == expected, f"{key} hash mismatch"
        )
    model = base / p["model"]["path"]
    require(
        model.with_suffix(model.suffix + ".sha256").read_text().strip() == MODEL_SHA,
        "Wrong raw model sidecar",
    )
    require(
        p.get("history"),
        "Supply historical manifests or explicitly resolve missing history",
    )
    for item in p["history"]:
        require(
            sha256_file(base / item["path"]) == item["sha256"], "History hash mismatch"
        )
    info = provenance()
    require(
        info["git_commit"] == p["code_commit"], "Checkout differs from protocol commit"
    )
    return p, info


def selected_rows(labels):
    """Filter by split before touching any image path, including invalid test paths."""
    with Path(labels).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [
        r for r in rows if r["source"] in SOURCES and r["split"] in {"train", "val"}
    ]
    require(bool(selected), "No GenImage train/validation rows")
    for r in selected:
        require(r["label"] in {"0", "1"}, "Invalid label")
        r["label"] = int(r["label"])
        require(r["label"] == int(r["source"] != SOURCES[0]), "Source/label conflict")
    return sorted(selected, key=lambda r: (r["source"], r["split"], r["raw_path"]))


def pixel_hash(image):
    image = ImageOps.exif_transpose(image).convert("RGB")
    return hashlib.sha256(str(image.size).encode() + image.tobytes()).hexdigest()


def assign_groups(rows):
    """Union raw, oriented RGB pixel and supplied lineage identities."""
    parent = list(range(len(rows)))
    seen = {}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, row in enumerate(rows):
        tokens = [("raw", row["raw_sha256"]), ("pixel", row["decoded_pixel_sha256"])]
        if row.get("lineage_group"):
            tokens.append(("lineage", row["lineage_group"]))
        for token in tokens:
            if token in seen:
                parent[find(i)] = find(seen[token])
            seen[token] = i
    members = {}
    for i, row in enumerate(rows):
        members.setdefault(find(i), []).append(row)
    for group in members.values():
        require(len({r["split"] for r in group}) == 1, "Group crosses train/val")
        require(len({r["label"] for r in group}) == 1, "Group has contradictory labels")
        gid = min(r["sample_id"] for r in group)
        for r in group:
            r["group_id"] = gid


def inventory(rows):
    output = {}
    for source in SOURCES:
        for split in ("train", "val"):
            subset = [r for r in rows if r["source"] == source and r["split"] == split]
            if not subset:
                continue
            output[f"{source}/{split}"] = {
                "n": len(subset),
                "formats": dict(Counter(r["format"] for r in subset)),
                "exact_256": sum(r["width"] == r["height"] == 256 for r in subset),
                "needs_resize_or_crop": sum(
                    (r["width"], r["height"]) != (256, 256) for r in subset
                ),
                "non_square_crop": sum(r["width"] != r["height"] for r in subset),
                "width_q025_25_50_75_975": np.percentile(
                    [r["width"] for r in subset], [2.5, 25, 50, 75, 97.5]
                ).tolist(),
                "height_q025_25_50_75_975": np.percentile(
                    [r["height"] for r in subset], [2.5, 25, 50, 75, 97.5]
                ).tolist(),
                "short_side_q025_25_50_75_975": np.percentile(
                    [min(r["width"], r["height"]) for r in subset],
                    [2.5, 25, 50, 75, 97.5],
                ).tolist(),
                "quantization_subsampling": dict(
                    Counter(
                        json.dumps(
                            {
                                k: r["raw_metadata"][k]
                                for k in ("subsampling", "q_luma_mean", "q_chroma_mean")
                            },
                            sort_keys=True,
                        )
                        for r in subset
                    )
                ),
            }
    return output


def history_exposure(rows, history, base):
    """Inspect CSV identities only; never open historical train/test images."""
    result = []
    for item in history:
        with (base / item["path"]).open(encoding="utf-8-sig", newline="") as handle:
            previous = list(csv.DictReader(handle))
        by_path = {}
        for row in previous:
            by_path.setdefault(row.get("raw_path", "").replace("\\", "/"), []).append(
                row
            )
        overlaps = Counter()
        for row in rows:
            for old in by_path.get(row["raw_path"], []):
                require(int(old["label"]) == row["label"], "Historical label conflict")
                overlaps[f"current_{row['split']}/historical_{old['split']}"] += 1
        result.append(
            {
                "history_sha256": item["sha256"],
                "path_identity_overlap": dict(overlaps),
                "limitation": "CSV path matches only; historical image bytes not opened or independently verified",
            }
        )
    return result


def effective_arm(source, arm):
    if source == SOURCES[0]:
        return "B"
    if source != "genimage_glide":
        return "J" if "J" in arm else "B"
    return arm


def intervention(image, arm):
    """Encode only for J; RGB/EXIF is idempotent with shared normalization."""
    image = ImageOps.exif_transpose(image).convert("RGB")
    if "R" in arm:
        image = image.resize((512, 512), Image.Resampling.BICUBIC)
    if "J" in arm:
        buffer = BytesIO()
        image.save(buffer, "JPEG", **DESIGN["jpeg"])
        data = buffer.getvalue()
        with Image.open(BytesIO(data)) as decoded:
            image = decoded.copy()
        return image, data, ".jpg"
    if arm == "R":
        buffer = BytesIO()
        image.save(buffer, "PNG")
        return image, buffer.getvalue(), ".png"
    return image, None, None


def describe(path):
    return {
        "sha256": sha256_file(path),
        "size_bytes": Path(path).stat().st_size,
        "metadata": clean(extract(str(path))),
    }


def prepare(protocol_path, output):
    p, info = load_protocol(protocol_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = Path(protocol_path).resolve().parent
    root = (base / p["dataset_root"]).resolve()
    labels = base / p["labels"]["path"]
    rows, errors = [], []
    for row in selected_rows(labels):
        raw = (root / row["raw_path"]).resolve()
        require(raw.is_relative_to(root), "Raw image outside dataset root")
        try:
            raw_sha = sha256_file(raw)
            with Image.open(raw) as image:
                image.load()
                oriented = ImageOps.exif_transpose(image)
                require(min(oriented.size) >= 256, "IMAGE_TOO_SMALL")
                width, height = oriented.size
                pixels = pixel_hash(image)
                fmt = image.format
            identity = hashlib.sha256((row["raw_path"] + raw_sha).encode()).hexdigest()
            rows.append(
                {
                    "sample_id": identity,
                    "source": row["source"],
                    "label": row["label"],
                    "split": row["split"],
                    "raw_path": relative(raw, root),
                    "raw_sha256": raw_sha,
                    "raw_size_bytes": raw.stat().st_size,
                    "decoded_pixel_sha256": pixels,
                    "width": width,
                    "height": height,
                    "format": fmt,
                    "lineage_group": row.get("group_id"),
                    "raw_metadata": clean(extract(str(raw))),
                }
            )
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            errors.append(
                {
                    "raw_path": row["raw_path"],
                    "source": row["source"],
                    "split": row["split"],
                    "error_code": "IMAGE_TOO_SMALL"
                    if str(error) == "IMAGE_TOO_SMALL"
                    else "INVALID_IMAGE",
                }
            )
    counts = {
        s: dict(Counter(r["split"] for r in rows if r["source"] == s)) for s in SOURCES
    }
    write_json(output / "inventory.json", inventory(rows))
    write_json(
        output / "preflight.json", {"counts": counts, "errors": errors, "run": info}
    )
    require(
        not errors and counts == p["expected_counts"],
        "Preflight errors/count mismatch; inspect retained preflight.json",
    )
    require(len({r["sample_id"] for r in rows}) == len(rows), "Duplicate sample ID")
    assign_groups(rows)
    write_json(
        output / "history-exposure.json", history_exposure(rows, p["history"], base)
    )
    require(
        all(
            (r["width"], r["height"]) == (256, 256)
            for r in rows
            if r["source"] == "genimage_glide"
        ),
        "GLIDE is not entirely 256x256; re-lock protocol before R/JR",
    )
    records = []
    for index, row in enumerate(rows):
        raw = root / row["raw_path"]
        require(sha256_file(raw) == row["raw_sha256"], "Raw mutated during preparation")
        variants = {}
        with Image.open(raw) as original:
            original.load()
            for arm in ARMS:
                effective = effective_arm(row["source"], arm)
                if effective not in variants:
                    folder = output / "images" / row["sample_id"] / effective
                    folder.mkdir(parents=True)
                    image, data, extension = intervention(original, effective)
                    middle = raw
                    if data is not None:
                        middle = folder / ("intervention" + extension)
                        middle.write_bytes(data)
                    normalized = normalize_image(image)
                    post = folder / "post.jpg"
                    post.write_bytes(normalized.jpeg)
                    variants[effective] = {
                        "intervention": {
                            "path": relative(middle, output),
                            **describe(middle),
                        },
                        "post": {"path": relative(post, output), **describe(post)},
                    }
                records.append(
                    {
                        "sample_id": row["sample_id"],
                        "arm": arm,
                        "effective_arm": effective,
                        **variants[effective],
                    }
                )
        if index % 250 == 0:
            print(f"prepare {index + 1}/{len(rows)}", flush=True)
    write_json(output / "samples.json", rows)
    write_json(output / "variants.json", records)
    artifacts = {
        name: sha256_file(output / name)
        for name in (
            "inventory.json",
            "preflight.json",
            "samples.json",
            "variants.json",
            "history-exposure.json",
        )
    }
    # Rebase paths for a portable lock; never serialize personal absolute paths.
    locked = dict(
        p,
        status="locked",
        prepared_artifacts=artifacts,
        dataset_root=relative(root, output),
    )
    for key in ("model", "labels"):
        locked[key] = {**p[key], "path": relative(base / p[key]["path"], output)}
    locked["history"] = [
        {**h, "path": relative(base / h["path"], output)} for h in p["history"]
    ]
    for row in rows:
        require(
            sha256_file(root / row["raw_path"]) == row["raw_sha256"],
            "Raw mutated during preparation",
        )
    load_protocol(protocol_path)
    write_json(output / "protocol.json", locked)
    print(f"Prepared {len(rows)} originals; protocol locked before scoring", flush=True)


def validate_prepared(protocol_path, prepared):
    p, info = load_protocol(protocol_path, locked=True)
    prepared = Path(prepared).resolve()
    require(
        Path(protocol_path).resolve() == prepared / "protocol.json",
        "Use the preparation's locked protocol",
    )
    for name, digest in p["prepared_artifacts"].items():
        require(sha256_file(prepared / name) == digest, f"Prepared {name} mutated")
    samples, variants = (
        read_json(prepared / "samples.json"),
        read_json(prepared / "variants.json"),
    )
    require(
        len({r["sample_id"] for r in samples}) == len(samples), "Duplicate prepared ID"
    )
    require(
        all(r["split"] in {"train", "val"} for r in samples),
        "Unexpected evaluation split",
    )
    require(len(variants) == len(samples) * len(ARMS), "Incomplete variant manifest")
    expected = {(r["sample_id"], arm) for r in samples for arm in ARMS}
    require(
        {(r["sample_id"], r["arm"]) for r in variants} == expected, "Wrong variant IDs"
    )
    root = (Path(protocol_path).parent / p["dataset_root"]).resolve()
    for row in samples:
        require(
            sha256_file(root / row["raw_path"]) == row["raw_sha256"],
            "Raw hash mismatch",
        )
    checked = set()
    for row in variants:
        for stage in ("intervention", "post"):
            item = row[stage]
            path = (prepared / item["path"]).resolve()
            if path not in checked:
                require(sha256_file(path) == item["sha256"], "Variant hash mismatch")
                checked.add(path)
    return p, info, samples, variants


def metadata_matrix(records, categories=None):
    frame = pd.DataFrame(records)
    if categories is None:
        categories = {c: sorted(frame[c].dropna().unique()) for c in CATEGORICAL}
        # An entirely absent train feature carries no information. Keep its column
        # constant; sklearn 1.9.1 cannot bin an all-NaN numeric column.
        categories["_empty_numeric"] = [
            c for c in frame.columns.difference(CATEGORICAL) if frame[c].isna().all()
        ]
    for column in CATEGORICAL:
        known = frame[column].where(frame[column].isin(categories[column]))
        frame[column] = pd.Categorical(known, categories=categories[column])
    for column in frame.columns.difference(CATEGORICAL):
        frame[column] = (
            0
            if column in categories["_empty_numeric"]
            else pd.to_numeric(frame[column], errors="raise")
        )
    return frame, categories


def audit_probes(samples, variants):
    """Save validation probabilities from pre-registered probes, never test."""
    indexed = {(r["sample_id"], r["arm"]): r for r in variants}
    predictions, diagnostics = [], {}
    for ai_source in SOURCES[1:]:
        subset = [r for r in samples if r["source"] in (SOURCES[0], ai_source)]
        train = np.array([r["split"] == "train" for r in subset])
        val = ~train
        y = np.array([r["label"] for r in subset])

        def features(arm, stage, probe, subset=subset, train=train):
            items = [
                (
                    {"metadata": r["raw_metadata"], "size_bytes": r["raw_size_bytes"]}
                    if stage == "raw"
                    else indexed[r["sample_id"], arm][stage]
                )
                for r in subset
            ]
            if probe != "metadata":
                return np.log(np.array([[r["size_bytes"] / 1024] for r in items])), None
            records = [r["metadata"] for r in items]
            _, categories = metadata_matrix([records[i] for i in np.flatnonzero(train)])
            return metadata_matrix(records, categories)

        for stage in ("raw", "post"):
            for name in ("logreg", "tree_depth3", "metadata"):
                fitted = {}
                for arm in ("B",) if stage == "raw" else ARMS:
                    x, _ = features(arm, stage, name)
                    if name == "logreg":
                        probe = LogisticRegression(
                            C=1, class_weight="balanced", solver="lbfgs", max_iter=1000
                        )
                    elif name == "tree_depth3":
                        probe = DecisionTreeClassifier(
                            max_depth=3, class_weight="balanced", random_state=42
                        )
                    else:
                        probe = HistGradientBoostingClassifier(
                            categorical_features="from_dtype", random_state=42
                        )
                    probe.fit(
                        x.loc[train] if isinstance(x, pd.DataFrame) else x[train],
                        y[train],
                    )
                    fitted[arm] = (probe, x)
                for arm in ("B",) if stage == "raw" else ARMS:
                    for mode in ("refit",) if stage == "raw" else ("fixed", "refit"):
                        probe = fitted["B" if mode == "fixed" else arm][0]
                        x, _ = features(arm, stage, name)
                        # Categories for a frozen probe must come only from B/train.
                        if name == "metadata" and mode == "fixed":
                            baseline_records = [
                                indexed[r["sample_id"], "B"]["post"]["metadata"]
                                for r in subset
                            ]
                            _, categories = metadata_matrix(
                                [baseline_records[i] for i in np.flatnonzero(train)]
                            )
                            x, _ = metadata_matrix(
                                [
                                    indexed[r["sample_id"], arm]["post"]["metadata"]
                                    for r in subset
                                ],
                                categories,
                            )
                        values = probe.predict_proba(
                            x.loc[val] if isinstance(x, pd.DataFrame) else x[val]
                        )[:, 1]
                        for row, value in zip(
                            (r for r in subset if r["split"] == "val"), values
                        ):
                            predictions.append(
                                {
                                    "sample_id": row["sample_id"],
                                    "pair": ai_source,
                                    "probe": name,
                                    "stage": stage,
                                    "arm": arm,
                                    "mode": mode,
                                    "score": float(value),
                                }
                            )
                        if name == "metadata":
                            key = f"{ai_source}/{stage}/{arm}"
                            diagnostics[key] = {
                                "constant_features": [
                                    c for c in x if x[c].nunique(dropna=False) <= 1
                                ]
                            }
                # Controls diagnose the extractor/probe, without changing its gate.
                if name == "metadata":
                    x = fitted["B"][1]
                    positive = HistGradientBoostingClassifier(
                        categorical_features="from_dtype", random_state=42
                    )
                    with_label = x.assign(control=y)
                    positive.fit(with_label.loc[train], y[train])
                    pos = positive.predict_proba(with_label.loc[val])[:, 1]
                    groups = [r["group_id"] for r in subset]
                    shuffled = y.copy()
                    rng = np.random.default_rng(42)
                    for mask in (train, val):
                        unique = sorted({groups[i] for i in np.flatnonzero(mask)})
                        labels = [y[groups.index(group)] for group in unique]
                        permuted = dict(zip(unique, rng.permutation(labels)))
                        for i in np.flatnonzero(mask):
                            shuffled[i] = permuted[groups[i]]
                    negative = HistGradientBoostingClassifier(
                        categorical_features="from_dtype", random_state=42
                    )
                    negative.fit(x.loc[train], shuffled[train])
                    neg = negative.predict_proba(x.loc[val])[:, 1]
                    from sklearn.metrics import roc_auc_score

                    a = float(roc_auc_score(shuffled[val], neg))
                    diagnostics[f"{ai_source}/{stage}/controls"] = {
                        "positive_auroc": float(roc_auc_score(y[val], pos)),
                        "negative_a_eff": max(a, 1 - a),
                        "negative_label_shuffle": "whole groups, independently within train and val",
                        "gate_approved": False,
                    }
        print(f"audit complete: {ai_source}", flush=True)
    return predictions, diagnostics


def infer_validation(samples, variants, prepared, model_path, output):
    """Normalize occurred in prepare; score those exact decoded JPEG pixels once."""
    from models.score import load_scorer

    scorer = load_scorer(model_path, device="cpu")
    require(
        not scorer.encoder.training
        and all(not p.requires_grad for p in scorer.encoder.parameters()),
        "Encoder must be frozen/eval",
    )
    selected = {r["sample_id"]: r for r in samples if r["split"] == "val"}
    rows = [r for r in variants if r["sample_id"] in selected]
    cached, outcomes, parity = {}, [], {}
    started = perf_counter()
    for source in SOURCES:
        variant = next(
            r
            for r in rows
            if r["arm"] == "B" and selected[r["sample_id"]]["source"] == source
        )
        with Image.open(prepared / variant["post"]["path"]) as normalized:
            normalized.load()
            score = float(
                scorer.predict_features(encode_images([normalized], scorer.encoder))[0]
            )
        with Image.open(prepared / variant["intervention"]["path"]) as original:
            original.load()
            difference = abs(scorer(original) - score)
        require(difference <= 1e-5, "Scorer parity failure")
        parity[source] = difference
        cached[variant["post"]["sha256"]] = {
            "status": "ok",
            "score": score,
            "verdict": ("likely_real", "uncertain", "likely_ai")[int(verdict(score))],
            "error_code": "",
        }
        write_json(
            output / f"parity-{source}.json",
            {"sample_id": variant["sample_id"], "max_abs_difference": difference},
        )
    fields = [
        "sample_id",
        "group_id",
        "parent_id",
        "source",
        "label",
        "split",
        "arm",
        "status",
        "score",
        "verdict",
        "error_code",
        "post_sha256",
    ]
    with (output / "predictions.csv").open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, variant in enumerate(rows):
            sample = selected[variant["sample_id"]]
            digest = variant["post"]["sha256"]
            if digest not in cached:
                try:
                    with Image.open(prepared / variant["post"]["path"]) as image:
                        image.load()
                        score = float(
                            scorer.predict_features(
                                encode_images([image], scorer.encoder)
                            )[0]
                        )
                    cached[digest] = {
                        "status": "ok",
                        "score": score,
                        "verdict": ("likely_real", "uncertain", "likely_ai")[
                            int(verdict(score))
                        ],
                        "error_code": "",
                    }
                except (OSError, ValueError, RuntimeError) as error:
                    cached[digest] = {
                        "status": "error",
                        "score": "",
                        "verdict": "",
                        "error_code": "INFERENCE_ERROR",
                    }
                    with (output / "inference-errors.log").open(
                        "a", encoding="utf-8"
                    ) as log:
                        log.write(
                            f"{sample['sample_id']}/{variant['arm']}: {type(error).__name__}: {error}\n"
                        )
            outcome = {
                k: sample[k]
                for k in ("sample_id", "group_id", "source", "label", "split")
            }
            outcome.update(
                arm=variant["arm"],
                parent_id=sample["sample_id"],
                post_sha256=digest,
                **cached[digest],
            )
            outcomes.append(outcome)
            writer.writerow(outcome)
            handle.flush()
            if index % 100 == 0:
                print(
                    f"inference {index + 1}/{len(rows)}, unique={len(cached)}, seconds={perf_counter() - started:.1f}",
                    flush=True,
                )
    return {
        "unique_post_inferences": len(cached),
        "logical_predictions": len(outcomes),
        "parity": parity,
        "seconds": perf_counter() - started,
        "warmup_calls": 1,
        "parity_extra_calls": len(parity),
    }


def run(protocol_path, prepared, output):
    require(
        os.environ.get("HF_HUB_OFFLINE") == "1"
        and os.environ.get("TRANSFORMERS_OFFLINE") == "1",
        "Provision cache first; offline environment flags are required",
    )
    p, info, samples, variants = validate_prepared(protocol_path, prepared)
    output, prepared = Path(output).resolve(), Path(prepared).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "run-start.json",
        {
            "protocol_sha256": sha256_file(protocol_path),
            "run": info,
            "prepared": relative(prepared, output),
            "status": "started",
            "runtime": runtime(),
        },
    )
    from models.score import load_bundle

    bundle = load_bundle(prepared / p["model"]["path"])
    require(bundle["thresholds"] == DESIGN["thresholds"], "Wrong model thresholds")
    for row in samples:
        row["raw_size_bytes"] = (
            ((prepared / p["dataset_root"]) / row["raw_path"]).stat().st_size
        )
    audits, diagnostics = audit_probes(samples, variants)
    write_json(output / "audit-predictions.json", audits)
    write_json(output / "audit-diagnostics.json", diagnostics)
    info_inference = infer_validation(
        samples, variants, prepared, prepared / p["model"]["path"], output
    )
    validate_prepared(protocol_path, prepared)
    checksums = {
        name: sha256_file(output / name)
        for name in (
            "run-start.json",
            "audit-predictions.json",
            "audit-diagnostics.json",
            "predictions.csv",
        )
    }
    write_json(
        output / "run-complete.json",
        {
            "status": "inference_finished_pending_analysis",
            "checksums": checksums,
            "inference": info_inference,
            "model_sha256_after": MODEL_SHA,
            "independent_qa_approved": False,
        },
    )


def summarize(run_dir, output):
    require(not Path(output).exists(), "Output already exists")
    run_dir = Path(run_dir).resolve()
    completed = read_json(run_dir / "run-complete.json")
    for name, digest in completed["checksums"].items():
        require(sha256_file(run_dir / name) == digest, f"Run artifact {name} changed")
    start = read_json(run_dir / "run-start.json")
    prepared = (run_dir / start["prepared"]).resolve()
    require(
        sha256_file(prepared / "protocol.json") == start["protocol_sha256"],
        "Protocol changed after scoring",
    )
    p = read_json(prepared / "protocol.json")
    analysis_info = provenance()
    require(
        analysis_info["git_commit"] == p["code_commit"],
        "Analyze with the locked code commit",
    )
    require(runtime() == p["runtime"], "Analysis runtime differs from protocol")
    for name, digest in p["prepared_artifacts"].items():
        require(sha256_file(prepared / name) == digest, f"Prepared {name} changed")
    samples = read_json(prepared / "samples.json")
    selected = {r["sample_id"]: r for r in samples if r["split"] == "val"}
    with (run_dir / "predictions.csv").open(encoding="utf-8", newline="") as handle:
        predictions = list(csv.DictReader(handle))
    expected = {(sid, arm) for sid in selected for arm in ARMS}
    require(
        len(predictions) == len(expected)
        and {(r["sample_id"], r["arm"]) for r in predictions} == expected,
        "Missing, duplicate or unexpected prediction ID",
    )
    indexed = {}
    post_hashes = {
        (r["sample_id"], r["arm"]): r["post"]["sha256"]
        for r in read_json(prepared / "variants.json")
    }
    for r in predictions:
        sample = selected[r["sample_id"]]
        require(
            all(
                str(r[k]) == str(sample[k])
                for k in ("group_id", "label", "source", "split")
            ),
            "Prediction lineage mismatch",
        )
        require(r["parent_id"] == r["sample_id"], "Prediction parent mismatch")
        require(
            r["post_sha256"] == post_hashes[r["sample_id"], r["arm"]],
            "Prediction image hash mismatch",
        )
        require(r["status"] in {"ok", "error"}, "Bad prediction status")
        if r["status"] == "ok":
            r["score"] = float(r["score"])
            require(np.isfinite(r["score"]) and 0 <= r["score"] <= 1, "Invalid score")
            require(
                r["verdict"]
                == ("likely_real", "uncertain", "likely_ai")[int(verdict(r["score"]))]
                and not r["error_code"],
                "Wrong verdict/error",
            )
        else:
            require(
                not r["score"]
                and not r["verdict"]
                and r["error_code"] == "INFERENCE_ERROR",
                "Invalid failure record",
            )
        indexed[r["sample_id"], r["arm"]] = r
    report = {
        "schema_version": 1,
        "issue": 59,
        "status": "measured_pending_independent_review",
        "evaluation_split": "validation",
        "model_sha256": MODEL_SHA,
        "source_labels_sha256": LABELS_SHA,
        "protocol_sha256": start["protocol_sha256"],
        "run": start["run"],
        "analysis_run": analysis_info,
        "runtime": start["runtime"],
        "design": DESIGN,
        "exposure": p["exposure"],
        "history_limitations": p["history_limitations"],
        "history_sha256": [h["sha256"] for h in p["history"]],
        "history_exposure": read_json(prepared / "history-exposure.json"),
        "independent_qa_approved": False,
        "release_approved": False,
        "shortcut_excluded": False,
        "limitations": LIMITATIONS,
        "inventory": read_json(prepared / "inventory.json"),
        "inference": completed["inference"],
        "model": {},
        "audit": {},
        "audit_diagnostics": read_json(run_dir / "audit-diagnostics.json"),
        "evidence_checksums": completed["checksums"],
    }
    for name in (*SOURCES, *[f"real_vs_{s}" for s in SOURCES[1:]]):
        rows = [
            r
            for r in selected.values()
            if r["source"] == name
            or (
                name.startswith("real_vs_")
                and r["source"] in (SOURCES[0], name.removeprefix("real_vs_"))
            )
        ]
        report["model"][name] = {}
        for arm in ARMS:
            scored = [r for r in rows if indexed[r["sample_id"], arm]["status"] == "ok"]
            failed = len(rows) - len(scored)
            result = (
                summarize_probabilities(
                    scored, [indexed[r["sample_id"], arm]["score"] for r in scored]
                )
                if scored
                else {"metrics": None, "reason": "no_valid_predictions"}
            )
            result.update(n_total=len(rows), n_scored=len(scored), n_failed=failed)
            matched = [
                r for r in scored if indexed[r["sample_id"], "B"]["status"] == "ok"
            ]
            if matched:
                paired = summarize_probabilities(
                    matched,
                    [indexed[r["sample_id"], arm]["score"] for r in matched],
                    [indexed[r["sample_id"], "B"]["score"] for r in matched],
                )
                result["paired"] = paired["paired"]
                result["paired"]["baseline_accuracy_matched"] = summarize_probabilities(
                    matched, [indexed[r["sample_id"], "B"]["score"] for r in matched]
                )["accuracy"]
                result["paired"]["child_accuracy_matched"] = paired["accuracy"]
            else:
                result["paired"] = None
            if failed:
                report["status"] = "partial"
            report["model"][name][arm] = result
    audit = read_json(run_dir / "audit-predictions.json")
    buckets = {}
    for row in audit:
        key = (row["pair"], row["stage"], row["probe"], row["mode"], row["arm"])
        require(row["sample_id"] in selected, "Audit ID not validation")
        bucket = buckets.setdefault(key, {})
        require(row["sample_id"] not in bucket, "Duplicate audit prediction")
        bucket[row["sample_id"]] = row["score"]
    expected_audits = {
        (pair, stage, probe, mode, arm)
        for pair in SOURCES[1:]
        for stage in ("raw", "post")
        for probe in ("logreg", "tree_depth3", "metadata")
        for mode in (("refit",) if stage == "raw" else ("fixed", "refit"))
        for arm in (("B",) if stage == "raw" else ARMS)
    }
    require(set(buckets) == expected_audits, "Missing or unexpected audit cells")
    for key, values in buckets.items():
        pair, stage, probe, mode, arm = key
        rows = [r for r in selected.values() if r["source"] in (SOURCES[0], pair)]
        require(set(values) == {r["sample_id"] for r in rows}, "Missing audit IDs")
        base = buckets[pair, stage, probe, mode, "B"]
        report["audit"]["/".join(key)] = summarize_probabilities(
            rows,
            [values[r["sample_id"]] for r in rows],
            [base[r["sample_id"]] for r in rows],
        )
    variants = read_json(prepared / "variants.json")
    stats = {}
    for source in SOURCES:
        for split in ("train", "val"):
            ids = {
                r["sample_id"]
                for r in samples
                if r["source"] == source and r["split"] == split
            }
            for arm in ARMS:
                for stage in ("intervention", "post"):
                    sizes = [
                        r[stage]["size_bytes"]
                        for r in variants
                        if r["sample_id"] in ids and r["arm"] == arm
                    ]
                    stats[f"{source}/{split}/{arm}/{stage}"] = {
                        "n": len(sizes),
                        "bytes_q25_50_75": np.percentile(sizes, [25, 50, 75]).tolist(),
                    }
    report["size_distributions"] = stats
    write_json(output, report)
    print(f"Analysis: {report['status']}; JSON saved", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "run", "summarize"):
        sub = commands.add_parser(name)
        sub.add_argument("--output", type=Path, required=True)
        if name != "summarize":
            sub.add_argument("--protocol", type=Path, required=True)
        if name == "run":
            sub.add_argument("--prepared", type=Path, required=True)
        if name == "summarize":
            sub.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.protocol, args.output)
        elif args.command == "run":
            run(args.protocol, args.prepared, args.output)
        else:
            report = summarize(args.run, args.output)
            return 1 if report["status"] == "partial" else 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f"ADV-10 stopped: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
