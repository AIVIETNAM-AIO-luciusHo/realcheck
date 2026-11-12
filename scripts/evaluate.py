"""Đánh giá model đã khóa trên một split, xuất báo cáo cho trang đánh giá (T013).

Không train và không chọn ngưỡng: công thức dùng lại models.train.metrics, ngưỡng lấy
từ model. Phải ghi rõ --split để không vô tình mở tập test; tập test chỉ chạy một lần
sau khi đã khóa model và ngưỡng, không ghi đè báo cáo đã có.

Cách chạy (từ thư mục gốc repo):
    python -m scripts.evaluate --split val --output artifacts/evaluation-val.json
    # GenImage test: use models.evaluate with its approved protocol.

Robustness (ADV-07): chấm từng ảnh trong manifest JSONL của scripts.robustness_manifest
qua đúng đường API, ghi predictions CSV cho scripts.analyze_robustness (ADV-08):
    python -m scripts.evaluate --robustness --manifest <manifest.jsonl> \
        --model <model.joblib> --model-manifest <manifest.json> \
        --protocol <protocol.json> --output <predictions.csv>
"""

import argparse
import csv
import hashlib
import json
import logging
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np

from app.errors import ApiError
from app.inference import Scorer as ImageScorer
from app.schemas import ErrorCode
from app.settings import Settings
from app.uploads import analyze_image
from app.verdict import decide_verdict
from models.clip_input import feature_contract
from models.extract_features import load_features, sha256_file
from models.normalize import NORMALIZATION_VERSION
from models.run_info import run_info
from models.score import Scorer, load_bundle, load_scorer
from models.train import metrics

ACCURACY_TARGET = 0.90
MANIFEST_FIELDS = {
    "sample_id",
    "path",
    "sha256",
    "label",
    "source",
    "cohort",
    "split",
    "group_id",
    "parent_id",
    "transform",
}
PREDICTION_FIELDS = [
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
]
logger = logging.getLogger(__name__)


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
    if not (
        0 < thresholds["binary"] < 1
        and 0 <= thresholds["low"] < thresholds["high"] <= 1
    ):
        raise ValueError("Invalid model thresholds")
    return bundle, model_hash


def evaluate(labels: Path, feature_dir: Path, model_path: Path, split: str) -> dict:
    features, rows, manifest = load_features(labels, feature_dir)
    bundle, model_hash = load_locked_model(model_path, manifest)
    dataset = bundle["metadata"]["dataset"]
    if dataset == "genimage" and split == "test":
        raise ValueError("Use models.evaluate with an approved lock for GenImage test")
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
    scores = Scorer(bundle["probe"], None).predict_features(features[keep])
    binary, low, high = (bundle["thresholds"][key] for key in ("binary", "low", "high"))
    overall = metrics(y, scores, binary, low, high)
    by_source = [
        {
            "name": source,
            **metrics(
                y[sources == source], scores[sources == source], binary, low, high
            ),
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


class RobustnessInputError(ValueError):
    """Inputs refused before any image is scored; the CLI exits with code 2."""


def _read_json_object(path: Path, what: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RobustnessInputError(f"{what} not found: {path}") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RobustnessInputError(f"{what} is not valid JSON: {path}") from None
    if not isinstance(data, dict):
        raise RobustnessInputError(f"{what} must be a JSON object: {path}")
    return data


def read_robustness_manifest(path: Path) -> list[dict]:
    """Manifest rows; refuses missing fields, non-integer labels, non-test rows,
    reused IDs and identical bytes listed under different groups."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines if line.strip()]
    except FileNotFoundError:
        raise RobustnessInputError(f"Manifest not found: {path}") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RobustnessInputError(f"Manifest is not valid JSONL: {path}") from None
    if not rows:
        raise RobustnessInputError(f"Manifest is empty: {path}")
    ids, group_of_bytes = set(), {}
    for number, row in enumerate(rows, 1):
        where = f"{path.name}:{number}"
        if not isinstance(row, dict) or MANIFEST_FIELDS - set(row):
            raise RobustnessInputError(
                f"{where}: need fields {sorted(MANIFEST_FIELDS)}"
            )
        if type(row["label"]) is not int or row["label"] not in (0, 1):
            raise RobustnessInputError(f"{where}: label must be the integer 0 or 1")
        if row["split"] != "test":
            raise RobustnessInputError(f"{where}: split must be test")
        if row["sample_id"] in ids:
            raise RobustnessInputError(f"{where}: duplicate sample_id")
        if group_of_bytes.setdefault(row["sha256"], row["group_id"]) != row["group_id"]:
            raise RobustnessInputError(f"{where}: same image bytes in another group")
        ids.add(row["sample_id"])
    return rows


def check_model_manifest(
    model_manifest: dict, model_sha: str, thresholds: dict
) -> None:
    """The handed-over model manifest must describe exactly the model being loaded."""
    expected = {
        "model_sha256": model_sha,
        "clip_model_id": feature_contract()["clip_model_id"],
        "clip_revision": feature_contract()["clip_revision"],
        "normalization_version": NORMALIZATION_VERSION,
        "thresholds": thresholds,
    }
    for key, value in expected.items():
        if model_manifest.get(key) != value:
            raise RobustnessInputError(
                f"Model manifest does not match the model: {key}"
            )


def check_protocol(
    protocol: dict, hashes: dict[str, str], thresholds: dict, rows: list[dict]
) -> None:
    """Test-set gate: the locked ADV-08 protocol must name exactly these inputs.

    Checks status, review references, profile, thresholds, the SHA256 of model,
    model manifest and manifest, and that every row's cohort is registered as
    present with the same transform. Raises RobustnessInputError listing problems.
    """
    profile = {
        "clip_model_id": feature_contract()["clip_model_id"],
        "clip_revision": feature_contract()["clip_revision"],
        "normalization_version": NORMALIZATION_VERSION,
    }
    refs = ("manifest_lock_ref", "split_review_ref")
    checks = [
        (protocol.get("schema_version") == 1, "schema_version must be 1"),
        (protocol.get("status") == "locked", "status must be locked"),
        (
            all(isinstance(protocol.get(k), str) and protocol[k].strip() for k in refs),
            "manifest_lock_ref and split_review_ref are required",
        ),
        (protocol.get("profile") == profile, "profile differs from the model"),
        (protocol.get("thresholds") == thresholds, "thresholds differ from the model"),
    ]
    artifacts = protocol.get("artifacts")
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    for name, digest in hashes.items():
        entry = artifacts.get(name)
        checks.append(
            (
                isinstance(entry, dict) and entry.get("sha256") == digest,
                f"artifacts.{name}.sha256 differs from the file given",
            )
        )
    cohorts = protocol.get("cohorts")
    present = {
        cohort.get("name"): cohort.get("transform")
        for cohort in (cohorts if isinstance(cohorts, list) else [])
        if isinstance(cohort, dict) and cohort.get("status") == "present"
    }
    unregistered = sorted(
        {r["cohort"] for r in rows if present.get(r["cohort"], {}) != r["transform"]}
    )
    checks.append(
        (not unregistered, f"cohorts not registered as present: {unregistered}")
    )
    if problems := [message for passed, message in checks if not passed]:
        raise RobustnessInputError("Protocol refused: " + "; ".join(problems))


def check_image_bytes(manifest: Path, rows: list[dict]) -> None:
    """Every listed image must still match its hash before CLIP loads or the protocol is spent."""
    for row in rows:
        try:
            data = (manifest.parent / row["path"]).read_bytes()
        except OSError as exc:
            raise RobustnessInputError(
                f"Image not readable: {row['sample_id']}"
            ) from exc
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise RobustnessInputError(
                f"Image bytes changed since listing: {row['sample_id']}"
            )


def score_like_api(data: bytes, settings: Settings, scorer: ImageScorer) -> float:
    """Same checks and error codes as POST /v1/analyze; raises ApiError on failure."""
    if len(data) > settings.max_file_bytes:
        raise ApiError(ErrorCode.FILE_TOO_LARGE)
    try:
        score, _ = analyze_image(data, settings, scorer)
    except ApiError:
        raise
    except Exception as exc:  # as app.inference: any scorer failure is MODEL_ERROR
        logger.warning("Scorer failed: %s", type(exc).__name__)
        raise ApiError(ErrorCode.MODEL_ERROR) from exc
    return score


def _side_files(output: Path, protocol: Path) -> tuple[Path, Path, Path]:
    """Partial predictions, run log and the protocol's used marker."""
    return (
        output.with_name(output.name + ".partial"),
        output.with_name(output.name + ".run.json"),
        protocol.with_name(protocol.name + ".used.json"),
    )


def run_robustness(
    manifest: Path,
    model: Path,
    model_manifest: Path,
    protocol: Path,
    output: Path,
    load: Callable[[], ImageScorer],
) -> Counter:
    """Check every input, then score each manifest image like the API.

    Everything is validated before ``load`` (CLIP) is called. The protocol's
    ``.used.json`` marker is written before the first prediction, so one locked
    protocol scores once, like models.evaluate. Rows stream to ``<output>.partial``
    and are renamed only after all images and an unchanged-hash check pass; an
    interrupted run keeps the partial file and never invents outcomes. Expected
    image errors become ``status=error`` rows. Returns counts per status.
    """
    partial, run_log, used = _side_files(output, protocol)
    for path in (output, partial, run_log):
        if path.exists():
            raise FileExistsError(f"Output already exists: {path}")
    if used.exists():
        raise RobustnessInputError(
            f"Protocol already used ({used.name}); review that run, do not delete to retry"
        )
    inputs = {"model": model, "model_manifest": model_manifest, "manifest": manifest}
    for name, path in {**inputs, "protocol": protocol}.items():
        if not path.is_file():
            raise RobustnessInputError(f"{name} not found: {path}")
    hashes = {name: sha256_file(path) for name, path in inputs.items()}
    protocol_sha = sha256_file(protocol)
    try:
        thresholds = load_bundle(model)["thresholds"]
    except (OSError, TypeError, ValueError) as exc:
        raise RobustnessInputError(f"Model refused: {exc}") from None
    model_info = _read_json_object(model_manifest, "Model manifest")
    check_model_manifest(model_info, hashes["model"], thresholds)
    rows = read_robustness_manifest(manifest)
    check_protocol(_read_json_object(protocol, "Protocol"), hashes, thresholds, rows)
    check_image_bytes(manifest, rows)
    settings = Settings(
        threshold_low=thresholds["low"], threshold_high=thresholds["high"]
    )
    scorer = load()
    output.parent.mkdir(parents=True, exist_ok=True)
    with used.open("x", encoding="utf-8") as handle:
        json.dump(
            {
                "started_at": datetime.now(UTC).isoformat(),
                "output": output.name,
                "protocol_sha256": protocol_sha,
                **{f"{name}_sha256": digest for name, digest in hashes.items()},
            },
            handle,
            indent=2,
        )
    counts = Counter()
    with partial.open("x", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, PREDICTION_FIELDS)
        writer.writeheader()
        for row in rows:
            data = (manifest.parent / row["path"]).read_bytes()
            if hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise ValueError(
                    f"Image bytes changed since listing: {row['sample_id']}"
                )
            result = {"status": "ok", "score": "", "verdict": "", "error_code": ""}
            try:
                score = score_like_api(data, settings, scorer)
                result.update(
                    score=repr(score), verdict=decide_verdict(score, settings).value
                )
            except ApiError as exc:
                result.update(status="error", error_code=exc.code.value)
            counts[result["status"]] += 1
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "group_id": row["group_id"],
                    "parent_id": row["parent_id"] or "",
                    "label": row["label"],
                    **result,
                    "model_sha256": hashes["model"],
                    "manifest_sha256": hashes["manifest"],
                    "protocol_sha256": protocol_sha,
                }
            )
    after = {name: sha256_file(path) for name, path in inputs.items()}
    if after != hashes or sha256_file(protocol) != protocol_sha:
        raise ValueError(f"Inputs changed during the run; see {partial}")
    partial.rename(output)
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--split", choices=["val", "test"])
    mode.add_argument("--robustness", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--features", type=Path, default=Path("data/features"))
    parser.add_argument("--model", type=Path, default=Path("models/clip_probe.joblib"))
    parser.add_argument("--manifest", type=Path, help="Robustness manifest JSONL")
    parser.add_argument(
        "--model-manifest", type=Path, help="Handed-over model manifest"
    )
    parser.add_argument("--protocol", type=Path, help="Locked ADV-08 protocol")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    if args.robustness:
        if not (args.manifest and args.model_manifest and args.protocol):
            parser.error("--robustness needs --manifest, --model-manifest, --protocol")
        provenance = run_info("scripts.evaluate")
        try:
            counts = run_robustness(
                args.manifest,
                args.model,
                args.model_manifest,
                args.protocol,
                args.output,
                lambda: load_scorer(args.model),
            )
        except (RobustnessInputError, FileExistsError) as exc:
            parser.exit(2, f"{parser.prog}: error: {exc}\n")
        except ValueError as exc:
            parser.exit(1, f"{parser.prog}: run stopped: {exc}\n")
        # Local run log for QA (commit, dirty flag, versions); keep it out of Git.
        _, run_log, _ = _side_files(args.output, args.protocol)
        with run_log.open("x", encoding="utf-8") as handle:
            json.dump({**provenance, "counts": dict(counts)}, handle, indent=2)
        print(f"Đã ghi {args.output}: {dict(counts)}")
        return
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
