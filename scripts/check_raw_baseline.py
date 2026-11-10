"""Doi chieu DOC LAP du lieu tho voi baseline (T013, spec 001).

Chay: python -m scripts.check_raw_baseline --raw-dir <data/raw cua T013>
      [--rejected-small data/processed/rejected_small.csv]

Khac scripts.check_normalization (T016, dung models.normalize): script nay KHONG
import normalize_image. No dung lai dung cong thuc cua prepare_data cu (commit ghi
trong baseline): exif_transpose -> RGB -> fit 256 BICUBIC (chi genimage) -> JPEG q95,
roi so sha256 voi data/processed_baseline.sha256 cho MOI dong baseline (gom ca anh
nho ma code cu da phong to). Neu co --rejected-small, kiem ca ngoai <256px.
In so tep OK / FAILED / thieu; kiem phien ban: header baseline (commit, pillow,
sha labels.csv), norm_version trong labels/rejected neu co.
Chi doc. Ma thoat: 0 dat; 1 lech/thieu/sai phien ban; 2 thieu dau vao (neu cach
chay T013); 3 anh tho hong.
"""

import argparse
import hashlib
import re
import sys
from io import BytesIO
from pathlib import Path

import PIL
from PIL import Image, ImageOps

from models.normalize import MIN_SIDE, NORMALIZATION_VERSION
from scripts.check_normalization import (
    UNREADABLE,
    _posix,
    _read_csv,
    _rel,
    check_small_records,
    read_baseline,
)

SIZE, QUALITY = 256, 95
GUIDE = (
    "T013: dung ban sao ma cu ngoai repo (git archive <commit trong baseline> | "
    "tar -x -C <thu muc rieng>), tai du lieu tho bang script cua ban sao do (~4 GB), "
    "roi chay lai voi --raw-dir <thu muc rieng>/data/raw. Khong chep du lieu tho vao repo."
)


def legacy_jpeg(source: Path, genimage: bool) -> tuple[bytes, int]:
    """(jpeg bytes, canh ngan sau orientation) theo cong thuc prepare_data cu."""
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        short = min(image.size)
        if genimage:
            image = ImageOps.fit(image, (SIZE, SIZE), Image.Resampling.BICUBIC)
        with BytesIO() as buffer:
            image.save(buffer, "JPEG", quality=QUALITY)
            return buffer.getvalue(), short


def check_header(path: Path, labels_path: Path) -> tuple[list[str], str]:
    """(loi, canh bao Pillow hoac chuoi rong)."""
    header = {
        m[1]: m[2].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if (
            m := re.match(
                r"# (prepare_data_commit|pillow|labels_csv_sha256): (.*)", line
            )
        )
    }
    errors = [
        f"Baseline header lacks '{key}'"
        for key in ("prepare_data_commit", "pillow", "labels_csv_sha256")
        if key not in header
    ]
    if "labels_csv_sha256" in header:
        actual = hashlib.sha256(labels_path.read_bytes()).hexdigest()
        if actual != header["labels_csv_sha256"]:
            errors.append(f"{labels_path} sha256 differs from baseline header")
    note = ""
    if header.get("pillow", PIL.__version__) != PIL.__version__:
        # Khong la loi: chi la nguyen nhan co the cua lech sha, de nguoi chay doc.
        note = f"WARNING: Pillow {PIL.__version__} != baseline {header['pillow']}"
        print(note, file=sys.stderr)
    return errors, note


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--labels", type=Path, default=Path("data/labels.csv"))
    parser.add_argument(
        "--baseline", type=Path, default=Path("data/processed_baseline.sha256")
    )
    parser.add_argument("--rejected-small", type=Path)
    args = parser.parse_args(argv)

    needed = [args.raw_dir, args.labels, args.baseline]
    needed += [args.rejected_small] if args.rejected_small else []
    missing = [str(p) for p in needed if not p.exists()]
    if missing or not any(args.raw_dir.glob("*/*")):
        print(
            f"Missing required input, tried: {', '.join(missing) or args.raw_dir}",
            file=sys.stderr,
        )
        print(GUIDE, file=sys.stderr)
        return 2

    labels = _read_csv(args.labels)
    baseline, errors = read_baseline(args.baseline)
    header_errors, pillow_note = check_header(args.baseline, args.labels)
    errors += header_errors
    raw_of = {_posix(r["filepath"]).as_posix(): r["raw_path"] for r in labels}
    if len(baseline) != len(labels) or set(baseline) != set(raw_of):
        errors.append(f"Baseline ({len(baseline)}) and labels ({len(labels)}) differ")
    bad = {r.get("norm_version") for r in labels if "norm_version" in r} - {
        NORMALIZATION_VERSION
    }
    errors += [f"labels norm_version {v!r} != {NORMALIZATION_VERSION!r}" for v in bad]

    ok = failed = absent = 0
    small: set[str] = set()
    unreadable = False
    for processed, expected in sorted(baseline.items()):
        if processed not in raw_of:
            continue
        rel = _rel(raw_of[processed], args.raw_dir)
        source = args.raw_dir / rel
        if not source.is_file():
            absent += 1
            errors.append(f"Raw image missing: tried {source}")
            continue
        try:
            jpeg, short = legacy_jpeg(source, rel.parts[0] != "cifake")
        except (OSError, Image.DecompressionBombError) as exc:
            unreadable = True
            errors.append(f"{UNREADABLE}: {source} ({type(exc).__name__}: {exc})")
            continue
        if rel.parts[0] != "cifake" and short < MIN_SIDE:
            small.add(rel.as_posix())
        if hashlib.sha256(jpeg).hexdigest() == expected:
            ok += 1
        else:
            failed += 1
            errors.append(f"sha256 differs from baseline: {source}")
    print(f"Baseline: OK {ok}, FAILED {failed}, missing {absent}, of {len(baseline)}")
    if failed and pillow_note:  # canh dong FAILED de khong bi bo sot
        print(f"{pillow_note}: sha lech co the do phien ban Pillow")
    print(f"Small (<{MIN_SIDE}px, upscaled by legacy code): {len(small)}")
    if not args.rejected_small:
        print(
            "WARNING: khong co --rejected-small: KHONG kiem anh nho <256px "
            "(ket qua OK khong gom kiem tra nay)",
            file=sys.stderr,
        )

    if args.rejected_small:
        rows = _read_csv(args.rejected_small)
        bad = {r.get("norm_version") for r in rows} - {NORMALIZATION_VERSION}
        errors += [
            f"rejected_small norm_version {v!r} != {NORMALIZATION_VERSION!r}"
            for v in bad
        ]
        errors += check_small_records(rows, args.raw_dir)
        rejected = {_rel(r["raw_path"], args.raw_dir).as_posix() for r in rows}
        errors += [
            f"Small image not in rejected_small: {p}" for p in sorted(small - rejected)
        ]
        print(f"Rejected small: {len(rejected)} recorded, {len(small)} expected")
    for error in errors:
        print(error, file=sys.stderr)
    print("FAILED" if errors else "OK")
    if unreadable:
        return 3
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
