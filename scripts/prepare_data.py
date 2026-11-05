"""Chuẩn hóa ảnh, loại ảnh trùng, chia tập và xuất data/labels.csv (D3).

Mọi ảnh (thật và AI) được đưa về cùng một "vỏ ngoài" để mô hình không học
định dạng file thay cho dấu vết AI:
    RGB -> resize cạnh ngắn về SIZE -> center-crop SIZE x SIZE -> JPEG QUALITY, bỏ EXIF.
CIFAKE (32x32) giữ nguyên kích thước, chỉ lưu lại JPEG cùng chất lượng.

Cách chạy (từ thư mục gốc repo):
    python -m scripts.prepare_data
"""

import argparse
import csv
import hashlib
import io
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

from models.normalize import NORMALIZATION_VERSION, ImageTooSmall, normalize_image

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
LABELS_CSV = Path("data/labels.csv")

SEED = 42
SPLIT_RATIO = (0.70, 0.15, 0.15)  # train / val / test cho GenImage
CIFAKE_VAL_RATIO = 0.15  # phần CIFAKE train tách ra làm val; test giữ split gốc
REJECTED_COLUMNS = ["raw_path", "source", "width", "height", "reason", "norm_version"]


def collect_raw() -> pd.DataFrame:
    """Liệt kê ảnh gốc; nhãn lấy theo tên thư mục (real = 0, còn lại = 1)."""
    # (file, bộ dữ liệu, split gốc): chỉ CIFAKE có sẵn split train/test
    files = [(f, "genimage", None) for f in sorted(RAW_DIR.glob("genimage/*/*"))]
    files += [
        (f, "cifake", f.parent.parent.name)
        for f in sorted(RAW_DIR.glob("cifake/*/*/*"))
    ]
    rows = [
        (
            f.as_posix(),
            int(f.parent.name != "real"),
            f"{dataset}_{f.parent.name}",
            split,
        )
        for f, dataset, split in files
    ]
    return pd.DataFrame(rows, columns=["raw_path", "label", "source", "split"])


def process_one(item: tuple[str, str, str]) -> dict:
    """Normalize one image, or return an explicit rejection (Windows spawn-safe)."""
    raw_path, raw_dir, processed_dir = item
    rel = Path(raw_path).relative_to(raw_dir)
    out = Path(processed_dir) / rel.with_suffix(".jpg")
    width = height = 0
    try:
        with Image.open(raw_path) as im:
            width, height = im.size
            normalized = normalize_image(im, resize=rel.parts[0] != "cifake")
    except ImageTooSmall as exc:
        return {
            "rejection": "small",
            "width": width,
            "height": height,
            "reason": str(exc),
        }
    except (OSError, Image.DecompressionBombError) as exc:
        return {
            "rejection": "invalid",
            "width": width,
            "height": height,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    # Output failures (e.g. disk full) must stop the run, not label an image invalid.
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(normalized.jpeg)
    return {
        "filepath": out.as_posix(),
        "hash": hashlib.sha256(normalized.image.tobytes()).hexdigest(),
        "width": width,
        "height": height,
    }


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Bỏ ảnh trùng pixel; cùng ảnh mà khác nhãn thì bỏ cả hai."""
    mixed = df.groupby("hash")["label"].transform("nunique") > 1
    kept = df[~mixed].drop_duplicates("hash")
    print(f"Loại {len(df) - len(kept)} ảnh trùng")
    return kept


def duplicate_records(df: pd.DataFrame, kept: pd.DataFrame) -> pd.DataFrame:
    """Bản ghi cho ảnh bị drop_duplicates bỏ, để mọi ảnh gốc đều truy được."""
    dropped = df.drop(kept.index)
    kept_path = dropped["hash"].map(kept.set_index("hash")["raw_path"])
    reason = [
        f"Same pixels as {path} after normalization"
        if isinstance(path, str)
        else "Same pixels as an image with a different label"
        for path in kept_path
    ]
    return dropped.assign(reason=reason, norm_version=NORMALIZATION_VERSION)[
        REJECTED_COLUMNS
    ]


def write_rejected(kind: str, records: pd.DataFrame) -> None:
    records.to_csv(PROCESSED_DIR / f"rejected_{kind}.csv", index=False)
    print(f"Rejected {kind}:", records.groupby("source").size().to_dict())


def assign_splits(df: pd.DataFrame) -> pd.Series:
    """Chia tập phân tầng theo source để mỗi tập cân bằng giữa các nguồn."""
    rng = np.random.default_rng(SEED)
    split = df["split"].copy()
    for source, g in df.groupby("source"):
        if source.startswith("cifake"):
            train = g.index[g["split"] == "train"]
            val = rng.choice(train, round(len(train) * CIFAKE_VAL_RATIO), replace=False)
            split[val] = "val"
            continue
        idx = rng.permutation(g.index)
        n_train, n_val = (round(len(idx) * r) for r in SPLIT_RATIO[:2])
        split[idx[:n_train]] = "train"
        split[idx[n_train : n_train + n_val]] = "val"
        split[idx[n_train + n_val :]] = "test"
    return split


def preserve_splits(df: pd.DataFrame, reference: Path) -> str:
    """Reuse an exact raw cohort's split before filtering; never draw new splits."""
    content = reference.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
    required = {"raw_path", "label", "source", "split"}
    fields = reader.fieldnames or []
    if not required.issubset(fields) or len(fields) != len(set(fields)):
        raise ValueError("missing required or duplicate columns")
    rows = list(reader)
    if any(
        None in row or any(not (row.get(key) or "").strip() for key in required)
        for row in rows
    ):
        raise ValueError("empty or malformed CSV row")

    def identity(value: str) -> str:
        path = Path(value.replace("\\", "/"))
        for prefix in (Path("data/raw"), RAW_DIR):
            if path.is_relative_to(prefix):
                path = path.relative_to(prefix)
                break
        if (
            path.is_absolute()
            or path.drive
            or ".." in path.parts
            or not path.parts
            or path.parts[0] not in {"genimage", "cifake"}
        ):
            raise ValueError(f"invalid raw_path: {value}")
        return path.as_posix()

    indexed = {identity(row["raw_path"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("duplicate raw_path")
    keys = df["raw_path"].map(identity)
    if set(keys) != set(indexed):
        raise ValueError("raw cohort differs; every raw image needs one reference row")
    splits = []
    for key, row in zip(keys, df.itertuples()):
        old = indexed[key]
        split = old["split"]
        if old["label"] != str(row.label) or old["source"] != row.source:
            raise ValueError(f"label/source changed: {key}")
        if split not in {"train", "val", "test"}:
            raise ValueError(f"invalid split: {key}")
        if row.source.startswith("cifake_") and (
            (row.split == "test") != (split == "test")
        ):
            raise ValueError(f"CIFAKE original test membership changed: {key}")
        splits.append(split)
    df["split"] = splits
    return hashlib.sha256(content).hexdigest()


def main() -> None:
    global RAW_DIR, PROCESSED_DIR, LABELS_CSV
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--labels", type=Path, default=LABELS_CSV)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--split-from",
        type=Path,
        help="Keep each raw image's split from an existing manifest; do not reshuffle",
    )
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    RAW_DIR, PROCESSED_DIR, LABELS_CSV = args.raw_dir, args.output_dir, args.labels
    # A new output directory avoids overwriting the pre-migration data baseline.
    if LABELS_CSV.exists() or (PROCESSED_DIR.exists() and any(PROCESSED_DIR.iterdir())):
        parser.error("Output already exists; use new --output-dir and --labels paths")
    df = collect_raw()
    if df.empty:
        parser.error(f"No raw images under {RAW_DIR}")
    split_hash = None
    if args.split_from is not None:
        try:
            split_hash = preserve_splits(df, args.split_from)
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            parser.error(f"Invalid split reference: {exc}")
        print(f"Split reference sha256: {split_hash}")
    print(f"Tìm thấy {len(df)} ảnh gốc")
    items = [(p, str(RAW_DIR), str(PROCESSED_DIR)) for p in df["raw_path"]]
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        results = list(ex.map(process_one, items, chunksize=32))
    rejected = [
        {
            "raw_path": row.raw_path,
            "source": row.source,
            **result,
            "norm_version": NORMALIZATION_VERSION,
        }
        for row, result in zip(df.itertuples(), results)
        if "reason" in result
    ]
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for kind in ("small", "invalid"):
        rows = [row for row in rejected if row["rejection"] == kind]
        write_rejected(kind, pd.DataFrame(rows, columns=REJECTED_COLUMNS))
    ok = ["filepath" in r for r in results]
    df = df[ok].assign(
        filepath=[r["filepath"] for r in results if "filepath" in r],
        hash=[r["hash"] for r in results if "hash" in r],
        width=[r["width"] for r in results if "filepath" in r],
        height=[r["height"] for r in results if "filepath" in r],
    )
    kept = drop_duplicates(df)
    write_rejected("duplicate", duplicate_records(df, kept))
    # Ảnh bị loại không được để lại JPEG trong processed; a.png và a.jpg dùng chung tệp
    for path in set(df.drop(kept.index)["filepath"]) - set(kept["filepath"]):
        Path(path).unlink()
    df = kept
    if split_hash is None:
        df["split"] = assign_splits(df)
    elif hashlib.sha256(args.split_from.read_bytes()).hexdigest() != split_hash:
        raise ValueError("Split reference changed during processing; no labels written")

    df = df[["filepath", "label", "source", "split", "raw_path"]]
    df["norm_version"] = NORMALIZATION_VERSION
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LABELS_CSV, index=False)
    print(f"Đã ghi {LABELS_CSV}: {len(df)} dòng")
    print(pd.crosstab(df["source"], df["split"], margins=True))


if __name__ == "__main__":
    main()
