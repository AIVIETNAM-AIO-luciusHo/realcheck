"""Kiểm tra data/labels.csv và ảnh đã chuẩn hóa trước khi bàn giao.

Lỗi (FAIL) làm script thoát với mã 1; cảnh báo (WARN) chỉ in ra để xem lại.

Cách chạy (từ thư mục gốc repo, sau prepare_data.py):
    python scripts/check_data.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

LABELS_CSV = Path("data/labels.csv")
COLUMNS = ["filepath", "label", "source", "split", "raw_path"]
SPLITS = {"train", "val", "test"}
EXPECTED_SIZE = {"genimage": (256, 256), "cifake": (32, 32)}
# Hai ảnh có dHash lệch <= ngưỡng này coi là gần trùng
NEAR_DUP_BITS = 4
# Tỷ lệ ảnh AI trong mỗi split phải nằm trong khoảng này
AI_RATIO_RANGE = (0.4, 0.6)

failures: list[str] = []
warnings: list[str] = []


def check(ok: bool, msg: str, warn: bool = False) -> None:
    print(f"  {'OK  ' if ok else 'WARN' if warn else 'FAIL'} {msg}")
    if not ok:
        (warnings if warn else failures).append(msg)


def dhash(im: Image.Image) -> int:
    """Hash cảm nhận 64 bit: giống nhau nếu ảnh gần như cùng nội dung."""
    px = np.asarray(im.convert("L").resize((9, 8), Image.Resampling.LANCZOS), dtype=int)
    bits = np.packbits(px[:, 1:] > px[:, :-1])
    return int.from_bytes(bits.tobytes(), "big")


def check_schema(df: pd.DataFrame) -> None:
    print("1. Cấu trúc labels.csv")
    check(list(df.columns) == COLUMNS, f"cột đúng {COLUMNS}")
    check(not df.isna().any().any(), "không có ô trống")
    check(set(df["label"]) <= {0, 1}, "label chỉ là 0/1")
    check(set(df["split"]) <= SPLITS, "split chỉ là train/val/test")


def check_labels(df: pd.DataFrame) -> None:
    print("2. Nhãn khớp nguồn")
    expected = (~df["source"].str.endswith("_real")).astype(int)
    bad = df[df["label"] != expected]
    check(bad.empty, f"nhãn khớp source ({len(bad)} dòng sai)")
    folder = df["filepath"].map(lambda p: Path(p).parent.name)
    want = df["source"].str.split("_", n=1).str[1]
    check((folder == want).all(), "thư mục ảnh khớp source")


def check_files(df: pd.DataFrame) -> None:
    print("3. File tồn tại")
    check(df["filepath"].is_unique, "filepath không trùng")
    for col in ("filepath", "raw_path"):
        missing = [p for p in df[col] if not Path(p).is_file()]
        check(not missing, f"mọi {col} tồn tại ({len(missing)} thiếu)")


def dataset_of(df: pd.DataFrame) -> pd.Series:
    """Tên bộ dữ liệu (genimage/cifake) lấy từ tiền tố của source."""
    return df["source"].str.split("_").str[0]


def check_images(df: pd.DataFrame) -> list[int]:
    """Kiểm tra định dạng từng ảnh processed; trả về dHash để dùng ở bước rò rỉ."""
    print("4. Ảnh đã chuẩn hóa")
    hashes, problems = [], []
    for p, dataset in zip(df["filepath"], dataset_of(df)):
        with Image.open(p) as im:
            if im.format != "JPEG" or im.mode != "RGB":
                problems.append(f"{p}: {im.format}/{im.mode}")
            elif im.size != EXPECTED_SIZE[dataset]:
                problems.append(f"{p}: kích thước {im.size}")
            elif im.getexif():
                problems.append(f"{p}: còn EXIF")
            hashes.append(dhash(im))
    check(not problems, f"JPEG RGB, đúng kích thước, không EXIF ({len(problems)} lỗi)")
    for line in problems[:5]:
        print(f"       {line}")
    return hashes


def check_leakage(df: pd.DataFrame) -> None:
    print("5. Rò rỉ giữa các split")
    for dataset, g in df.groupby(dataset_of(df)):
        train = g.loc[g["split"] == "train", "dhash"].to_numpy()
        for split in ("val", "test"):
            other = g.loc[g["split"] == split, "dhash"].to_numpy()
            dist = np.bitwise_count(other[:, None] ^ train[None, :])
            exact = int((dist == 0).any(axis=1).sum())
            near = int((dist <= NEAR_DUP_BITS).any(axis=1).sum())
            # CIFAKE 32x32 quá nhỏ, dHash dễ trùng ngẫu nhiên nên chỉ cảnh báo
            check(
                exact == 0,
                f"{dataset} {split}: {exact} ảnh trùng hệt train",
                warn=dataset == "cifake",
            )
            check(
                near == 0,
                f"{dataset} {split}: {near} ảnh gần trùng train (dHash <= {NEAR_DUP_BITS})",
                warn=True,
            )


def check_balance(df: pd.DataFrame) -> None:
    print("6. Cân bằng")
    lo, hi = AI_RATIO_RANGE
    for dataset, g in df.groupby(dataset_of(df)):
        n_sources = g["source"].nunique()
        for split, s in g.groupby("split"):
            ratio = s["label"].mean()
            check(lo <= ratio <= hi, f"{dataset} {split}: {len(s)} ảnh, {ratio:.0%} AI")
            check(
                s["source"].nunique() == n_sources,
                f"{dataset} {split}: có đủ {n_sources} nguồn",
            )
    print()
    print(pd.crosstab(df["source"], df["split"], margins=True).to_string())


def main() -> None:
    df = pd.read_csv(LABELS_CSV)
    print(f"{LABELS_CSV}: {len(df)} dòng\n")
    check_schema(df)
    check_labels(df)
    check_files(df)
    # File thiếu đã báo ở bước 3; các bước sau chỉ xét ảnh đọc được
    present = df[df["filepath"].map(lambda p: Path(p).is_file())]
    present = present.assign(dhash=np.array(check_images(present), dtype=np.uint64))
    check_leakage(present)
    check_balance(df)
    print(f"\n{len(failures)} lỗi, {len(warnings)} cảnh báo")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
