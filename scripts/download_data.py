"""Tải CIFAKE (D1) và một phần GenImage (D2) về data/raw/.

Ảnh được lưu nguyên byte gốc (giữ cả định dạng PNG/JPEG để D4 đo được
thiên lệch định dạng).

Cách chạy (từ thư mục gốc repo):
    python scripts/download_data.py cifake
    python scripts/download_data.py genimage
"""

import argparse
import io
import random
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from huggingface_hub import hf_hub_download, list_repo_files
from PIL import Image

RAW_DIR = Path("data/raw")
GENIMAGE_DIR = RAW_DIR / "genimage"
SEED = 42

CIFAKE_REPO = "dragonintelligence/CIFAKE-image-dataset"
# Nhãn trong repo: 0 = FAKE, 1 = REAL (ngược quy ước của nhóm)
CIFAKE_CLASS = {0: "ai", 1: "real"}

TINY_REPO = "TheKernel01/Tiny-GenImage"
TINY_SOURCES = {0: "real", 3: "glide", 4: "midjourney"}  # generator id -> thư mục
# Tiny-GenImage không có SD v1.4 nên lấy từ split test của GenImage đầy đủ.
# Các hàng xếp theo nhãn (6000 thật rồi 6000 AI); shard 4 nằm trọn trong phần AI.
SD14_REPO = "nebula/GenImage-arrow"
SD14_SHARD = "data/test/stable_diffusion_v_1_4/data-00004-of-00008.arrow"


def ext_of(data: bytes) -> str:
    fmt = Image.open(io.BytesIO(data)).format
    return "jpg" if fmt == "JPEG" else fmt.lower()


@contextmanager
def fetch(repo: str, filename: str) -> Iterator[Path]:
    """Tải một file của dataset HF, xoá khỏi cache khi dùng xong."""
    path = Path(hf_hub_download(repo, filename, repo_type="dataset"))
    try:
        yield path
    finally:
        path.resolve().unlink()


def download_cifake(per_class: int) -> None:
    """Lấy per_class ảnh mỗi lớp từ mỗi split (train/test) của CIFAKE."""
    rng = random.Random(SEED)
    for split in ("train", "test"):
        path = hf_hub_download(
            CIFAKE_REPO, f"data/{split}-00000-of-00001.parquet", repo_type="dataset"
        )
        rows = pq.read_table(path).to_pylist()
        for label, cls in CIFAKE_CLASS.items():
            picked = [r["image"]["bytes"] for r in rows if r["label"] == label]
            rng.shuffle(picked)
            out = RAW_DIR / "cifake" / split / cls
            out.mkdir(parents=True, exist_ok=True)
            for i, data in enumerate(picked[:per_class]):
                (out / f"{cls}_{i:05d}.{ext_of(data)}").write_bytes(data)
            print(f"cifake/{split}/{cls}: {min(per_class, len(picked))} ảnh")


def shard_tag(filename: str) -> str:
    """'data/train-00003-of-00014.parquet' -> 'train-00003'."""
    return Path(filename).name.split("-of-")[0]


def save(
    items: Iterable[tuple[str | None, str, bytes]], quota: dict, count: dict
) -> None:
    """Ghi các bộ (nguồn, tên, byte ảnh) vào thư mục nguồn cho đến khi đủ quota.

    Tên file lấy theo vị trí ảnh trong dataset gốc, nên chạy lại không tạo
    bản trùng và mọi máy ra cùng tên file.
    """
    for src, name, data in items:
        if src is None or count[src] >= quota[src]:
            continue
        out = GENIMAGE_DIR / src / f"{src}_{name}.{ext_of(data)}"
        if not out.exists():
            out.write_bytes(data)
            count[src] += 1


def download_genimage(n_real: int, n_per_gen: int) -> None:
    quota = {
        "real": n_real,
        "glide": n_per_gen,
        "midjourney": n_per_gen,
        "sd14": n_per_gen,
    }
    count = {}
    for src in quota:
        (GENIMAGE_DIR / src).mkdir(parents=True, exist_ok=True)
        count[src] = len(list((GENIMAGE_DIR / src).iterdir()))

    def done(sources: Iterable[str]) -> bool:
        return all(count[s] >= quota[s] for s in sources)

    shards = sorted(
        f
        for f in list_repo_files(TINY_REPO, repo_type="dataset")
        if f.endswith(".parquet")
    )
    for shard in shards:
        if done(TINY_SOURCES.values()):
            break
        with fetch(TINY_REPO, shard) as path:
            rows = pq.read_table(path, columns=["image", "generator"]).to_pylist()
        tag = shard_tag(shard)
        items = (
            (TINY_SOURCES.get(r["generator"]), f"{tag}_{i:04d}", r["image"]["bytes"])
            for i, r in enumerate(rows)
        )
        save(items, quota, count)
        print(f"{shard}: {count}")

    if not done(["sd14"]):
        with fetch(SD14_REPO, SD14_SHARD) as path:
            table = pa.ipc.open_stream(path).read_all().select(["image", "label"])
        tag = shard_tag(SD14_SHARD)
        items = (
            ("sd14", f"{tag}_{i:04d}", r["image"])
            for i, r in enumerate(table.to_pylist())
            if r["label"] == 1
        )
        save(items, quota, count)
        print(f"{SD14_SHARD}: {count}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="dataset", required=True)
    c = sub.add_parser("cifake")
    c.add_argument("--per-class", type=int, default=1000)
    g = sub.add_parser("genimage")
    g.add_argument("--n-real", type=int, default=3000)
    g.add_argument("--n-per-gen", type=int, default=1000)
    args = p.parse_args()

    if args.dataset == "cifake":
        download_cifake(args.per_class)
    else:
        download_genimage(args.n_real, args.n_per_gen)


if __name__ == "__main__":
    main()
