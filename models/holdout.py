"""Select test images unseen in the recorded train/validation histories, no model."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from PIL import Image

from models.extract_features import read_labels, sha256_file

SOURCES = {"genimage_real", "genimage_sd14", "genimage_midjourney", "genimage_glide"}


def select_holdout(rows: list[dict], histories: list[Path]) -> tuple[list[int], dict]:
    """History files are evidence inputs, not proof that unrecorded runs never existed."""
    seen_paths, seen_pixels, snapshots = set(), set(), []

    def pixel_hash(row):
        with Image.open(row["filepath"]) as image:
            # Include dimensions so different shapes cannot alias the same byte buffer.
            content = str(image.size).encode() + image.convert("RGB").tobytes()
        return hashlib.sha256(content).hexdigest()

    for path in histories:
        before = sha256_file(path)
        previous = read_labels(path)
        exposed = hashlib.sha256()
        for row in previous:
            if row["split"] in {"train", "val"}:
                digest = pixel_hash(row)
                seen_paths.add(Path(row["raw_path"]).resolve())
                seen_pixels.add(digest)
                exposed.update((row["split"] + ":" + digest + "\n").encode())
        if sha256_file(path) != before:
            raise ValueError("History labels changed during holdout selection")
        snapshots.append(
            {
                "labels_sha256": before,
                "rows": len(previous),
                "exposed_pixels_sha256": exposed.hexdigest(),
            }
        )
    for row in rows:
        if row["split"] in {"train", "val"}:
            seen_paths.add(Path(row["raw_path"]).resolve())
            seen_pixels.add(pixel_hash(row))

    selected, excluded, unique_test_pixels = [], [], set()
    candidates = [
        i
        for i, row in enumerate(rows)
        if row["source"] in SOURCES and row["split"] == "test"
    ]
    for index in candidates:
        row = rows[index]
        digest = pixel_hash(row)
        if Path(row["raw_path"]).resolve() in seen_paths or digest in seen_pixels:
            reason = "recorded_train_or_validation"
        elif digest in unique_test_pixels:
            reason = "duplicate_test_pixels"
        else:
            selected.append(index)
            unique_test_pixels.add(digest)
            continue
        excluded.append({"row_index": index, "source": row["source"], "reason": reason})
    if {rows[i]["source"] for i in selected} != SOURCES:
        raise ValueError("Unseen holdout needs all four GenImage sources")
    return selected, {
        "policy": "exclude_recorded_train_and_validation_and_duplicate_pixels",
        "histories": snapshots,
        "test_rows_before_filter": len(candidates),
        "selected_row_indices": selected,
        "selected_by_source": dict(Counter(rows[i]["source"] for i in selected)),
        "excluded": excluded,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--history-labels", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; do not overwrite the holdout record")
    before = sha256_file(args.labels)
    indices, selection = select_holdout(read_labels(args.labels), args.history_labels)
    if sha256_file(args.labels) != before:
        raise ValueError("Candidate labels changed during holdout selection")
    record = {
        "status": "proposed_pending_independent_QA",
        "labels_sha256": before,
        "test_rows": len(indices),
        "holdout": selection,
        "model_test_evaluated": False,
        "limitations": [
            "Only the supplied histories are checked; group review is still required"
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"Selected {len(indices)} test rows; no model predictions were made")


if __name__ == "__main__":
    main()
