"""Chuẩn hóa ảnh, loại ảnh trùng, chia tập và xuất data/labels.csv (D3).

Mọi ảnh (thật và AI) được đưa về cùng một "vỏ ngoài" để mô hình không học
định dạng file thay cho dấu vết AI:
    RGB -> resize cạnh ngắn về SIZE -> center-crop SIZE x SIZE -> JPEG QUALITY, bỏ EXIF.
CIFAKE (32x32) giữ nguyên kích thước, chỉ lưu lại JPEG cùng chất lượng.

Cách chạy (từ thư mục gốc repo):
    python scripts/prepare_data.py
"""

import hashlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageOps

RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")
LABELS_CSV = Path("data/labels.csv")

SEED = 42
SIZE = 256
QUALITY = 95
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


def process_one(raw_path: str) -> tuple[str, str] | None:
    """Chuẩn hóa một ảnh; trả về (đường dẫn processed, hash pixel), None nếu ảnh hỏng."""
    rel = Path(raw_path).relative_to(RAW_DIR)
    out = PROCESSED_DIR / rel.with_suffix(".jpg")
    try:
        with Image.open(raw_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            if rel.parts[0] == "genimage":
                im = ImageOps.fit(im, (SIZE, SIZE), Image.Resampling.BICUBIC)
            out.parent.mkdir(parents=True, exist_ok=True)
            im.save(out, "JPEG", quality=QUALITY)  # không truyền exif= nên EXIF bị bỏ
            return out.as_posix(), hashlib.md5(im.tobytes()).hexdigest()
    except OSError as e:
        print(f"Bỏ ảnh hỏng {raw_path}: {e}")
        return None


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
    df = collect_raw()
    print(f"Tìm thấy {len(df)} ảnh gốc")
    with ProcessPoolExecutor() as ex:
        results = list(ex.map(process_one, df["raw_path"], chunksize=32))
    ok = [r is not None for r in results]
    df = df[ok].assign(
        filepath=[r[0] for r in results if r], hash=[r[1] for r in results if r]
    )
    df = drop_duplicates(df)
    df["split"] = assign_splits(df)

    df = df[["filepath", "label", "source", "split", "raw_path"]]
    df.to_csv(LABELS_CSV, index=False)
    print(f"Đã ghi {LABELS_CSV}: {len(df)} dòng")
    print(pd.crosstab(df["source"], df["split"], margins=True))


if __name__ == "__main__":
    main()
