"""Holdout selection uses image identity/pixels and never model predictions."""

import csv
import json
import sys
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from models import holdout
from models.normalize import normalize_image


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def cohort(tmp_path):
    rows = []
    for split in ("train", "val", "test", "test"):
        for source in sorted(holdout.SOURCES):
            n = len(rows)
            pixels = np.random.default_rng(n).integers(
                0, 256, (280, 300, 3), dtype=np.uint8
            )
            path = tmp_path / f"{n}.jpg"
            path.write_bytes(normalize_image(Image.fromarray(pixels)).jpeg)
            rows.append(
                {
                    "filepath": str(path),
                    "raw_path": str(tmp_path / f"raw-{n}.png"),
                    "label": str(int(source != "genimage_real")),
                    "source": source,
                    "split": split,
                    "norm_version": "1",
                }
            )
    history = tmp_path / "history.csv"
    write_rows(history, rows)
    return rows, history


@pytest.mark.parametrize("previous_split", ["train", "val"])
def test_excludes_previous_fit_and_selection_rows(cohort, previous_split):
    rows, history = cohort
    old = [dict(row) for row in rows]
    old[8]["split"] = previous_split
    write_rows(history, old)
    indices, record = holdout.select_holdout(rows, [history])
    assert indices == list(range(9, 16))
    assert record["excluded"] == [
        {
            "row_index": 8,
            "source": rows[8]["source"],
            "reason": "recorded_train_or_validation",
        }
    ]
    assert record["histories"][0]["labels_sha256"] == holdout.sha256_file(history)


def test_rejects_same_pixels_under_different_paths_and_jpeg_metadata(cohort, tmp_path):
    rows, history = cohort
    alias = tmp_path / "alias.jpg"
    original = (tmp_path / "8.jpg").read_bytes()
    comment = b"different metadata"
    alias.write_bytes(
        original[:2]
        + b"\xff\xfe"
        + (len(comment) + 2).to_bytes(2, "big")
        + comment
        + original[2:]
    )
    old = [dict(row) for row in rows]
    old[8].update(filepath=str(alias), raw_path="different-raw-name.png", split="train")
    write_rows(history, old)
    indices, _ = holdout.select_holdout(rows, [history])
    assert 8 not in indices and len(indices) == 7


def test_deduplicates_test_pixels_and_requires_all_sources(cohort):
    rows, history = cohort
    rows[12]["filepath"] = rows[8]["filepath"]
    indices, record = holdout.select_holdout(rows, [])
    assert 12 not in indices and len(indices) == 7
    assert record["excluded"][0]["reason"] == "duplicate_test_pixels"
    # Both test examples of a source previously used to fit: fail, do not hide source loss.
    old = [dict(row) for row in rows]
    old[8]["split"] = old[12]["split"] = "train"
    old[12]["filepath"] = str(history.parent / "12.jpg")
    write_rows(history, old)
    with pytest.raises(ValueError, match="all four"):
        holdout.select_holdout(rows, [history])


def test_history_changed_mid_selection_is_error(cohort, monkeypatch):
    rows, history = cohort
    monkeypatch.setattr(holdout, "sha256_file", Mock(side_effect=["before", "after"]))
    with pytest.raises(ValueError, match="History labels changed"):
        holdout.select_holdout(rows, [history])


def test_history_pixel_snapshot_changes_even_when_selected_rows_do_not(
    cohort, tmp_path
):
    rows, history = cohort
    alias = tmp_path / "historical.jpg"
    alias.write_bytes((tmp_path / "0.jpg").read_bytes())
    write_rows(
        history, [{**rows[0], "filepath": str(alias), "raw_path": "historical.png"}]
    )
    before_indices, before = holdout.select_holdout(rows, [history])
    alias.write_bytes((tmp_path / "1.jpg").read_bytes())
    after_indices, after = holdout.select_holdout(rows, [history])
    assert before_indices == after_indices
    assert (
        before["histories"][0]["labels_sha256"]
        == after["histories"][0]["labels_sha256"]
    )
    assert (
        before["histories"][0]["exposed_pixels_sha256"]
        != after["histories"][0]["exposed_pixels_sha256"]
    )


def test_cli_writes_proposed_selection_without_opening_model(
    cohort, tmp_path, monkeypatch
):
    rows, history = cohort
    labels, output = tmp_path / "labels.csv", tmp_path / "selection.json"
    write_rows(labels, rows)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "holdout",
            "--labels",
            str(labels),
            "--history-labels",
            str(history),
            "--output",
            str(output),
        ],
    )
    from sklearn.linear_model import LogisticRegression

    predict = Mock(side_effect=AssertionError("No holdout inference"))
    monkeypatch.setattr(LogisticRegression, "predict_proba", predict)
    holdout.main()
    record = json.loads(output.read_text())
    assert record["test_rows"] == 8 and record["model_test_evaluated"] is False
    assert record["status"] == "proposed_pending_independent_QA"
    before = output.read_bytes()
    with pytest.raises(SystemExit):
        holdout.main()
    assert output.read_bytes() == before
    predict.assert_not_called()
