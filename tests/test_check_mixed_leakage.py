"""ADV-09: leakage check of a new dataset's metadata against a protected manifest."""

import csv
import hashlib
import json

import numpy as np
import pytest
from PIL import Image

from scripts import check_mixed_leakage as cml
from scripts.check_data import dhash


def image(path, seed, size=(64, 64)):
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 255, (*size, 3), dtype=np.uint8)).save(path)
    return path


def test_hamming_min_finds_the_closest_reference():
    queries = np.array([0b1111, 0], dtype=np.uint64)
    references = np.array([0b0111, 2**63], dtype=np.uint64)
    assert cml.hamming_min(queries, references).tolist() == [1, 1]
    assert cml.hamming_min(queries, np.array([], dtype=np.uint64)).tolist() == [64, 64]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Protected manifest with one image per split, plus a selection reusing some of them."""
    monkeypatch.chdir(tmp_path)
    rows, digests = [], {}
    for split, seed in (("train", 1), ("val", 2), ("test", 3)):
        raw = image(tmp_path / f"raw_{split}.png", seed)
        rows.append(
            {
                "filepath": raw.name,
                "raw_path": raw.name,
                "source": "genimage_real",
                "split": split,
            }
        )
        digests[split] = (
            hashlib.sha256(raw.read_bytes()).hexdigest(),
            dhash(Image.open(raw)),
        )
    with (tmp_path / "labels.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def write_selection(entries):
        path = tmp_path / "selection.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        return path

    return write_selection, digests


def selection_row(cohort, digest):
    raw_sha, hash_value = digest
    return {"cohort": cohort, "raw_sha256": raw_sha, "dhash": int(hash_value)}


def test_train_overlap_is_allowed_but_val_test_overlap_fails(setup, capsys):
    write_selection, digests = setup
    clean = write_selection(
        [
            selection_row("expanded_train", digests["train"]),
            selection_row("new_validation", ("x", 0)),
        ]
    )
    with pytest.raises(SystemExit) as exit_info:
        cml.main(["--selection", str(clean), "--protected", "labels.csv"])
    assert exit_info.value.code == 0
    assert "train: exact 1, near 1" in capsys.readouterr().out
    leaked = write_selection([selection_row("expanded_train", digests["test"])])
    with pytest.raises(SystemExit) as exit_info:
        cml.main(["--selection", str(leaked), "--protected", "labels.csv"])
    assert exit_info.value.code == 1
    assert "test: exact 1, near 1" in capsys.readouterr().out


def test_near_duplicates_inside_the_new_dataset_fail(setup, capsys):
    write_selection, _ = setup
    selection = write_selection(
        [
            {"cohort": "expanded_train", "raw_sha256": "a", "dhash": 0b1111},
            {"cohort": "core_test", "raw_sha256": "b", "dhash": 0b0111},  # 1 bit apart
        ]
    )
    with pytest.raises(SystemExit) as exit_info:
        cml.main(["--selection", str(selection), "--protected", "labels.csv"])
    assert exit_info.value.code == 1
    assert "core_test        near 1" in capsys.readouterr().out


def test_missing_input_exits_two(setup):
    with pytest.raises(SystemExit) as exit_info:
        cml.main(["--selection", "none.jsonl", "--protected", "labels.csv"])
    assert exit_info.value.code == 2
