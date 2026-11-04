"""ML contracts run offline; no torch or model downloads required in CI."""

import csv
import hashlib
import importlib
import json
from io import BytesIO
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image, ImageOps

from models.clip_input import FEATURE_DIM, feature_contract
from models.extract_features import extract_features, load_features
from models.normalize import NORMALIZATION_VERSION, ImageTooSmall, normalize_image


class FakeEncoder:
    def __init__(self):
        self.inputs = []

    def encode(self, images, **kwargs):
        assert kwargs["normalize_embeddings"] is True
        self.inputs.extend(np.asarray(im).copy() for im in images)
        features = np.zeros((len(images), FEATURE_DIM), dtype=np.float32)
        for index, im in enumerate(images):
            features[index, 0] = np.asarray(im).mean() / 255
            features[index, 1] = 1
        return features / np.linalg.norm(features, axis=1, keepdims=True)


@pytest.fixture
def dataset(tmp_path):
    rows = []
    for split in ("train", "val", "test"):
        for label in (0, 1):
            for n in range(3):
                raw = Image.new(
                    "RGB", (300, 280), (25 + 160 * label + n * 5, len(rows), 60)
                )
                path = tmp_path / f"{split}-{label}-{n}.jpg"
                path.write_bytes(normalize_image(raw).jpeg)
                rows.append(
                    {
                        "filepath": str(path),
                        "label": str(label),
                        "source": "genimage_real" if label == 0 else "genimage_sd14",
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
    feature_dir = tmp_path / "features"
    extract_features(labels, feature_dir, batch_size=5, encoder=FakeEncoder())
    return labels, feature_dir


def test_normalize_matches_legacy_bytes_and_decoded_pixels():
    image = Image.effect_noise((400, 300), 70).convert("RGB")
    image.getexif()[274] = 6
    old = ImageOps.fit(
        ImageOps.exif_transpose(image).convert("RGB"),
        (256, 256),
        Image.Resampling.BICUBIC,
    )
    stream = BytesIO()
    old.save(stream, "JPEG", quality=95)
    normalized = normalize_image(image)
    assert normalized.jpeg == stream.getvalue() == normalize_image(image).jpeg
    with Image.open(BytesIO(normalized.jpeg)) as decoded:
        np.testing.assert_array_equal(normalized.image, decoded)
    assert normalized.image.size == (256, 256)
    assert not normalized.image.getexif()
    assert image.size == (400, 300) and image.getexif()[274] == 6


@pytest.mark.parametrize("size", [(255, 500), (500, 255), (32, 32)])
def test_small_image_rejected(size):
    with pytest.raises(ImageTooSmall) as error:
        normalize_image(Image.new("RGB", size))
    assert (error.value.width, error.value.height) == size


def test_cifake_exception_and_phone_image():
    assert normalize_image(Image.new("RGB", (32, 32)), resize=False).image.size == (
        32,
        32,
    )
    assert normalize_image(Image.new("RGB", (4000, 3000))).image.size == (256, 256)
    assert normalize_image(Image.new("RGB", (256, 256))).image.size == (256, 256)


@pytest.mark.parametrize(
    "field,value",
    [
        ("norm_version", "old"),
        ("labels_norm_version", "old"),
        ("rows", 1),
        ("clip_model_id", "openai/clip-vit-base-patch32"),
        ("clip_revision", "old"),
        ("normalize_embeddings", False),
        ("features_sha256", "wrong"),
    ],
)
def test_stale_feature_cache_is_rejected(dataset, field, value):
    labels, directory = dataset
    path = directory / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match=field):
        load_features(labels, directory)


def test_labels_reordered_and_images_changed_are_rejected(dataset):
    labels, directory = dataset
    original = labels.read_text()
    lines = original.splitlines()
    labels.write_text("\n".join([lines[0], *reversed(lines[1:])]) + "\n")
    with pytest.raises(ValueError):
        load_features(labels, directory)
    labels.write_text(original)
    rows = list(csv.DictReader(lines))
    Image.new("RGB", (256, 256), "red").save(rows[0]["filepath"], "JPEG")
    with pytest.raises(ValueError):
        load_features(labels, directory)


def test_score_normalizes_once_and_matches_training_input(monkeypatch):
    module = importlib.import_module("models.score")
    encoder = FakeEncoder()
    probe = Mock(classes_=np.array([1, 0]), n_features_in_=512)
    probe.predict_proba.return_value = np.array([[0.8, 0.2]])
    scorer = module.Scorer(probe, encoder)
    raw = Image.new("RGB", (400, 300), "orange")
    normalized = normalize_image(raw)
    with Image.open(BytesIO(normalized.jpeg)) as processed:
        encoder.encode([processed], normalize_embeddings=True)
    spy = Mock(wraps=normalize_image)
    monkeypatch.setattr(module, "normalize_image", spy)
    assert scorer(raw) == 0.8  # AI column follows classes_, not a hardcoded index.
    spy.assert_called_once_with(raw)
    np.testing.assert_array_equal(encoder.inputs[0], encoder.inputs[1])
    with pytest.raises(ImageTooSmall):
        scorer(Image.new("RGB", (32, 32)))


@pytest.mark.parametrize("probability", [float("nan"), float("inf"), -0.1, 1.1])
def test_score_rejects_invalid_probability(probability):
    from models.score import Scorer

    probe = Mock(classes_=np.array([0, 1]), n_features_in_=512)
    probe.predict_proba.return_value = np.array([[1 - probability, probability]])
    with pytest.raises(ValueError):
        Scorer(probe, FakeEncoder())(Image.new("RGB", (256, 256)))


def test_train_fit_uses_only_train_and_evaluation_keeps_uncertain(
    dataset, tmp_path, monkeypatch
):
    from sklearn.linear_model import LogisticRegression

    from models.train import metrics, train

    labels, directory = dataset
    x, rows, _ = load_features(labels, directory)
    expected_train = x[[row["split"] == "train" for row in rows]]
    original_fit = LogisticRegression.fit
    calls = []

    def checked_fit(self, features, targets):
        np.testing.assert_array_equal(features, expected_train)
        calls.append(len(targets))
        return original_fit(self, features, targets)

    monkeypatch.setattr(LogisticRegression, "fit", checked_fit)
    report = train(
        labels, directory, "genimage", tmp_path / "probe.joblib", binary_threshold=0.5
    )
    assert report["split_counts"] == {"train": 6, "val": 6, "test": 6}
    assert report["test"] is None  # Default does not inspect the final test scores.
    assert calls == [6] * 5
    result = metrics(np.array([0, 1, 0, 1]), np.array([0.3, 0.7, 0.1, 0.9]), 0.5)
    assert result["n"] == 4 and result["uncertain_n"] == 2
    assert sum(map(sum, result["confusion_matrix"])) == 4


@pytest.mark.parametrize(
    "key,value",
    [
        ("clip_model_id", "wrong-model"),
        ("clip_revision", "wrong-revision"),
        ("norm_version", "old"),
        ("dataset", "cifake"),
        ("feature_dim", 768),
    ],
)
def test_wrong_model_bundle_rejected_before_loading_clip(
    dataset, tmp_path, monkeypatch, key, value
):
    import joblib

    from models.train import train

    module = importlib.import_module("models.score")
    labels, directory = dataset
    path = tmp_path / "probe.joblib"
    train(labels, directory, "genimage", path, binary_threshold=0.5)
    bundle = joblib.load(path)
    assert bundle["metadata"]["clip_model_id"] == feature_contract()["clip_model_id"]
    bundle["metadata"][key] = value
    joblib.dump(bundle, path)
    path.with_suffix(".joblib.sha256").write_text(
        hashlib.sha256(path.read_bytes()).hexdigest()
    )
    loader = Mock(side_effect=AssertionError("Must reject before CLIP loads"))
    monkeypatch.setattr(module, "load_encoder", loader)
    with pytest.raises(ValueError):
        module.load_scorer(path)
    loader.assert_not_called()


def test_score_requires_startup_and_failed_reload_clears_old_model(monkeypatch):
    module = importlib.import_module("models.score")
    monkeypatch.setattr(module, "_default_scorer", None)
    with pytest.raises(RuntimeError, match="not initialized"):
        module.score(Image.new("RGB", (256, 256)))
    monkeypatch.setattr(module, "_default_scorer", Mock(return_value=0.9))
    monkeypatch.setattr(
        module, "load_scorer", Mock(side_effect=ValueError("wrong model"))
    )
    with pytest.raises(ValueError):
        module.load_model()
    with pytest.raises(RuntimeError):
        module.score(Image.new("RGB", (256, 256)))


def test_normalization_version_has_pinned_jpeg_fingerprint():
    pixels = np.arange(300 * 400 * 3, dtype=np.uint32).reshape(300, 400, 3) % 256
    jpeg = normalize_image(Image.fromarray(pixels.astype("uint8"))).jpeg
    assert NORMALIZATION_VERSION == "1"
    assert (
        hashlib.sha256(jpeg).hexdigest()
        == "6ce00bca2f8fe3e7bb338f93c81a8236715e2a70f4d6dfadfb4eb5c3c9ddcb23"
    )
