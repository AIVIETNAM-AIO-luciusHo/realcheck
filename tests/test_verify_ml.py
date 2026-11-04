"""Verify the audit itself fails on broken parity; mock CLIP, never download it."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from models.normalize import ImageTooSmall, normalize_image
from scripts import verify_ml


class Tensor:
    def __init__(self, values):
        self.values = np.asarray(values)
        self.shape = self.values.shape

    def cpu(self):
        return self

    def numpy(self):
        return self.values


@pytest.fixture
def verification(tmp_path, monkeypatch):
    raw = tmp_path / "raw.png"
    Image.new("RGB", (300, 280), "orange").save(raw)
    processed = tmp_path / "processed.jpg"
    with Image.open(raw) as image:
        processed.write_bytes(normalize_image(image).jpeg)
    rows = [
        {"source": "genimage_real", "split": "test", "raw_path": "must-not-read.png"},
        {
            "source": "genimage_real",
            "split": "val",
            "raw_path": str(raw),
            "filepath": str(processed),
        },
    ]
    features = np.array([[99.0], [0.2]], dtype=np.float32)
    monkeypatch.setattr(
        verify_ml, "load_features", Mock(return_value=(features, rows, {}))
    )
    encoder = SimpleNamespace(
        training=False,
        parameters=lambda: [SimpleNamespace(requires_grad=False)],
        preprocess=lambda images: {"pixels": Tensor(np.asarray(images[0]))},
    )
    calls = []

    class Scorer:
        ai_column = 1
        probe = SimpleNamespace(
            predict_proba=lambda x: np.column_stack([1 - x[:, 0], x[:, 0]])
        )

        def __call__(self, image):
            if min(image.size) < 256:
                raise ImageTooSmall(*image.size)
            calls.append(image.size)
            return 0.2

    scorer = Scorer()
    scorer.encoder = encoder
    monkeypatch.setattr(verify_ml, "load_scorer", Mock(return_value=scorer))
    model = tmp_path / "probe.joblib"
    model.write_bytes(b"mock model")
    labels = tmp_path / "labels.csv"
    labels.write_text("fixture manifest", encoding="utf-8")
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_ml",
            "--labels",
            str(labels),
            "--model",
            str(model),
            "--report",
            str(report),
        ],
    )
    return rows, scorer, processed, report, calls


def test_verify_ml_selects_validation_and_records_environment(verification):
    _rows, _scorer, _processed, report, calls = verification
    verify_ml.main()
    result = json.loads(report.read_text())
    assert result["test_split_evaluated"] is False
    assert len(result["samples"]) == 1
    assert result["samples"][0]["split"] == "val"
    assert result["samples"][0]["tensor_exact_match"] is True
    assert result["small_image_rejected"] is True
    assert len(calls) == 4 and (4000, 3000) in calls
    assert result["run"]["python"]
    assert result["run"]["platform"]
    assert result["run"]["command"][1:3] == ["-m", "scripts.verify_ml"]


@pytest.mark.parametrize(
    "failure",
    [
        "jpeg",
        "tensor",
        "score",
        "training",
        "gradients",
        "no_validation",
        "no_genimage",
    ],
)
def test_verify_ml_rejects_invalid_evidence_without_writing_report(
    verification, failure
):
    rows, scorer, processed, report, _calls = verification
    if failure == "jpeg":
        Image.new("RGB", (256, 256), "blue").save(processed, "JPEG")
    elif failure == "tensor":
        scorer.encoder.preprocess = Mock(
            side_effect=[{"pixels": Tensor([1])}, {"pixels": Tensor([2])}]
        )
    elif failure == "score":
        scorer.probe.predict_proba = lambda x: np.array([[0.1, 0.9]])
    elif failure == "training":
        scorer.encoder.training = True
    elif failure == "gradients":
        scorer.encoder.parameters = lambda: [SimpleNamespace(requires_grad=True)]
    elif failure == "no_validation":
        rows[1]["split"] = "train"
    else:
        for row in rows:
            row["source"] = "cifake_real"
    with pytest.raises((AssertionError, ValueError)):
        verify_ml.main()
    assert not report.exists()
