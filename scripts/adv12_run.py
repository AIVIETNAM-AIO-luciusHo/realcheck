"""Keo cho thí nghiệm ADV-12 (#144): trích đặc trưng (có tăng cường chỉ ở train) và fit LR, xuất điểm cho so sánh.

    python -m scripts.adv12_run extract --labels data/labels.csv --output run/features.npz \
        --encoder last|layers [--layers 6,9,12] [--augment 0.5 --augment-seed 42] [--batch-size 32]
    python -m scripts.adv12_run fit --features run/features.npz --output-dir run/fit [--C 10 --seed 42]

THỬ NGHIỆM: không sửa models.train, models.extract_features hay normalize_image; không ghi vào models/ và không
đặt tên clip_probe*. Đặc trưng `--encoder layers` KHÔNG cùng không gian với e571.

`extract`: đọc `labels.csv` (cần cột group_id), ảnh ở cột `--image-column` (mặc định `filepath`, ảnh đã chuẩn hóa).
`--encoder last` đi đúng đường của e571 (models.clip_input); `layers` dùng models.clip_layers. `--augment p` áp
models.augment.apply_random CHỈ cho split train (không bao giờ cho val/test); ảnh tăng cường (hoặc đọc từ raw_path)
đi qua normalize_image rồi mới vào encoder. Seed tăng cường của từng ảnh suy ra từ `--augment-seed` và đường dẫn ảnh,
nên không phụ thuộc thứ tự dòng. Ghi `.npz` (features, ids, labels, groups, splits, sources), `.json` manifest (hash
labels.csv, phiên bản, tham số, đếm split) và, khi có tăng cường, `.augment.jsonl` (phép đã áp cho từng ảnh train).

`score`: chấm ảnh bằng model THẬT qua models.score.load_scorer (bắt buộc checksum; --model hoặc REALCHECK_MODEL_PATH),
ghi CSV điểm theo từng ID để làm E0. Ảnh nên là ảnh gốc (--image-column raw_path) vì Scorer tự chuẩn hóa; với
ảnh đã chuẩn hóa (filepath) kết quả vẫn đúng hợp đồng của extract_features.

`fit`: LogisticRegression(C, max_iter=2000, random_state=seed) chỉ trên split train; ghi `<name>.joblib` + `.sha256`,
điểm validation mặc định dạng `sample_id,label,score,group_id,source` (đọc được bởi scripts.compare_models và
scripts.calibrate_scores) và `<name>.fit.json`. `score` cũng mặc định chỉ validation; test phải được yêu cầu
tường minh bằng --split test theo protocol đã khóa. Từ chối group_id xuất hiện ở hai split và output đã có.
"""

import argparse
import csv
import hashlib
import json
import platform
import re
import sys
import time
import warnings
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import joblib
import numpy as np
from PIL import Image
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression

from models.clip_input import CLIP_MODEL_ID, CLIP_REVISION
from models.extract_features import read_labels, sha256_file
from models.normalize import normalize_image
from models.run_info import peak_rss_mib

SPLITS = ("train", "val", "test")
PACKAGES = (
    "numpy",
    "pillow",
    "scikit-learn",
    "joblib",
    "torch",
    "transformers",
    "sentence-transformers",
)


def versions() -> dict:
    out = {"python": platform.python_version()}
    for package in PACKAGES:
        try:
            out[package] = version(package)
        except PackageNotFoundError:
            out[package] = "not-installed"
    return out


def image_seed(base: int, key: str) -> int:
    """Seed riêng cho từng ảnh, độc lập thứ tự dòng."""
    return int(hashlib.sha256(f"{base}:{key}".encode()).hexdigest()[:8], 16)


def read_rows(labels: Path) -> list[dict]:
    rows = read_labels(labels)
    if "group_id" not in rows[0] or any(
        not (r.get("group_id") or "").strip() for r in rows
    ):
        raise ValueError("labels.csv cần cột group_id không rỗng (PR #113)")
    check_no_group_leak(
        np.array([r["group_id"] for r in rows]), np.array([r["split"] for r in rows])
    )
    return rows


def extract_rows(
    rows: list[dict],
    embed,
    *,
    image_column: str = "filepath",
    augment_p: float = 0.0,
    augment_seed: int = 42,
    batch_size: int = 32,
) -> tuple[np.ndarray, list[dict]]:
    """(đặc trưng theo đúng thứ tự dòng, bản ghi tăng cường). `embed(list[Image]) -> (n, d)`; chỉ train được tăng cường."""
    if batch_size < 1 or not 0 <= augment_p <= 1:
        raise ValueError("batch_size >= 1 và augment trong [0, 1]")
    if image_column not in rows[0]:
        raise ValueError(f"labels.csv không có cột {image_column}")
    if augment_p > 0:
        from models.augment import apply_random
    chunks, records = [], []
    for start in range(0, len(rows), batch_size):
        images = []
        for row in rows[start : start + batch_size]:
            with Image.open(row[image_column]) as opened:
                image = opened.convert("RGB")
            augmented = augment_p > 0 and row["split"] == "train"
            if augmented:
                seed = image_seed(augment_seed, row["filepath"])
                image, applied = apply_random(image, seed, augment_p)
                records.append(
                    {
                        "sample_id": row["filepath"],
                        "split": "train",
                        "seed": seed,
                        "applied": applied,
                    }
                )
            if augmented or image_column != "filepath":
                image = normalize_image(
                    image, resize=not row["source"].startswith("cifake_")
                ).image
            images.append(image)
        chunks.append(np.asarray(embed(images), dtype=np.float32))
    features = np.concatenate(chunks, axis=0)
    if (
        features.ndim != 2
        or len(features) != len(rows)
        or not np.isfinite(features).all()
    ):
        raise ValueError("embed phải trả (n, d) hữu hạn theo đúng số ảnh")
    return features, records


def make_embed(args):
    if args.device == "cuda":
        import torch

        if not torch.cuda.is_available():
            raise ValueError("--device cuda requested but CUDA is not available")
    if args.encoder == "last":
        from models.clip_input import encode_images, load_encoder

        encoder = load_encoder(device=args.device)
        return lambda images: encode_images(images, encoder)
    if not args.layers:
        raise ValueError("--encoder layers cần --layers a,b,c")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.revision or ""):
        raise ValueError("--encoder layers cần --revision SHA 40 ký tự đã ghim")
    from models import clip_layers

    layers = [int(v) for v in args.layers.split(",")]
    model, processor = clip_layers.load_vision_model(
        args.model_id, args.revision, device=args.device
    )
    return lambda images: clip_layers.extract_features(
        images, model, processor, layers, batch_size=len(images)
    )


def cmd_extract(args, embed=None) -> int:
    for path in (
        args.output,
        args.output.with_suffix(".json"),
        args.output.with_suffix(".augment.jsonl"),
    ):
        if path.exists():
            raise FileExistsError(f"output đã tồn tại: {path}")
    rows = read_rows(args.labels)
    labels_hash = sha256_file(args.labels)
    started = time.perf_counter()
    embed = embed or make_embed(args)
    features, records = extract_rows(
        rows,
        embed,
        image_column=args.image_column,
        augment_p=args.augment,
        augment_seed=args.augment_seed,
        batch_size=args.batch_size,
    )
    extraction_seconds = time.perf_counter() - started
    if sha256_file(args.labels) != labels_hash:
        raise ValueError("labels.csv đổi trong lúc trích; bỏ lượt này")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        args.output,
        features=features,
        ids=np.array([r["filepath"] for r in rows]),
        labels=np.array([int(r["label"]) for r in rows]),
        groups=np.array([r["group_id"] for r in rows]),
        splits=np.array([r["split"] for r in rows]),
        sources=np.array([r["source"] for r in rows]),
    )
    manifest = {
        "labels_sha256": labels_hash,
        "features_sha256": sha256_file(args.output),
        "encoder": args.encoder,
        "layers": args.layers,
        "model_id": args.model_id if args.encoder == "layers" else CLIP_MODEL_ID,
        "revision": args.revision if args.encoder == "layers" else CLIP_REVISION,
        "device": args.device,
        "batch_size": args.batch_size,
        "cpu_thread_policy": 4 if args.device == "cpu" else None,
        "extraction_seconds_including_load": extraction_seconds,
        "peak_rss_process_mib": peak_rss_mib(),
        "image_column": args.image_column,
        "augment": {
            "p": args.augment,
            "seed": args.augment_seed,
            "applied_splits": ["train"] if args.augment > 0 else [],
        },
        "counts": {s: sum(r["split"] == s for r in rows) for s in SPLITS},
        "shape": list(features.shape),
        "versions": versions(),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    if args.augment > 0:
        with args.output.with_suffix(".augment.jsonl").open(
            "w", encoding="utf-8"
        ) as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Đã ghi {args.output} {features.shape}")
    return 0


def load_npz(path: Path) -> dict:
    with np.load(path, allow_pickle=False) as data:
        out = {
            k: data[k]
            for k in ("features", "ids", "labels", "groups", "splits", "sources")
        }
    n = len(out["features"])
    if (
        out["features"].ndim != 2
        or any(len(out[k]) != n for k in out)
        or not np.isfinite(out["features"]).all()
    ):
        raise ValueError(f"{path}: .npz không nhất quán hoặc có giá trị không hữu hạn")
    if len(set(out["ids"].tolist())) != n:
        raise ValueError(f"{path}: sample_id trùng")
    return out


def check_no_group_leak(groups: np.ndarray, splits: np.ndarray) -> None:
    where: dict[str, str] = {}
    for g, s in zip(groups.tolist(), splits.tolist()):
        if where.setdefault(g, s) != s:
            raise ValueError(
                f"group_id {g!r} xuất hiện ở hai split ({where[g]} và {s})"
            )


def write_scores(path: Path, data: dict, mask: np.ndarray, scores: np.ndarray) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["sample_id", "label", "score", "group_id", "source"])
        for i, score in zip(np.flatnonzero(mask), scores, strict=True):
            writer.writerow(
                [
                    data["ids"][i],
                    int(data["labels"][i]),
                    repr(float(score)),
                    data["groups"][i],
                    data["sources"][i],
                ]
            )


NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def check_name(name: str, out_dir: Path) -> None:
    """Tên an toàn, output mới nằm trong `out_dir` và ngoài models/."""
    if not NAME_RE.fullmatch(name) or ".." in name:
        raise ValueError(
            "--name chỉ nhận [A-Za-z0-9._-], không bắt đầu bằng '.', không chứa '/', '\\', '..'"
        )
    models_dir = Path("models").resolve()
    for suffix in (
        ".joblib",
        ".joblib.sha256",
        ".fit.json",
        ".val_scores.csv",
        ".test_scores.csv",
    ):
        target = (out_dir / f"{name}{suffix}").resolve()
        if target.parent != out_dir:
            raise ValueError("đường ghi nằm ngoài --output-dir")
        if target.parent == models_dir or models_dir in target.parents:
            raise ValueError("không ghi vào thư mục models/")
        if target.exists():
            raise FileExistsError(f"output đã tồn tại: {target}")


def cmd_fit(args) -> int:
    name = args.name
    out_dir = args.output_dir.resolve()
    check_name(name, out_dir)
    if name.lower().startswith("clip_probe"):
        raise ValueError("không đặt tên clip_probe*: tên đó dành cho model phục vụ")
    models_dir = Path("models").resolve()
    if out_dir == models_dir or models_dir in out_dir.parents:
        raise ValueError("không ghi vào thư mục models/")
    data = load_npz(args.features)
    check_no_group_leak(data["groups"], data["splits"])
    train = data["splits"] == "train"
    y = data["labels"]
    if set(y[train].tolist()) != {0, 1}:
        raise ValueError("train cần cả hai lớp")
    probe = LogisticRegression(C=args.C, max_iter=2000, random_state=args.seed)
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        probe.fit(data["features"][train], y[train])
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {s: int((data["splits"] == s).sum()) for s in SPLITS}
    metadata = {
        "features_sha256": sha256_file(args.features),
        "C": args.C,
        "seed": args.seed,
        "split_counts": counts,
        "feature_dim": int(data["features"].shape[1]),
        "trained_on": ["train"],
    }
    model_path = out_dir / f"{name}.joblib"
    joblib.dump(
        {"probe": probe, "metadata": metadata, "versions": versions()}, model_path
    )
    model_hash = sha256_file(model_path)
    model_path.with_suffix(".joblib.sha256").write_text(
        model_hash + "\n", encoding="ascii"
    )
    written = []
    for split in dict.fromkeys(args.split or ["val"]):
        mask = data["splits"] == split
        if mask.any():
            scores = probe.predict_proba(data["features"][mask])[
                :, int(np.flatnonzero(probe.classes_ == 1)[0])
            ]
            filename = f"{name}.{split}_scores.csv"
            write_scores(out_dir / filename, data, mask, scores)
            written.append(filename)
    (out_dir / f"{name}.fit.json").write_text(
        json.dumps(
            {
                **metadata,
                "model_sha256": model_hash,
                "score_files": written,
                "note": "Thử nghiệm ADV-12; chọn trên validation, không dùng cho đánh giá cuối.",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Đã ghi {model_path} và {written}")
    return 0


def cmd_score(args) -> int:
    """Chấm ảnh GỐC bằng model THẬT qua models.score (kiểm checksum như load_scorer); ghi điểm theo từng ID cho E0."""
    import os

    from models.score import load_scorer

    model = args.model or (
        Path(os.environ["REALCHECK_MODEL_PATH"])
        if os.environ.get("REALCHECK_MODEL_PATH")
        else None
    )
    if model is None:
        raise ValueError("cần --model hoặc biến REALCHECK_MODEL_PATH")
    if args.output.exists():
        raise FileExistsError(f"output đã tồn tại: {args.output}")
    rows = read_rows(args.labels)
    rows = [r for r in rows if r["split"] in (args.split or ["val"])]
    if not rows:
        raise ValueError("không có ảnh nào để chấm")
    scorer = load_scorer(model)  # kiểm checksum, hợp đồng đặc trưng, rồi nạp CLIP
    data = {k: [] for k in ("ids", "labels", "groups", "sources")}
    scores = []
    for row in rows:
        with Image.open(row[args.image_column]) as image:
            image.load()
            scores.append(scorer(image))
        data["ids"].append(row["filepath"])
        data["labels"].append(int(row["label"]))
        data["groups"].append(row["group_id"])
        data["sources"].append(row["source"])
    data = {k: np.array(v) for k, v in data.items()}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_scores(args.output, data, np.ones(len(rows), dtype=bool), np.array(scores))
    print(f"Đã ghi {args.output} ({len(rows)} ảnh)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Keo thí nghiệm ADV-12")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    ex.add_argument("--output", type=Path, required=True, help=".npz")
    ex.add_argument("--encoder", choices=("last", "layers"), default="last")
    ex.add_argument("--layers", help="vd 6,9,12 (chỉ cho --encoder layers)")
    ex.add_argument("--model-id", default="openai/clip-vit-base-patch32")
    ex.add_argument("--revision", default=None)
    ex.add_argument(
        "--image-column", default="filepath", choices=("filepath", "raw_path")
    )
    ex.add_argument(
        "--augment", type=float, default=0.0, help="xác suất mỗi phép; chỉ áp cho train"
    )
    ex.add_argument("--augment-seed", type=int, default=42)
    ex.add_argument("--batch-size", type=int, default=32)
    ex.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    fit = sub.add_parser("fit")
    fit.add_argument("--features", type=Path, required=True)
    fit.add_argument("--output-dir", type=Path, required=True)
    fit.add_argument("--name", default="adv12_probe")
    fit.add_argument("--C", type=float, default=10.0)
    fit.add_argument("--seed", type=int, default=42)
    fit.add_argument(
        "--split",
        action="append",
        choices=("val", "test"),
        help="split được chấm, lặp được; mặc định chỉ val; test cần protocol đã khóa",
    )
    sc = sub.add_parser("score", help="chấm bằng model e571 thật (E0)")
    sc.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    sc.add_argument("--model", type=Path, help="mặc định biến REALCHECK_MODEL_PATH")
    sc.add_argument("--output", type=Path, required=True, help="CSV điểm")
    sc.add_argument(
        "--split", action="append", choices=SPLITS, help="lặp được; mặc định chỉ val"
    )
    sc.add_argument(
        "--image-column", default="filepath", choices=("filepath", "raw_path")
    )
    args = ap.parse_args(argv)
    try:
        if args.cmd == "score":
            return cmd_score(args)
        return cmd_extract(args) if args.cmd == "extract" else cmd_fit(args)
    except (ValueError, OSError, ConvergenceWarning) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
