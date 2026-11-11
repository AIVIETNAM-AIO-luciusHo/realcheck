"""Filter, split and train the November expansion without reusing opened tests."""

import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

from models.clip_input import encode_images, feature_contract, load_encoder
from models.extract_features import load_features, sha256_file
from models.normalize import NORMALIZATION_VERSION
from models.run_info import run_info
from models.score import Scorer, load_bundle
from models.train import metrics, train
from scripts.check_data import dhash
from scripts.download_expansion import records, save_json

PHOTO = [
    "a photograph of a real world scene",
    "a photograph of a person or a human face",
    "a photograph of objects, animals or food",
    "a photograph of a landscape or a city street",
]
ART = [
    "an anime illustration",
    "a cartoon drawing",
    "a painting or digital artwork",
    "a screenshot of a computer screen or a video game",
    "a poster, a meme or a page of text",
    "a 3D rendered cartoon character",
    "a stylized digital illustration",
    "a flat graphic design or a product mockup",
    "a book cover or an advertisement with text",
]
TOPICS = [
    "a photograph of a person's face or a human portrait",
    "a photograph of a natural landscape, mountains, lake or forest",
    "a photograph of an animal or a bird",
    "a photograph of objects, vehicles, food or a room interior",
    "a photograph of buildings or a city street",
]
QUOTAS = {
    "tiny/real": 2300,
    "tiny/adm": 400,
    "tiny/glide": 400,
    "tiny/midjourney": 400,
    "tiny/sd15": 400,
    "tiny/wukong": 400,
    "openfake/real": 1180,
    "openfake/ai": 1770,
    "community/coco": 885,
    "community/vision": 590,
    "community/ffhq": 470,
    "community/landscapeshq": 415,
    "community/portrait_ai": 470,
    "community/landscape_ai": 355,
    "community/diffusion_ai": 1300,
}
FIELDS = ["filepath", "label", "source", "split", "raw_path", "norm_version"]


class HashTree:
    """BK tree for conservative dHash leakage screening, Hamming radius four."""

    def __init__(self):
        self.root = None

    def add(self, value):
        if self.root is None:
            self.root = (value, {})
            return
        node = self.root
        while True:
            distance = (node[0] ^ value).bit_count()
            if distance == 0:
                return
            if distance not in node[1]:
                node[1][distance] = (value, {})
                return
            node = node[1][distance]

    def near(self, value, radius=4):
        stack = [self.root] if self.root else []
        while stack:
            current, children = stack.pop()
            distance = (current ^ value).bit_count()
            if distance <= radius:
                return True
            stack.extend(
                child
                for edge, child in children.items()
                if abs(edge - distance) <= radius
            )
        return False


def rank(row):
    return hashlib.sha256(("42:" + row["uid"]).encode()).hexdigest()


def device(row):
    match = re.match(r"(D\d{2})_", row.get("image_name", ""))
    return match[1] if match else None


def metadata_eligible(row):
    if row.get("nsfw_flag"):
        return False
    name = row.get("model", row.get("model_name", "")).lower()
    if any(token in name for token in ("biggan", "vqdm", "vq-diffusion")):
        return False
    if row["stratum"].startswith("openfake/"):
        if row.get("type", "").lower() == "video":
            return False
        if any(
            token in name
            for token in (
                "anime",
                "animagine",
                "illustrious",
                "pony",
                "waifu",
                "hentai",
            )
        ):
            return False
    return True


def model_key(row):
    name = row.get("model", row.get("model_name", row.get("source", "")))
    name = name.removeprefix("genimage_").rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]", "", name.lower())


def categories(row):
    key = row["stratum"]
    if key in {"openfake/laion", "openfake/pexels"}:
        return ["openfake/real"]
    if key != "community/ai":
        return [key] if key in QUOTAS else []
    result = []
    if row["topic"] == 0:
        result.append("community/portrait_ai")
    if row["topic"] == 1:
        result.append("community/landscape_ai")
    architecture = row.get("architecture", "").lower()
    if (
        "diffusion" in architecture
        or "stable" in architecture
        or "laion" in row.get("real_source", "").lower()
    ):
        result.append("community/diffusion_ai")
    return result


def assign_splits(rows):
    vision_devices = {device(r) for r in rows if r["stratum"] == "community/vision"}
    if None in vision_devices:
        raise ValueError("VISION device identity missing")
    vision_devices = sorted(vision_devices)
    random.Random(42).shuffle(vision_devices)
    validation_devices = set(vision_devices[:5])
    buckets = defaultdict(list)
    for row in rows:
        row["split"] = "train"
        row["cohort"] = "expanded_train"
        if row["stratum"].startswith("tiny/"):
            continue
        if row["stratum"] == "community/vision":
            if device(row) in validation_devices:
                row.update(split="val", cohort="new_validation")
            continue
        buckets[row["selection_group"]].append(row)
    for bucket in buckets.values():
        for row in sorted(bucket, key=rank)[: round(len(bucket) * 0.15)]:
            row.update(split="val", cohort="new_validation")
    return sorted(validation_devices)


def embeddings(rows, output, encoder, old_labels, old_features, reuse_cache=None):
    identity = {
        "uids": [r["uid"] for r in rows],
        "images": [r["normalized_sha256"] for r in rows],
        "contract": feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
    }
    index = output / "pool-feature-index.json"
    path = output / "pool-features.npy"
    if index.exists():
        if json.loads(index.read_text("utf-8")) != identity:
            raise ValueError("Pool or embedding contract changed; use a new output")
        values = np.lib.format.open_memmap(path, mode="r+")
    else:
        cached = {}
        if not (reuse_cache and (reuse_cache / "pool-features.npy.sha256").exists()):
            old_values, _, manifest = load_features(old_labels, old_features)
            cached.update(zip(manifest["image_sha256"], old_values))
        if reuse_cache and (reuse_cache / "pool-features.npy.sha256").exists():
            reused_path = reuse_cache / "pool-features.npy"
            reused_index = json.loads(
                (reuse_cache / "pool-feature-index.json").read_text("utf-8")
            )
            if (
                reused_index["contract"] != feature_contract()
                or reused_index["norm_version"] != NORMALIZATION_VERSION
            ):
                raise ValueError("Incompatible reused feature cache")
            if (
                sha256_file(reused_path)
                != reused_path.with_suffix(".npy.sha256").read_text().strip()
            ):
                raise ValueError("Reused feature checksum mismatch")
            reused_values = np.load(reused_path, allow_pickle=False)
            if (
                reused_values.dtype != np.float32
                or reused_values.shape != (len(reused_index["images"]), 512)
                or not np.isfinite(reused_values).all()
                or not np.allclose(np.linalg.norm(reused_values, axis=1), 1, atol=1e-5)
            ):
                raise ValueError("Invalid reused feature vectors")
            cached.update(zip(reused_index["images"], reused_values))
        values = np.lib.format.open_memmap(
            path, mode="w+", dtype=np.float32, shape=(len(rows), 512)
        )
        values[:] = np.nan
        for i, row in enumerate(rows):
            if row["normalized_sha256"] in cached:
                values[i] = cached[row["normalized_sha256"]]
        values.flush()
        save_json(index, identity)
        print(f"Reused {np.isfinite(values[:, 0]).sum()} CLIP vectors", flush=True)
    missing = np.flatnonzero(~np.isfinite(values).all(axis=1))
    for start in range(0, len(missing), 32):
        indices = missing[start : start + 32]
        images = []
        for i in indices:
            with Image.open(rows[i]["filepath"]) as image:
                images.append(image.copy())
        values[indices] = encode_images(images, encoder)
        values.flush()
        if start % 320 == 0 or start + 32 >= len(missing):
            print(
                f"CLIP additional {min(start + 32, len(missing))}/{len(missing)}",
                flush=True,
            )
    if not np.isfinite(values).all() or not np.allclose(
        np.linalg.norm(values, axis=1), 1, atol=1e-5
    ):
        raise ValueError("Invalid pool embeddings")
    path.with_suffix(".npy.sha256").write_text(
        sha256_file(path) + "\n", encoding="ascii"
    )
    return values


def fingerprints(row):
    with Image.open(row["filepath"]) as image:
        return hashlib.sha256(image.convert("RGB").tobytes()).hexdigest(), dhash(image)


def protected(manifests):
    pixels, tree, all_history = set(), HashTree(), HashTree()
    for path in manifests:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                if row["source"].startswith("cifake_"):
                    continue
                digest, value = fingerprints(row)
                all_history.add(value)
                if row["split"] != "train":
                    pixels.add(digest)
                    tree.add(value)
    return pixels, tree, all_history


def select(rows, values, text_vectors, history, output):
    protected_pixels, protected_tree, all_history = history
    photo_n, art_n = len(PHOTO), len(ART)
    similarity = values @ text_vectors.T
    for i, row in enumerate(rows):
        row["photo_margin"] = float(
            similarity[i, :photo_n].max()
            - similarity[i, photo_n : photo_n + art_n].max()
        )
        row["topic"] = int(similarity[i, photo_n + art_n :].argmax())
        row["feature_index"] = i
        if "dhash" not in row or "pixel_sha256" not in row:
            row["pixel_sha256"], row["dhash"] = fingerprints(row)
    seen_pixels, seen_near = set(), HashTree()
    evaluation, reasons = [], Counter()
    # Reserve evaluation images first; metadata/sample ranks never use detector scores.
    for cohort, n in (("core_test", 520), ("reddit_test", 420)):
        count = Counter()
        for row in sorted((r for r in rows if r["stratum"] == cohort), key=rank):
            label = row["label"]
            if count[label] >= n:
                continue
            if (
                row["pixel_sha256"] in protected_pixels
                or all_history.near(row["dhash"])
                or seen_near.near(row["dhash"])
            ):
                reasons["evaluation_duplicate_or_history"] += 1
                continue
            count[label] += 1
            row.update(split="test", cohort=cohort)
            evaluation.append(row)
            seen_pixels.add(row["pixel_sha256"])
            seen_near.add(row["dhash"])
        if count[0] < n or count[1] < n:
            raise ValueError(
                f"Insufficient untouched evaluation images: {cohort} {count}"
            )
    heldout_models = {model_key(r) for r in evaluation if r["label"] == 1}
    eligible = []
    for row in sorted((r for r in rows if r["upstream_split"] == "train"), key=rank):
        if row["label"] == 1 and model_key(row) in heldout_models:
            reasons["heldout_openfake_tool"] += 1
        elif not metadata_eligible(row):
            reasons["metadata_anime_video_or_flagged"] += 1
        elif row["photo_margin"] < 0:
            reasons["clip_nonphotographic"] += 1
        elif row["pixel_sha256"] in protected_pixels or protected_tree.near(
            row["dhash"]
        ):
            reasons["protected_validation_or_test"] += 1
        elif row["pixel_sha256"] in seen_pixels or seen_near.near(row["dhash"]):
            reasons["duplicate_or_near_duplicate"] += 1
        else:
            eligible.append(row)
            seen_pixels.add(row["pixel_sha256"])
            seen_near.add(row["dhash"])
    selected, counts, models, devices = [], Counter(), Counter(), Counter()
    # Photo/landscape AI have separate requested maxima; every Community tool stays <=10.
    for key, quota in QUOTAS.items():
        candidates = [
            r for r in eligible if not r.get("selection_group") and key in categories(r)
        ]
        if key.startswith("tiny/"):
            buckets = defaultdict(list)
            for row in candidates:
                buckets[row["parquet"]].append(row)
            candidates = []
            while any(buckets.values()):
                for name in sorted(buckets):
                    if buckets[name]:
                        candidates.append(buckets[name].pop())
        for row in candidates:
            if counts[key] >= quota:
                break
            if row["stratum"] == "community/ai" and models[model_key(row)] >= 10:
                continue
            if key == "community/vision":
                dev = device(row)
                if dev is None or devices[dev] >= (17 if int(dev[1:]) <= 30 else 16):
                    continue
                devices[dev] += 1
            row["selection_group"] = key
            selected.append(row)
            counts[key] += 1
            if row["stratum"] == "community/ai":
                models[model_key(row)] += 1
    validation_devices = assign_splits(selected)
    if any(r["split"] != "train" for r in selected if r["stratum"].startswith("tiny/")):
        raise AssertionError("Tiny leaked into validation")
    if len(devices) != 35:
        raise ValueError(f"VISION has only {len(devices)} usable devices")
    selected += evaluation
    with (output / "selection.jsonl").open("x", encoding="utf-8") as stream:
        for row in selected:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "selected_by_group": {k: counts[k] for k in QUOTAS},
        "maxima": QUOTAS,
        "below_maximum": {k: n - counts[k] for k, n in QUOTAS.items() if counts[k] < n},
        "splits": dict(Counter(r["cohort"] for r in selected)),
        "rejections": dict(reasons),
        "vision_devices": dict(devices),
        "vision_validation_devices": validation_devices,
        "community_tools": len(models),
        "community_max_images_per_tool": max(models.values(), default=0),
        "tiny_shards_by_group": {
            key: dict(
                Counter(
                    r["parquet"] for r in selected if r.get("selection_group") == key
                )
            )
            for key in QUOTAS
            if key.startswith("tiny/")
        },
        "filter": "fixed CLIP photo-vs-art prompts, margin>=0; automatic screen, not human QA",
        "photo_prompts": PHOTO,
        "art_prompts": ART,
        "topic_prompts": TOPICS,
        "heldout_openfake_tool_names": sorted(heldout_models),
        "tool_identity_limit": "Exact normalized names screened across sources; unknown aliases and shared base architectures still require review",
    }
    save_json(output / "selection-summary.json", summary)
    return selected


def write_training_manifest(
    selected, values, output, baseline_labels, baseline_features
):
    old_values, old_rows, _ = load_features(baseline_labels, baseline_features)
    rows, vectors = [], []
    for row in selected:
        # OpenFake audits are saved separately and never enter the training manifest.
        if row["cohort"] not in {"expanded_train", "new_validation"}:
            continue
        rows.append(
            {
                **{field: row[field] for field in FIELDS if field in row},
                "norm_version": NORMALIZATION_VERSION,
            }
        )
        vectors.append(values[row["feature_index"]])
    for i, row in enumerate(old_rows):
        if row["source"].startswith("genimage_") and row["split"] in {"val", "test"}:
            rows.append(row)
            vectors.append(old_values[i])
    labels = output / "labels.csv"
    with labels.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({key: row[key] for key in FIELDS} for row in rows)
    directory = output / "features"
    directory.mkdir()
    feature_path = directory / "features.npy"
    np.save(feature_path, np.asarray(vectors, dtype=np.float32), allow_pickle=False)
    manifest = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "labels_norm_version": NORMALIZATION_VERSION,
        "rows": len(rows),
        "order": [r["filepath"] for r in rows],
        "labels_sha256": sha256_file(labels),
        "image_sha256": [sha256_file(Path(r["filepath"])) for r in rows],
        "features_sha256": sha256_file(feature_path),
    }
    save_json(directory / "manifest.json", manifest)
    return labels, directory


def compare(scorers, x, rows):
    result = {}
    predictions = {}
    for name, scorer in scorers.items():
        probabilities = scorer.predict_features(x)
        predictions[name] = probabilities
        groups = {"all": np.ones(len(rows), dtype=bool)}
        for field in ("source", "cohort"):
            for key in sorted({r.get(field, "genimage_validation") for r in rows}):
                groups[key] = np.array(
                    [r.get(field, "genimage_validation") == key for r in rows]
                )
        result[name] = {
            key: metrics(
                np.array([int(r["label"]) for r in rows])[mask],
                probabilities[mask],
                0.5,
            )
            for key, mask in groups.items()
        }
    return result, predictions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--downloads", type=Path, required=True)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Stop after writing the screened train/validation manifests, before fitting or test scores",
    )
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    provenance = run_info("scripts.train_expansion")
    provenance["source_sha256"] = {
        name: sha256_file(Path(name))
        for name in (
            "scripts/train_expansion.py",
            "models/data_sources.py",
            "models/train.py",
            "models/extract_features.py",
            "models/clip_input.py",
            "models/normalize.py",
            "models/score.py",
        )
    }
    baseline_labels = Path("../outputs/realcheck-preserved-split/labels.csv")
    baseline_features = Path("../outputs/realcheck-ml-final-run/features")
    baseline_model = Path("../outputs/realcheck-ml-final-run/genimage.joblib")
    policy = {
        "seed": 42,
        "quotas": QUOTAS,
        "dataset": "realcheck_mixed_v3",
        "training": "retrain LogisticRegression; frozen CLIP; no old train rows",
        "C_grid": [0.01, 0.1, 1, 10, 100],
        "C_selection": "accuracy on pooled unchanged GenImage validation plus separate new-source validation",
        "thresholds": {"binary": 0.5, "low": 0.3, "high": 0.7},
        "baseline_model_sha256": sha256_file(baseline_model),
        "baseline_labels_sha256": sha256_file(baseline_labels),
        "photo_prompts": PHOTO,
        "art_prompts": ART,
        "topic_prompts": TOPICS,
        "test_use": "OpenFake core/reddit once after freezing; old GenImage test not evaluated",
        "baseline_scope": "Existing local candidate and 871 GenImage validation rows; newer team baseline/manifests not available",
    }
    policy_path = output / "policy.json"
    if policy_path.exists() and json.loads(policy_path.read_text("utf-8")) != policy:
        raise ValueError("Policy changed; use a new run directory")
    save_json(policy_path, policy)
    rows = sorted(
        (
            r
            for r in records(args.downloads / "pool.jsonl")
            if r["status"] == "candidate"
        ),
        key=lambda r: r["uid"],
    )
    for row in rows:
        if sha256_file(Path(row["filepath"])) != row["normalized_sha256"]:
            raise ValueError("Downloaded normalized image changed")
    encoder = load_encoder()
    text_vectors = encoder.encode(
        PHOTO + ART + TOPICS, convert_to_numpy=True, normalize_embeddings=True
    )
    reuse_cache = output.parent / "extended-features"
    if not (reuse_cache / "pool-features.npy.sha256").exists():
        reuse_cache = output.parent / "base-features"
    values = embeddings(
        rows,
        output,
        encoder,
        Path("../outputs/realcheck-domain-expansion/acquired-01/labels.csv"),
        Path("../outputs/realcheck-domain-expansion/features-01"),
        reuse_cache=reuse_cache,
    )
    selection_path = output / "selection.jsonl"
    selected = (
        list(records(selection_path))
        if selection_path.exists()
        else select(
            rows,
            values,
            text_vectors,
            protected([baseline_labels, Path(".cache/ml-run/labels.csv")]),
            output,
        )
    )
    if not (output / "labels.csv").exists():
        write_training_manifest(
            selected, values, output, baseline_labels, baseline_features
        )
    labels, directory = output / "labels.csv", output / "features"
    if args.prepare_only:
        load_features(labels, directory)
        print(
            "Prepared and checked manifests; no classifier fitted or test scores read",
            flush=True,
        )
        return
    model = output / "mixed-v3.joblib"
    if not model.exists():
        report = train(
            labels, directory, "realcheck_mixed_v3", model, binary_threshold=0.5
        )
        report["run"] = provenance
        save_json(output / "training.json", report)
    x, manifest_rows, _ = load_features(labels, directory)
    candidate = load_bundle(model)
    baseline = load_bundle(baseline_model)
    scorers = {
        "baseline": Scorer(baseline["probe"], None),
        "candidate": Scorer(candidate["probe"], None),
    }
    val_indices = [i for i, row in enumerate(manifest_rows) if row["split"] == "val"]
    new_paths = {r["filepath"] for r in selected if r["cohort"] == "new_validation"}
    val_rows = [
        {
            **manifest_rows[i],
            "cohort": "new_validation"
            if manifest_rows[i]["filepath"] in new_paths
            else "genimage_validation",
        }
        for i in val_indices
    ]
    validation, _ = compare(scorers, x[val_indices], val_rows)
    save_json(output / "validation-comparison.json", validation)
    freeze = {
        "model_sha256": sha256_file(model),
        "baseline_model_sha256": sha256_file(baseline_model),
        "labels_sha256": sha256_file(labels),
        "policy_sha256": sha256_file(policy_path),
        "selection_sha256": sha256_file(selection_path),
        "thresholds": candidate["thresholds"],
        "selected_C": candidate["metadata"]["C"],
        "authorization": "user requested download and training; experimental evaluation only",
        "release_approved": False,
        "independent_qa_approved": False,
    }
    freeze_path = output / "frozen-model.json"
    if freeze_path.exists() and json.loads(freeze_path.read_text("utf-8")) != freeze:
        raise ValueError("Frozen model or data changed")
    save_json(freeze_path, freeze)
    audit_path = output / "openfake-evaluation.json"
    if not audit_path.exists():
        with (output / "openfake-test-used.json").open("x", encoding="utf-8") as stream:
            json.dump(
                {"freeze_sha256": sha256_file(freeze_path), "run": provenance}, stream
            )
        audits = [r for r in selected if r["split"] == "test"]
        audit_x = values[[r["feature_index"] for r in audits]]
        evaluation, scores = compare(scorers, audit_x, audits)
        save_json(audit_path, evaluation)
        with (output / "openfake-predictions.csv").open(
            "x", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                ["uid", "cohort", "label", "model", "baseline_score", "candidate_score"]
            )
            for i, row in enumerate(audits):
                writer.writerow(
                    [
                        row["uid"],
                        row["cohort"],
                        row["label"],
                        row["model"],
                        float(scores["baseline"][i]),
                        float(scores["candidate"][i]),
                    ]
                )
    save_json(
        output / "run.json",
        {
            **provenance,
            "model_sha256": sha256_file(model),
            "old_genimage_test_evaluated": False,
            "release_approved": False,
        },
    )
    print(
        json.dumps(
            {
                "C": candidate["metadata"]["C"],
                "validation": validation,
                "output": str(output),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
