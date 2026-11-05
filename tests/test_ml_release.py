"""Release regressions use synthetic images and never open the real holdout."""

import csv
import json
from unittest.mock import Mock

import joblib
import numpy as np
import pytest
from PIL import Image

from models.extract_features import (
    extract_features,
    load_features,
    read_labels,
    sha256_file,
)
from models.normalize import normalize_image
from models.train import train


@pytest.fixture
def release_data(tmp_path):
    rows = []
    for split in ("train", "val", "test"):
        for source in ("real", "sd14", "midjourney", "glide"):
            label = int(source != "real")
            image = Image.new("RGB", (300, 280), (20 + label * 200, len(rows) * 10, 60))
            image_path = tmp_path / f"{len(rows)}.jpg"
            image_path.write_bytes(normalize_image(image).jpeg)
            rows.append(
                {
                    "filepath": str(image_path),
                    "label": str(label),
                    "source": f"genimage_{source}",
                    "split": split,
                    "raw_path": f"raw/{len(rows)}.png",
                    "norm_version": "1",
                }
            )
    labels = tmp_path / "labels.csv"
    write_labels(labels, rows)

    def encode(images, **kwargs):
        values = np.zeros((len(images), 512), dtype=np.float32)
        values[:, 0] = [np.asarray(image)[:, :, 0].mean() / 255 for image in images]
        values[:, 1] = 1
        return values / np.linalg.norm(values, axis=1, keepdims=True)

    directory = tmp_path / "features"
    extract_features(labels, directory, encoder=Mock(encode=encode))
    return labels, directory


def write_labels(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize("raw_path", ["", None, "raw/0.png", "raw/sub/../0.png"])
def test_labels_reject_missing_or_aliased_raw_identity(release_data, raw_path):
    labels, _ = release_data
    rows = read_labels(labels)
    rows[4]["raw_path"] = raw_path
    write_labels(labels, rows)
    with pytest.raises(ValueError, match="raw_path"):
        read_labels(labels)


@pytest.mark.parametrize("change", ["float64", "not_unit_length"])
def test_loader_checks_embedding_contract_even_with_matching_checksum(
    release_data, change
):
    labels, directory = release_data
    values = np.load(directory / "features.npy")
    values = values.astype(np.float64) if change == "float64" else values * 2
    np.save(directory / "features.npy", values)
    manifest_path = directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["features_sha256"] = sha256_file(directory / "features.npy")
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="feature array"):
        load_features(labels, directory)


@pytest.fixture
def candidate(release_data, tmp_path):
    labels, directory = release_data
    model = tmp_path / "model.joblib"
    train(labels, directory, "genimage", model, binary_threshold=0.5)
    return labels, directory, model


def approve(lock):
    # Test-only signoff for synthetic data; never copied to a real protocol.
    protocol = json.loads(lock.read_text())
    protocol["status"] = "approved"
    protocol["approved_by"] = ["synthetic-test-reviewer"]
    protocol["evidence"] = {key: "synthetic fixture" for key in protocol["evidence"]}
    lock.write_text(json.dumps(protocol))


def test_evaluation_uses_frozen_probe_once_and_matches_saved_predictions(
    candidate, tmp_path, monkeypatch
):
    from sklearn.linear_model import LogisticRegression

    from models.evaluate import evaluate, prepare_lock

    labels, features, model = candidate
    lock, output = tmp_path / "protocol.json", tmp_path / "result"
    original_hash = sha256_file(model)
    prepare_lock(labels, features, model, lock)
    approve(lock)
    monkeypatch.setattr(
        LogisticRegression,
        "fit",
        Mock(side_effect=AssertionError("No training during evaluation")),
    )
    original_predict = LogisticRegression.predict_proba
    calls = []

    def predict(self, x):
        calls.append(len(x))
        return original_predict(self, x)

    monkeypatch.setattr(LogisticRegression, "predict_proba", predict)
    report = evaluate(labels, features, model, lock, output)
    assert calls == [4]
    assert sha256_file(model) == original_hash
    predictions = list(csv.DictReader((output / "predictions.csv").open()))
    assert report["test"]["n"] == len(predictions) == 4
    correct = sum(int(row["label"]) == int(row["prediction"]) for row in predictions)
    assert report["test"]["accuracy"] == correct / 4
    assert report["quality"]["status"] == ("pass" if correct / 4 >= 0.9 else "fail")
    assert report["predictions_sha256"] == sha256_file(output / "predictions.csv")
    assert len(report["profile"]["hash"]) == 64
    assert len(report["by_source"]) == 4
    assert all(group["auroc"] is None for group in report["by_source"])
    assert sum(sum(row) for row in report["test"]["confusion_matrix"]) == 4
    with pytest.raises(FileExistsError):
        evaluate(labels, features, model, lock, tmp_path / "second-result")
    assert calls == [4]


@pytest.mark.parametrize(
    "fault", ["proposed", "missing_evidence", "threshold", "model_hash", "labels_hash"]
)
def test_lock_rejects_unapproved_or_changed_inputs_before_prediction(
    candidate, tmp_path, monkeypatch, fault
):
    from sklearn.linear_model import LogisticRegression

    from models.evaluate import evaluate, prepare_lock

    labels, features, model = candidate
    lock = tmp_path / "protocol.json"
    prepare_lock(labels, features, model, lock)
    if fault != "proposed":
        approve(lock)
    protocol = json.loads(lock.read_text())
    if fault == "missing_evidence":
        protocol["evidence"]["data_qa"] = ""
    elif fault == "threshold":
        protocol["thresholds"]["binary"] = 0.6
    elif fault.endswith("_hash"):
        protocol["artifacts"][fault.removesuffix("_hash") + "_sha256"] = "0" * 64
    lock.write_text(json.dumps(protocol))
    predict = Mock(side_effect=AssertionError("Must reject before prediction"))
    monkeypatch.setattr(LogisticRegression, "predict_proba", predict)
    with pytest.raises(ValueError):
        evaluate(labels, features, model, lock, tmp_path / "result")
    predict.assert_not_called()
    assert not (tmp_path / "result").exists()


def test_model_trained_on_other_manifest_is_rejected(candidate, tmp_path):
    from models.evaluate import prepare_lock

    labels, features, model = candidate
    bundle = joblib.load(model)
    bundle["metadata"]["labels_sha256"] = "0" * 64
    joblib.dump(bundle, model)
    model.with_suffix(".joblib.sha256").write_text(sha256_file(model))
    with pytest.raises(ValueError, match="labels_sha256"):
        prepare_lock(labels, features, model, tmp_path / "lock.json")


def test_genimage_training_cannot_open_final_test(candidate, tmp_path):
    labels, features, _ = candidate
    with pytest.raises(ValueError, match="models.evaluate"):
        train(
            labels,
            features,
            "genimage",
            tmp_path / "bad.joblib",
            binary_threshold=0.5,
            evaluate_test=True,
        )
    assert not (tmp_path / "bad.joblib").exists()


def test_failed_inference_keeps_attempt_record(candidate, tmp_path, monkeypatch):
    from sklearn.linear_model import LogisticRegression

    from models.evaluate import evaluate, prepare_lock

    labels, features, model = candidate
    lock = tmp_path / "lock.json"
    prepare_lock(labels, features, model, lock)
    approve(lock)
    predict = Mock(side_effect=RuntimeError("simulated inference failure"))
    monkeypatch.setattr(LogisticRegression, "predict_proba", predict)
    with pytest.raises(RuntimeError, match="simulated"):
        evaluate(labels, features, model, lock, tmp_path / "first")
    assert lock.with_suffix(".json.used.json").exists()
    assert not (tmp_path / "first/evaluation.json").exists()
    with pytest.raises(FileExistsError):
        evaluate(labels, features, model, lock, tmp_path / "retry")
    predict.assert_called_once()


@pytest.mark.parametrize("probabilities", [[float("nan"), 0.8], [-0.1, 1.1], [0.5]])
def test_metrics_reject_invalid_predictions(probabilities):
    from models.train import metrics

    with pytest.raises(ValueError):
        metrics(np.array([0, 1]), np.array(probabilities), 0.5)


def test_metrics_use_locked_uncertainty_thresholds_and_keep_all_samples():
    from models.train import metrics

    result = metrics(
        np.array([0, 1, 0, 1]), np.array([0.2, 0.8, 0.6, 0.9]), 0.5, 0.2, 0.8
    )
    assert result["uncertain_n"] == 3 and result["decided_n"] == 1
    assert result["accuracy"] == 0.75
    assert result["decided_accuracy"] == 1.0 and result["decided_coverage"] == 0.25


def test_cli_prepare_lock_does_not_predict_or_overwrite(
    candidate, tmp_path, monkeypatch, capsys
):
    import sys

    from sklearn.linear_model import LogisticRegression

    from models.evaluate import main

    labels, features, model = candidate
    lock = tmp_path / "proposed.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "models.evaluate",
            "--labels",
            str(labels),
            "--features",
            str(features),
            "--model",
            str(model),
            "--prepare-lock",
            str(lock),
        ],
    )
    predict = Mock(side_effect=AssertionError("Do not open test during preparation"))
    monkeypatch.setattr(LogisticRegression, "predict_proba", predict)
    main()
    assert "test was not evaluated" in capsys.readouterr().out
    assert json.loads(lock.read_text())["status"] == "proposed"
    predict.assert_not_called()
    with pytest.raises(FileExistsError):
        main()


def test_cli_quality_failure_keeps_honest_report(candidate, tmp_path, monkeypatch):
    import sys

    from models.evaluate import main, prepare_lock

    labels, features, model = candidate
    bundle = joblib.load(model)
    bundle["probe"].coef_[:] = 0
    bundle["probe"].intercept_[:] = 0
    joblib.dump(bundle, model)
    model.with_suffix(".joblib.sha256").write_text(sha256_file(model))
    lock, output = tmp_path / "lock.json", tmp_path / "result"
    prepare_lock(labels, features, model, lock)
    approve(lock)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "models.evaluate",
            "--labels",
            str(labels),
            "--features",
            str(features),
            "--model",
            str(model),
            "--lock",
            str(lock),
            "--output-dir",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 1
    report = json.loads((output / "evaluation.json").read_text())
    assert report["test"]["accuracy"] == 0.75
    assert report["test"]["uncertain_n"] == 4
    assert report["test"]["decided_accuracy"] is None
    assert report["quality"]["status"] == "fail"


def test_extract_does_not_publish_cache_if_labels_change_mid_run(
    release_data, tmp_path
):
    labels, _ = release_data
    output = tmp_path / "new-features"

    def encode(images, **kwargs):
        with labels.open("a") as stream:
            stream.write("\n")
        values = np.zeros((len(images), 512), dtype=np.float32)
        values[:, 0] = 1
        return values

    with pytest.raises(ValueError, match="Labels changed"):
        extract_features(labels, output, encoder=Mock(encode=encode))
    assert not output.exists()
