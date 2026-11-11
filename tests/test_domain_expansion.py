"""Expanded sources must reach training without leaking reserved datasets."""

import csv

import numpy as np
import pytest
from PIL import Image

import models.train as train_module
from models.data_sources import SOURCE_LABELS, selected_sources
from models.extract_features import extract_features, read_labels
from models.normalize import NORMALIZATION_VERSION, normalize_image
from models.score import load_bundle
from models.train import metrics, train


def test_binary_misses_are_distinct_from_ai_called_likely_real():
    result = metrics(
        np.array([0, 0, 1, 1, 1, 1]), np.array([0.1, 0.8, 0.2, 0.3, 0.4, 0.8]), 0.5
    )
    assert result["false_negative_rate"] == 0.75
    assert result["likely_real_false_negative_rate"] == 0.25
    assert result["false_positive_rate"] == 0.5
    assert result["uncertain_n"] == 2
    real_only = metrics(np.array([0]), np.array([0.1]), 0.5)
    assert real_only["false_negative_rate"] is None
    assert real_only["likely_real_false_negative_rate"] is None


def test_mixed_selection_includes_new_domains_but_excludes_sd14_and_cifake():
    selected = selected_sources("realcheck_mixed_v2")
    assert {"genimage_adm", "genimage_sd15", "genimage_wukong"} <= selected
    assert {
        "openfake_real",
        "openfake_ai",
        "community_real",
        "community_ai",
    } <= selected
    assert not selected & {"genimage_sd14", "cifake_ai", "cifake_real"}
    assert not selected & {"genimage_vqdm", "genimage_biggan"}
    assert "genimage_sd14" in selected_sources("genimage")
    with pytest.raises(ValueError, match="Unknown dataset"):
        selected_sources("typo")


@pytest.mark.parametrize("source", ["genimage_vqdm", "genimage_biggan"])
def test_unseen_sources_can_be_read_for_audit_but_cannot_enter_fit(
    source, tmp_path, monkeypatch
):
    row = {
        "filepath": str(tmp_path / "image.jpg"),
        "raw_path": str(tmp_path / "raw.png"),
        "source": source,
        "label": "1",
        "split": "train",
        "norm_version": NORMALIZATION_VERSION,
    }
    labels = tmp_path / "labels.csv"
    with labels.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=row)
        writer.writeheader()
        writer.writerow(row)
    assert read_labels(labels)[0]["source"] == source
    monkeypatch.setattr(
        train_module, "load_features", lambda *_: (np.zeros((1, 512)), [row], {})
    )
    with pytest.raises(ValueError, match="Reserved unseen generators"):
        train(
            labels,
            tmp_path / "features",
            "realcheck_mixed_v2",
            tmp_path / "probe.joblib",
            binary_threshold=0.5,
        )


@pytest.mark.parametrize("dataset", ["genimage", "realcheck_mixed_v2"])
def test_non_cifake_training_cannot_open_test(dataset, tmp_path):
    with pytest.raises(ValueError, match="approved lock"):
        train(
            tmp_path / "missing.csv",
            tmp_path / "features",
            dataset,
            tmp_path / "probe.joblib",
            binary_threshold=0.5,
            evaluate_test=True,
        )


@pytest.mark.parametrize(
    "dataset, expected_count", [("realcheck_mixed_v2", 6), ("realcheck_mixed_v3", 7)]
)
def test_mixed_training_uses_all_requested_sources_and_leaves_test_unscored(
    tmp_path, dataset, expected_count
):
    sources = [
        "genimage_real",
        "genimage_adm",
        "openfake_real",
        "openfake_ai",
        "community_real",
        "community_ai",
        "genimage_sd14",
        "cifake_real",
        "cifake_ai",
    ]
    rows = []
    for split in ("train", "val", "test"):
        for source in sources:
            index = len(rows)
            image = Image.new("RGB", (300, 280), (20 + index * 7, 50, 80))
            cifake = source.startswith("cifake_")
            if cifake:
                image = image.resize((32, 32))
            path = tmp_path / f"{index}.jpg"
            path.write_bytes(normalize_image(image, resize=not cifake).jpeg)
            rows.append(
                {
                    "filepath": str(path),
                    "label": str(SOURCE_LABELS[source]),
                    "source": source,
                    "split": split,
                    "raw_path": str(tmp_path / f"raw-{index}.png"),
                    "norm_version": NORMALIZATION_VERSION,
                }
            )
    labels = tmp_path / "labels.csv"
    with labels.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)

    class Encoder:
        def encode(self, images, **_):
            features = np.zeros((len(images), 512), dtype=np.float32)
            for i, image in enumerate(images):
                features[i, 0] = np.asarray(image).mean() / 255
                features[i, 1] = 1
            return features / np.linalg.norm(features, axis=1, keepdims=True)

    features = tmp_path / "features"
    extract_features(labels, features, encoder=Encoder())
    model = tmp_path / "mixed.joblib"
    report = train(labels, features, dataset, model, binary_threshold=0.5)
    assert report["split_counts"] == {
        "train": expected_count,
        "val": expected_count,
        "test": expected_count,
    }
    assert report["test"] is None
    assert {g["name"] for g in report["val_by_source"]} == set(sources[:expected_count])
    assert load_bundle(model)["metadata"]["dataset"] == dataset
