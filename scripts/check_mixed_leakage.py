"""Check a new dataset's metadata for leakage into a protected manifest, without its images.

Compares the new rows' raw SHA256 and normalized-image dHash (from the handed-over
selection.jsonl) with the protected manifest's raw files and normalized images, by split.
Also reports near duplicates inside the new dataset (train vs each evaluation cohort).
dHash is scripts.check_data.dhash on the normalized image on both sides.

Run from the repo root (the protected manifest's images must be on disk):
    python -m scripts.check_mixed_leakage \
        --selection data/metadata/realcheck_mixed_v3/run-v2/selection.jsonl \
        --protected data/labels.csv [--radius 4]

Exit 0: no exact or near duplicate of protected val/test or across new cohorts;
1: duplicates found; 2: unreadable input.
"""

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from scripts.check_data import dhash

POPCOUNT = np.array([i.bit_count() for i in range(256)], dtype=np.uint8)


def hamming_min(queries: np.ndarray, references: np.ndarray) -> np.ndarray:
    """Smallest Hamming distance from each query hash to any reference hash."""
    if not len(references):
        return np.full(len(queries), 64, dtype=np.uint8)
    best = np.full(len(queries), 64, dtype=np.uint8)
    for start in range(0, len(queries), 512):
        block = queries[start : start + 512, None] ^ references[None, :]
        bits = POPCOUNT[block.view(np.uint8).reshape(*block.shape, 8)].sum(axis=2)
        best[start : start + 512] = bits.min(axis=1)
    return best


def read_selection(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def protected_hashes(path: Path) -> dict[str, tuple[set[str], np.ndarray]]:
    """Per split: raw SHA256 set and dHash array of the protected GenImage rows."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            r for r in csv.DictReader(handle) if r["source"].startswith("genimage_")
        ]
    out = {}
    for split in sorted({r["split"] for r in rows}):
        part = [r for r in rows if r["split"] == split]
        raw = {
            hashlib.sha256(Path(r["raw_path"]).read_bytes()).hexdigest() for r in part
        }
        hashes = []
        for row in part:
            with Image.open(row["filepath"]) as image:
                hashes.append(dhash(image))
        out[split] = (raw, np.array(hashes, dtype=np.uint64))
    return out


def report(selection: list[dict], protected: dict, radius: int) -> int:
    """Print overlap tables; return the number of problems found."""
    cohorts = sorted({r["cohort"] for r in selection})
    hashes = {
        c: np.array(
            [r["dhash"] for r in selection if r["cohort"] == c], dtype=np.uint64
        )
        for c in cohorts
    }
    problems = 0
    print(f"Protected manifest (GenImage), dHash radius <= {radius}:")
    for cohort in cohorts:
        raw = {r["raw_sha256"] for r in selection if r["cohort"] == cohort}
        cells = []
        for split, (protected_raw, protected_dhash) in protected.items():
            exact = len(raw & protected_raw)
            near = int((hamming_min(hashes[cohort], protected_dhash) <= radius).sum())
            cells.append(f"{split}: exact {exact}, near {near}")
            if split != "train":
                problems += exact + near
        print(f"  {cohort:16} n={len(raw):5} | " + " | ".join(cells))
    train = next((c for c in cohorts if "train" in c), None)
    if train:
        print(f"Inside the new dataset ({train} vs each evaluation cohort):")
        for cohort in cohorts:
            if cohort == train:
                continue
            near = int((hamming_min(hashes[cohort], hashes[train]) <= radius).sum())
            problems += near
            print(f"  {cohort:16} near {near}")
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--protected", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--radius", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        selection = read_selection(args.selection)
        protected = protected_hashes(args.protected)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    print("Cohorts:", dict(Counter(r["cohort"] for r in selection)))
    raise SystemExit(1 if report(selection, protected, args.radius) else 0)


if __name__ == "__main__":
    main()
