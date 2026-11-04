"""Chuẩn hóa ảnh, loại ảnh trùng, chia tập và xuất data/labels.csv (D3).

Mọi ảnh (thật và AI) được đưa về cùng một "vỏ ngoài" để mô hình không học
định dạng file thay cho dấu vết AI:
    RGB -> resize cạnh ngắn về SIZE -> center-crop SIZE x SIZE -> JPEG QUALITY, bỏ EXIF.
CIFAKE (32x32) giữ nguyên kích thước, chỉ lưu lại JPEG cùng chất lượng.

Cách chạy (từ thư mục gốc repo):
    python -m scripts.prepare_data
"""

import argparse
import hashlib
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
    }


def drop_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Bỏ ảnh trùng pixel; cùng ảnh mà khác nhãn thì bỏ cả hai."""
    mixed = df.groupby("hash")["label"].transform("nunique") > 1
    kept = df[~mixed].drop_duplicates("hash")
    print(f"Loại {len(df) - len(kept)} ảnh trùng")
    return kept


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


def main() -> None:
    global RAW_DIR, PROCESSED_DIR, LABELS_CSV
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--output-dir", type=Path, default=PROCESSED_DIR)
    parser.add_argument("--labels", type=Path, default=LABELS_CSV)
    parser.add_argument("--workers", type=int, default=2)
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
        rejected_df = pd.DataFrame(
            [row for row in rejected if row["rejection"] == kind],
            columns=["raw_path", "source", "width", "height", "reason", "norm_version"],
        )
        rejected_df.to_csv(PROCESSED_DIR / f"rejected_{kind}.csv", index=False)
        print(f"Rejected {kind}:", rejected_df.groupby("source").size().to_dict())
    ok = ["filepath" in r for r in results]
    df = df[ok].assign(
        filepath=[r["filepath"] for r in results if "filepath" in r],
        hash=[r["hash"] for r in results if "hash" in r],
    )
    df = drop_duplicates(df)
    df["split"] = assign_splits(df)

    df = df[["filepath", "label", "source", "split", "raw_path"]]
    df["norm_version"] = NORMALIZATION_VERSION
    LABELS_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(LABELS_CSV, index=False)
    print(f"Đã ghi {LABELS_CSV}: {len(df)} dòng")
    print(pd.crosstab(df["source"], df["split"], margins=True))


if __name__ == "__main__":
    main()
