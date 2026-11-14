"""Đóng gói ảnh gốc GenImage train cho Locust (#123), không cần model/CLIP."""

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import warnings
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

from PIL import Image

# D06/D07 và normalization v1; không nhập runtime ML để đóng gói dữ liệu.
MAX_BYTES = 5_242_880
MAX_PIXELS = 24_000_000
MAX_SIDE = 10_000
MIN_SIDE = 256
QUOTAS = {
    "genimage_real": ("JPEG", 100, "0"),
    "genimage_glide": ("PNG", 33, "1"),
    "genimage_midjourney": ("PNG", 33, "1"),
    "genimage_sd14": ("PNG", 34, "1"),
}
FIELDS = [
    "filename",
    "sha256",
    "size_bytes",
    "width",
    "height",
    "label",
    "source",
    "source_filepath",
    "raw_path",
    "split",
    "group_id",
]
REQUIRED = {
    "filepath",
    "raw_path",
    "source",
    "split",
    "label",
    "group_id",
    "norm_version",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def raw_file(value: str, root: Path) -> Path:
    """Map canonical data/raw paths to a supplied raw root, rejecting escapes."""
    path = PurePosixPath(value.replace("\\", "/"))
    prefix = PurePosixPath("data/raw")
    if not path.is_relative_to(prefix) or ".." in path.parts or ":" in value:
        raise ValueError(f"Unsafe raw_path: {value}")
    relative = path.relative_to(prefix)
    if not relative.parts or relative.parts[0] != "genimage":
        raise ValueError(f"Expected GenImage raw_path: {value}")
    target = (root / Path(*relative.parts)).resolve()
    if not target.is_relative_to((root / "genimage").resolve()):
        raise ValueError(f"raw_path escapes GenImage root: {value}")
    if not target.is_relative_to(root):
        raise ValueError(f"raw_path escapes raw root: {value}")
    return target


def candidates(content: bytes, root: Path) -> tuple[dict, Counter]:
    """Validate metadata and inspect only allowlisted train images; never read test."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
    fields = reader.fieldnames or []
    if not REQUIRED.issubset(fields) or len(fields) != len(set(fields)):
        raise ValueError(
            "labels.csv needs unique columns: " + ", ".join(sorted(REQUIRED))
        )
    rows = list(reader)
    for row in rows:
        if None in row or any(not row.get(key) for key in REQUIRED):
            raise ValueError("Malformed or empty labels row")
        if row["split"] not in {"train", "val", "test"} or row["label"] not in {
            "0",
            "1",
        }:
            raise ValueError("Invalid split or label")
    protected = {r["group_id"] for r in rows if r["split"] == "test"}
    pools = {source: [] for source in QUOTAS}
    skipped = Counter()
    seen_paths, seen_hashes = set(), {}
    for row in sorted(rows, key=lambda r: r["raw_path"]):
        source = row["source"]
        if source not in QUOTAS or row["split"] != "train":
            continue
        fmt, _, label = QUOTAS[source]
        if row["label"] != label or row["norm_version"] != "1":
            raise ValueError(f"Label/version mismatch: {row['raw_path']}")
        if row["group_id"] in protected:
            raise ValueError(f"Train group overlaps test: {row['group_id']}")
        path = raw_file(row["raw_path"], root)
        recorded = PurePosixPath(row["raw_path"].replace("\\", "/"))
        if recorded.parent != PurePosixPath("data/raw/genimage") / source.removeprefix(
            "genimage_"
        ):
            raise ValueError(f"Source/path mismatch: {row['raw_path']}")
        processed = PurePosixPath(row["filepath"].replace("\\", "/"))
        if (
            not processed.is_relative_to("data/processed/genimage")
            or ".." in processed.parts
        ):
            raise ValueError("Expected relative GenImage processed filepath")
        if path in seen_paths:
            raise ValueError(f"Duplicate raw_path: {row['raw_path']}")
        seen_paths.add(path)
        # Missing files are input errors, not silently replaced samples.
        size = path.stat().st_size
        if not 0 < size <= MAX_BYTES:
            skipped["empty_or_oversize"] += 1
            continue
        data = path.read_bytes()
        if len(data) != size:
            raise ValueError(f"Source changed while reading: {row['raw_path']}")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    width, height = image.size
                    suffixes = {".jpg", ".jpeg"} if fmt == "JPEG" else {".png"}
                    if image.format != fmt or path.suffix.lower() not in suffixes:
                        skipped["format"] += 1
                        continue
                    if getattr(image, "n_frames", 1) != 1:
                        skipped["multiframe"] += 1
                        continue
                    if (
                        min(width, height) < MIN_SIDE
                        or max(width, height) > MAX_SIDE
                        or width * height > MAX_PIXELS
                    ):
                        skipped["dimensions"] += 1
                        continue
                    image.load()
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ):
            skipped["decode"] += 1
            continue
        sha = digest(data)
        if sha in seen_hashes:
            if seen_hashes[sha] != label:
                raise ValueError("Identical bytes have conflicting labels")
            skipped["duplicate_sha256"] += 1
            continue
        seen_hashes[sha] = label
        group = "jpeg" if fmt == "JPEG" else "png"
        extension = ".jpg" if fmt == "JPEG" else ".png"
        pools[source].append(
            {
                "filename": f"{group}/{source}-{sha}{extension}",
                "sha256": sha,
                "size_bytes": size,
                "width": width,
                "height": height,
                "label": label,
                "source": source,
                "source_filepath": row["filepath"],
                "raw_path": row["raw_path"],
                "split": row["split"],
                "group_id": row["group_id"],
            }
        )
    return pools, skipped


def select(pools: dict) -> list[dict]:
    """Take evenly spaced order statistics in each source, including both extremes."""
    selected = []
    for source, (_, count, _) in QUOTAS.items():
        pool = sorted(
            pools[source],
            key=lambda r: (
                r["width"] * r["height"],
                r["size_bytes"],
                r["raw_path"],
            ),
        )
        if len(pool) < count:
            raise ValueError(f"Not enough {source}: {len(pool)} valid, need {count}")
        indices = (
            [i * (len(pool) - 1) // (count - 1) for i in range(count)]
            if count > 1
            else [len(pool) // 2]
        )
        selected.extend(pool[i] for i in indices)
    return sorted(selected, key=lambda r: r["filename"])


def verify_zip(path: Path, rows: list[dict], metadata: dict[str, bytes]) -> None:
    """Read every archived byte again; reject missing, extra or corrupt members."""
    with zipfile.ZipFile(path) as archive:
        expected = {row["filename"] for row in rows} | set(metadata)
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(
            expected
        ):
            raise ValueError("ZIP inventory mismatch")
        for row in rows:
            data = archive.read(row["filename"])
            if len(data) != row["size_bytes"] or digest(data) != row["sha256"]:
                raise ValueError(f"ZIP checksum mismatch: {row['filename']}")
        for name, data in metadata.items():
            if archive.read(name) != data:
                raise ValueError(f"ZIP metadata mismatch: {name}")


def build(labels: Path, raw_dir: Path, out: Path) -> dict:
    """Build folder, ZIP and ZIP checksum without overwriting existing artifacts."""
    out = out.absolute()
    archive_path = Path(str(out) + ".zip")
    checksum_path = Path(str(archive_path) + ".sha256")
    if any(p.exists() for p in (out, archive_path, checksum_path)):
        raise ValueError("Output already exists; choose a new --out")
    content = labels.read_bytes()
    root = raw_dir.resolve(strict=True)
    pools, skipped = candidates(content, root)
    rows = select(pools)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"]))
    report = {
        "commit": commit,
        "dirty": dirty,
        "labels_sha256": digest(content),
        "counts": dict(Counter(r["source"] for r in rows)),
        "skipped": dict(skipped),
        "size_bytes": {
            "min": min(r["size_bytes"] for r in rows),
            "max": max(r["size_bytes"] for r in rows),
            "total": sum(r["size_bytes"] for r in rows),
        },
        "dimensions": sorted({(r["width"], r["height"]) for r in rows}),
    }
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    readme = (
        "# Payload GenImage cho Locust (#123)\n\n"
        "Chỉ dùng đo tải, độ trễ và RPS; không dùng đánh giá độ chính xác.\n"
        "Chỉ ảnh gốc train trong labels.csv; giữ nguyên byte, không resize/nén lại.\n"
        "JPEG là ảnh thật; PNG là ảnh AI (GLIDE/Midjourney/SD1.4).\n"
        "Chọn cách đều trên thứ tự (diện tích pixel, dung lượng, raw_path) mỗi nguồn.\n"
        "Nguồn: GenImage (NeurIPS 2023), Tiny-GenImage và nebula/GenImage-arrow; "
        "chỉ dùng trong nhóm cho dự án học tập, không phát hành lại công khai.\n\n"
        "Kiểm ZIP bằng sha256sum -c <ten-goi>.zip.sha256 (hoặc Get-FileHash trên PowerShell).\n"
        "Sau giải nén: RC_PAYLOAD_DIR trỏ tới thư mục chứa trực tiếp jpeg/ và png/.\n"
        "Đặt RC_MIX=jpeg=50,png=50; chạy Locust từ máy đo riêng qua gateway.\n"
        "payload-manifest.csv ghi SHA256 của từng file để kiểm sau giải nén.\n\n"
        "```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n"
    )
    metadata = {
        "payload-manifest.csv": csv_buffer.getvalue().encode("utf-8"),
        "README.md": readme.encode("utf-8"),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".payload-", dir=out.parent) as temporary:
        stage = Path(temporary)
        folder = stage / "payloads"
        folder.mkdir()
        for row in rows:
            data = raw_file(row["raw_path"], root).read_bytes()
            if digest(data) != row["sha256"]:
                raise ValueError(f"Source changed before copy: {row['raw_path']}")
            target = folder / row["filename"]
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(data)
        for name, data in metadata.items():
            (folder / name).write_bytes(data)
        if labels.read_bytes() != content:
            raise ValueError("labels.csv changed during packaging")
        staged_zip = stage / "payload.zip"
        with zipfile.ZipFile(
            staged_zip, "w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for file in sorted(p for p in folder.rglob("*") if p.is_file()):
                entry = zipfile.ZipInfo(
                    file.relative_to(folder).as_posix(), (1980, 1, 1, 0, 0, 0)
                )
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, file.read_bytes())
        verify_zip(staged_zip, rows, metadata)
        with staged_zip.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        # Exclusive creation also protects against another process claiming the same output.
        out.mkdir()
        for file in folder.iterdir():
            shutil.move(str(file), out / file.name)
        staged_checksum = stage / "payload.sha256"
        staged_checksum.write_text(
            f"{sha}  {archive_path.name}\n", encoding="utf-8", newline="\n"
        )
        # Atomic, exclusive publication on the same filesystem: never expose a partial ZIP.
        os.link(staged_zip, archive_path)
        os.link(staged_checksum, checksum_path)
    return report | {"zip_sha256": sha}


def main(argv: list[str] | None = None) -> int:
    # Windows redirected consoles may default to cp1252; CLI text is UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument(
        "--out", type=Path, default=Path(".cache/locust-payloads-genimage")
    )
    args = parser.parse_args(argv)
    try:
        print(
            json.dumps(
                build(args.labels, args.raw_dir, args.out), ensure_ascii=False, indent=2
            )
        )
    except (OSError, ValueError, csv.Error, subprocess.SubprocessError) as exc:
        print(f"Payload error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
