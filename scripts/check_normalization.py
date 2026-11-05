"""Kiem tra chuan hoa (contracts C6; T016 + T022): baseline sha256 va kiem ke anh.

Chay: python -m scripts.check_normalization [--raw-dir data/raw]

Moi dong labels.csv phai (a) co anh tho doc duoc trong --raw-dir, (b) du lon,
(c) co dong trong baseline va sha256 cua jpeg do normalize_image sinh ra phai
trung baseline (KHONG so voi data/processed hien tai). Kiem ke: moi anh tho co
dung mot noi: labels.csv, hoac rejected_small / rejected_invalid /
rejected_duplicate (.csv, cung thu muc --rejected-dir hoac chi dinh rieng).
Ban ghi rejected_small phai tro toi anh thuc su nho (sau orientation).
rejected_duplicate.csv tuy chon: chua co thi coi la rong (prepare_data chua ghi
file nay, viec cua Loan/Kiet); khi do anh bi loai trung se bi bao "Lost".
Script chi doc, khong ghi/xoa gi.

Ma thoat: 0 dat; 1 kiem tra that bai (lech hash, thieu baseline, lost, ...);
2 thieu dau vao/cau hinh (neu duong dan da thu); 3 co anh tho hong khong doc duoc.
"""

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

from PIL import Image, ImageOps

from models.normalize import (
    MIN_SIDE,
    NORMALIZATION_VERSION,
    ImageTooSmall,
    normalize_image,
)

DEFAULT_RAW = "data/raw"
BASELINE_LINE = re.compile(r"([0-9a-f]{64})  (\S.*)")
UNREADABLE = "Unreadable raw image"
LABEL_COLUMNS = {"filepath", "label", "source", "split", "raw_path", "norm_version"}
REJECTED_COLUMNS = {"raw_path", "source", "width", "height", "reason", "norm_version"}


def _posix(path: str) -> PurePosixPath:
    return PurePosixPath(path.strip().replace("\\", "/"))


def _rel(raw_path: str, raw_dir: Path) -> PurePosixPath:
    """Path of a raw image relative to the raw root, whatever prefix was recorded."""
    path = _posix(raw_path)
    for prefix in (PurePosixPath(DEFAULT_RAW), PurePosixPath(raw_dir.as_posix())):
        if path.is_relative_to(prefix):
            path = path.relative_to(prefix)
            break
    if (
        path.is_absolute()
        or PureWindowsPath(path.as_posix()).drive
        or not path.parts
        or ".." in path.parts
        or not (raw_dir / path).resolve().is_relative_to(raw_dir.resolve())
    ):
        raise ValueError(f"raw_path outside raw root: {raw_path!r}")
    return path


def _read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        fields = reader.fieldnames or []
        if not required.issubset(fields) or len(fields) != len(set(fields)):
            raise ValueError(f"{path}: missing required or duplicate CSV columns")
        rows = list(reader)
    for number, row in enumerate(rows, 2):
        if None in row or any(not (row.get(key) or "").strip() for key in required):
            raise ValueError(f"{path}: malformed or empty CSV cell at line {number}")
        if row["norm_version"] != NORMALIZATION_VERSION:
            raise ValueError(f"{path}: unsupported norm_version at line {number}")
    return rows


def read_baseline(path: Path) -> tuple[dict[str, str], list[str]]:
    """({processed path: sha256}, errors) from 'sha256  path' lines; '#' ignored."""
    result, errors = {}, []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        match = BASELINE_LINE.fullmatch(line.rstrip())
        if match is None:
            errors.append(f"Malformed baseline line {number}: {line!r}")
        else:
            key = _posix(match[2]).as_posix()
            if key in result:
                errors.append(f"Duplicate baseline entry at line {number}: {key}")
            result[key] = match[1]
    return result, errors


def raw_images(raw_dir: Path) -> set[PurePosixPath]:
    """Same discovery as scripts.prepare_data.collect_raw, relative to raw_dir."""
    found = list(raw_dir.glob("genimage/*/*")) + list(raw_dir.glob("cifake/*/*/*"))
    return {_posix(f.relative_to(raw_dir).as_posix()) for f in found if f.is_file()}


def check_labels(labels, baseline, raw_dir) -> list[str]:
    errors, compared = [], 0
    for row in labels:
        rel = _rel(row["raw_path"], raw_dir)
        source = raw_dir / rel
        if not source.is_file():
            errors.append(f"Raw image missing: tried {source}")
            continue
        try:
            with Image.open(source) as image:
                jpeg = normalize_image(image, resize=rel.parts[0] != "cifake").jpeg
        except ImageTooSmall:
            errors.append(f"Image too small but listed in labels: {source}")
            continue
        except (OSError, Image.DecompressionBombError) as exc:
            errors.append(f"{UNREADABLE}: {source} ({type(exc).__name__}: {exc})")
            continue
        expected = baseline.get(_posix(row["filepath"]).as_posix())
        if expected is None:
            errors.append(f"No baseline entry for {row['filepath']} ({source})")
        elif hashlib.sha256(jpeg).hexdigest() != expected:
            errors.append(f"sha256 differs from baseline: {source}")
        else:
            compared += 1
    if compared == 0:
        errors.append(
            "Baseline: nothing was compared (no label row matched a baseline entry)"
        )
    print(f"Baseline: compared {compared} of {len(labels)} label row(s)")
    return errors


def check_small_records(rejected_small, raw_dir) -> list[str]:
    """Each rejected_small record must point to an existing, truly small image."""
    errors = []
    for row in rejected_small:
        rel = _rel(row["raw_path"], raw_dir)
        source = raw_dir / rel
        if not source.is_file():
            errors.append(f"Rejected record for missing raw image: tried {source}")
            continue
        try:
            with Image.open(source) as image:
                short_side = min(ImageOps.exif_transpose(image).size)
        except (OSError, Image.DecompressionBombError) as exc:
            errors.append(f"{UNREADABLE}: {source} ({type(exc).__name__}: {exc})")
            continue
        if short_side >= MIN_SIDE or rel.parts[0] == "cifake":
            errors.append(
                f"Recorded as too small but not small ({short_side}px): {source}"
            )
    return errors


def check_inventory(labels, rejected, raw_dir) -> list[str]:
    errors = []
    kept_paths = [_rel(row["raw_path"], raw_dir) for row in labels]
    kept = set(kept_paths)
    if len(kept_paths) != len(kept):
        errors.append("An image has more than one label record")
    refused = [_rel(row["raw_path"], raw_dir) for row in rejected]
    refused_set = set(refused)
    if len(refused) != len(refused_set):
        errors.append("An image has more than one rejection record")
    on_disk = raw_images(raw_dir)
    errors += [f"In both labels and rejected: {p}" for p in sorted(kept & refused_set)]
    errors += [
        f"Rejected record for missing raw image: tried {raw_dir / p}"
        for p in sorted(refused_set - on_disk)
    ]
    lost = on_disk - kept - refused_set
    errors += [f"Lost (in neither labels nor rejected): {p}" for p in sorted(lost)]
    print(
        f"Inventory: {len(on_disk)} raw, {len(kept)} kept, {len(refused_set)} rejected"
    )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=Path(DEFAULT_RAW))
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument(
        "--baseline", type=Path, default=Path("data/processed_baseline.sha256")
    )
    parser.add_argument("--rejected-dir", type=Path, default=Path("data/processed"))
    for kind in ("small", "invalid", "duplicate"):
        parser.add_argument(
            f"--rejected-{kind}",
            type=Path,
            help=f"default: <rejected-dir>/rejected_{kind}.csv",
        )
    args = parser.parse_args(argv)

    paths = {
        kind: getattr(args, f"rejected_{kind}")
        or args.rejected_dir / f"rejected_{kind}.csv"
        for kind in ("small", "invalid", "duplicate")
    }
    needed = [args.raw_dir, args.labels, args.baseline, paths["small"]]
    needed += [
        paths[kind]
        for kind in ("invalid", "duplicate")
        if getattr(args, f"rejected_{kind}") is not None
    ]
    missing = [
        str(p) for p in needed if not (p.is_dir() if p == args.raw_dir else p.is_file())
    ]
    if missing:
        print("Missing required input, tried: " + ", ".join(missing), file=sys.stderr)
        return 2
    try:
        records = {
            k: _read_csv(p, REJECTED_COLUMNS) if p.exists() else []
            for k, p in paths.items()
        }
        labels = _read_csv(args.labels, LABEL_COLUMNS)
        for row in labels + [r for rows in records.values() for r in rows]:
            _rel(row["raw_path"], args.raw_dir)
        baseline, errors = read_baseline(args.baseline)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    rejected = [row for rows in records.values() for row in rows]
    errors += check_labels(labels, baseline, args.raw_dir)
    errors += check_small_records(records["small"], args.raw_dir)
    errors += check_inventory(labels, rejected, args.raw_dir)
    for error in errors:
        print(error, file=sys.stderr)
    print("FAILED" if errors else "OK")
    if any(e.startswith(UNREADABLE) for e in errors):
        return 3
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
