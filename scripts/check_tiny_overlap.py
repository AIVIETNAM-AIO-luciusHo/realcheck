"""Find Tiny-GenImage images listed for training that are already in protected splits.

Identity is the Tiny-GenImage shard and row that scripts.download_data writes into
file names (``glide_train-00003_0042.png``): one shard row is one image. With
--verify-sha the bytes of every match are compared when both files exist.

Run from the repo root:
    python -m scripts.check_tiny_overlap --protected data/labels.csv \
        --candidates <labels.csv of a new dataset> [--verify-sha]

Exit 0: no overlap; 1: overlap found; 2: unreadable input.
"""

import argparse
import csv
import hashlib
import re
from collections import Counter
from pathlib import Path

TINY_ID = re.compile(r"_((?:train|validation)-\d{5})_(\d+)\.\w+$")


def tiny_identity(path: str) -> tuple[str, int] | None:
    """(shard, row) of a Tiny-GenImage file name, None for any other source."""
    match = TINY_ID.search(Path(path).name)
    return (match.group(1), int(match.group(2))) if match else None


def read_csv(path: Path, column: str) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if rows and column not in rows[0]:
        raise ValueError(f"{path.name} has no column {column!r}")
    return rows


def find_overlap(
    protected: list[dict],
    candidates: list[dict],
    candidate_column: str,
    splits: set[str],
) -> list[tuple[dict, dict]]:
    """Pairs (protected row, candidate row) sharing a Tiny-GenImage shard and row."""
    index = {}
    for row in protected:
        identity = tiny_identity(row.get("raw_path") or row["filepath"])
        if identity and row["split"] in splits:
            index[identity] = row
    return [
        (index[identity], row)
        for row in candidates
        if (identity := tiny_identity(row[candidate_column])) in index
    ]


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--protected", type=Path, default=Path("data/labels.csv"))
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--candidate-column", default="filepath")
    parser.add_argument("--splits", nargs="+", default=["val", "test"])
    parser.add_argument("--verify-sha", action="store_true")
    args = parser.parse_args(argv)
    try:
        protected = read_csv(args.protected, "split")
        candidates = read_csv(args.candidates, args.candidate_column)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{parser.prog}: error: {exc}\n")
    pairs = find_overlap(protected, candidates, args.candidate_column, set(args.splits))
    by_split = Counter(old["split"] for old, _ in pairs)
    print(
        f"Ứng viên: {len(candidates)}; trùng ảnh {'/'.join(args.splits)}: {dict(by_split)}"
    )
    if args.verify_sha:
        checked = Counter()
        for old, new in pairs:
            old_path = old.get("raw_path") or old["filepath"]
            if Path(old_path).exists() and Path(new[args.candidate_column]).exists():
                same = _sha256(old_path) == _sha256(new[args.candidate_column])
                checked["sha256 khớp" if same else "sha256 khác"] += 1
        print(f"Kiểm byte (khi có cả hai file): {dict(checked)}")
    for old, new in pairs[:5]:
        print(f"  {old['split']}: {Path(new[args.candidate_column]).name}")
    raise SystemExit(1 if pairs else 0)


if __name__ == "__main__":
    main()
