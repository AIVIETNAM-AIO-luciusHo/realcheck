"""Công thức báo cáo và các chốt chặn của scripts.evaluate, không cần CLIP thật."""

import csv
import json

import joblib
import numpy as np
import pytest
from PIL import Image

from models.clip_input import FEATURE_DIM
from models.extract_features import extract_features, load_features, sha256_file
from models.normalize import NORMALIZATION_VERSION, normalize_image
from models.train import metrics, train
from scripts import evaluate as ev


class Encoder:
    """Đặc trưng đơn giản theo độ sáng, đủ để tách hai lớp trong dữ liệu mẫu."""

    def encode(self, images, **kwargs):
        features = np.zeros((len(images), FEATURE_DIM), dtype=np.float32)
        for index, image in enumerate(images):
            features[index, 0] = np.asarray(image).mean() / 255
            features[index, 1] = 1
        return features / np.linalg.norm(features, axis=1, keepdims=True)


@pytest.fixture
def locked(tmp_path):
    """Dữ liệu mẫu 2 nguồn ở cả 3 split, cùng model đã train từ đặc trưng đó."""
    rows = []
    for split in ("train", "val", "test"):
        for label, source in ((0, "genimage_real"), (1, "genimage_sd14")):
            for n in range(3):
                color = (25 + 160 * label + n * 5, len(rows), 60)
                path = tmp_path / f"{split}-{label}-{n}.jpg"
                path.write_bytes(
                    normalize_image(Image.new("RGB", (300, 280), color)).jpeg
                )
                rows.append(
                    {
                        "filepath": str(path),
                        "label": str(label),
                        "source": source,
                        "split": split,
                        "raw_path": f"raw-{len(rows)}.png",
                        "norm_version": NORMALIZATION_VERSION,
                    }
                )
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    features = tmp_path / "features"
    extract_features(labels, features, batch_size=5, encoder=Encoder())
    model = tmp_path / "probe.joblib"
    trained = train(
        labels, features, "genimage", model, binary_threshold=0.5, evaluate_test=True
    )
    return labels, features, model, trained


def rewrite_bundle(model, change):
    bundle = joblib.load(model)
    change(bundle)
    joblib.dump(bundle, model)
    model.with_suffix(model.suffix + ".sha256").write_text(
        sha256_file(model) + "\n", encoding="ascii"
    )


def test_metrics_counts_all_images_and_reports_uncertain_separately():
    y = np.array([0, 0, 0, 1, 1, 1])
    scores = np.array([0.1, 0.4, 0.8, 0.2, 0.6, 0.9])
    result = metrics(y, scores, 0.5)
    assert result["n"] == 6
    assert result["confusion_matrix"] == [[2, 1], [1, 2]]
    assert result["accuracy"] == pytest.approx(4 / 6)
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)
    # 0.4 và 0.6 thuộc Chưa chắc nhưng vẫn được tính trong accuracy toàn bộ
    assert result["uncertain_n"] == 2 and result["decided_n"] == 4
    # Còn 0.1, 0.8, 0.2, 0.9: đúng 0.1 và 0.9
    assert result["decided_accuracy"] == pytest.approx(2 / 4)


def test_metrics_boundaries_belong_to_uncertain():
    result = metrics(np.array([0, 0, 1, 1]), np.array([0.3, 0.299, 0.7, 0.701]), 0.5)
    assert result["uncertain_n"] == 2


def test_metrics_zero_denominators_are_zero_with_counts():
    result = metrics(np.array([0, 0]), np.array([0.1, 0.2]), 0.5)
    assert result["precision"] == 0 and result["recall"] == 0
    assert result["confusion_matrix"] == [[2, 0], [0, 0]]
    assert result["auroc"] is None


def test_metrics_all_uncertain_has_no_decided_accuracy():
    result = metrics(np.array([0, 1]), np.array([0.4, 0.6]), 0.5)
    assert result["uncertain_rate"] == 1 and result["decided_accuracy"] is None


def test_evaluate_test_matches_training_report_and_page_fields(locked):
    labels, features, model, trained = locked
    report = ev.evaluate(labels, features, model, "test")
    assert report["test"] == trained["test"]
    assert report["by_source"] == trained["by_source"]
    assert report["model"] == trained["model"]
    assert report["profile"] == trained["profile"]
    assert report["dataset"] == trained["dataset"]
    assert report["thresholds"] == {"binary": 0.5, "low": 0.3, "high": 0.7}
    assert report["accuracy_target"]["value"] == 0.90
    names = [group["name"] for group in report["by_source"]]
    assert names == ["genimage_real", "genimage_sd14"]
    assert sum(group["n"] for group in report["by_source"]) == report["test"]["n"]


def test_evaluate_val_never_reports_test(locked):
    labels, features, model, trained = locked
    report = ev.evaluate(labels, features, model, "val")
    assert report["val"] == trained["val"]
    assert report["test"] is None and report["by_source"] == []
    assert "accuracy_target" not in report


def test_evaluate_uses_only_requested_split(locked, monkeypatch):
    labels, features, model, _ = locked
    x, rows, _ = load_features(labels, features)
    expected = x[[row["split"] == "val" for row in rows]]
    real_probe = joblib.load(model)["probe"]
    seen = []

    class Probe:
        classes_ = real_probe.classes_
        n_features_in_ = real_probe.n_features_in_

        def predict_proba(self, data):
            seen.append(data)
            return real_probe.predict_proba(data)

    real_load = ev.joblib.load
    monkeypatch.setattr(
        ev.joblib, "load", lambda path: {**real_load(path), "probe": Probe()}
    )
    ev.evaluate(labels, features, model, "val")
    assert len(seen) == 1
    np.testing.assert_array_equal(seen[0], expected)


def test_evaluate_rejects_changed_model_file(locked):
    labels, features, model, _ = locked
    model.write_bytes(model.read_bytes() + b"x")
    with pytest.raises(ValueError, match="checksum"):
        ev.evaluate(labels, features, model, "test")


@pytest.mark.parametrize("key", ["features_sha256", "labels_sha256", "norm_version"])
def test_evaluate_rejects_model_trained_on_other_data(locked, key):
    labels, features, model, _ = locked
    rewrite_bundle(model, lambda bundle: bundle["metadata"].update({key: "other"}))
    with pytest.raises(ValueError, match=key):
        ev.evaluate(labels, features, model, "test")


def test_evaluate_rejects_thresholds_metrics_cannot_apply(locked):
    labels, features, model, _ = locked
    rewrite_bundle(model, lambda bundle: bundle["thresholds"].update({"low": 0.4}))
    with pytest.raises(ValueError, match="thresholds"):
        ev.evaluate(labels, features, model, "test")


def test_accuracy_below_target_is_recorded_not_hidden(locked, monkeypatch):
    labels, features, model, _ = locked
    monkeypatch.setattr(ev, "ACCURACY_TARGET", 1.01)
    report = ev.evaluate(labels, features, model, "test")
    assert report["accuracy_target"] == {"value": 1.01, "passed": False}


def test_cli_requires_split(locked, tmp_path):
    with pytest.raises(SystemExit):
        ev.main(["--output", str(tmp_path / "report.json")])


def test_cli_writes_strict_json_and_refuses_overwrite(locked, tmp_path):
    labels, features, model, _ = locked
    output = tmp_path / "out" / "evaluation.json"
    args = ["--split", "val", "--output", str(output)]
    args += ["--labels", str(labels), "--features", str(features)]
    args += ["--model", str(model)]
    ev.main(args)
    written = output.read_bytes()
    report = json.loads(written)
    assert report["split"] == "val" and "scripts.evaluate" in report["run"]["command"]
    with pytest.raises(SystemExit):
        ev.main(args)
    assert output.read_bytes() == written
