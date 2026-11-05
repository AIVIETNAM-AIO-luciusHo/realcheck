"""T007: score() chuan hoa dung mot lan; dau vao CLIP giong duong huan luyen."""

import inspect
from io import BytesIO
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

import models.score as score_module
from models.clip_input import FEATURE_DIM, encode_images
from models.normalize import ImageTooSmall, normalize_image


class RecordingEncoder:
    def __init__(self):
        self.inputs = []

    def encode(self, images, **kwargs):
        self.inputs.extend(np.asarray(im).copy() for im in images)
        vectors = np.ones((len(images), FEATURE_DIM), dtype=np.float32)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _scorer(encoder):
    probe = Mock(classes_=np.array([0, 1]), n_features_in_=FEATURE_DIM)
    probe.predict_proba.return_value = np.array([[0.25, 0.75]])
    return score_module.Scorer(probe, encoder)


def _raw():
    return Image.effect_noise((640, 480), 60).convert("RGB")


def test_score_calls_normalize_exactly_once_with_default_resize(monkeypatch):
    spy = Mock(wraps=normalize_image)
    monkeypatch.setattr(score_module, "normalize_image", spy)
    raw = _raw()
    assert _scorer(RecordingEncoder())(raw) == 0.75
    assert spy.call_count == 1
    assert spy.call_args.args == (raw,) and spy.call_args.kwargs == {}


def test_score_has_no_resize_parameter():
    for function in (score_module.score, score_module.Scorer.__call__):
        assert "resize" not in inspect.signature(function).parameters
    with pytest.raises(TypeError):
        _scorer(RecordingEncoder())(_raw(), resize=False)


def test_clip_input_is_identical_for_disk_path_and_api_path(tmp_path):
    raw = _raw()
    # Training path: normalized jpeg written to disk, read back, encoded.
    path = tmp_path / "processed.jpg"
    path.write_bytes(normalize_image(raw).jpeg)
    training = RecordingEncoder()
    with Image.open(path) as image:
        encode_images([image.copy()], training)
    api = RecordingEncoder()
    _scorer(api)(raw)
    assert len(api.inputs) == len(training.inputs) == 1
    np.testing.assert_array_equal(api.inputs[0], training.inputs[0])


def test_module_score_delegates_to_the_loaded_scorer(monkeypatch):
    monkeypatch.setattr(score_module, "_default_scorer", _scorer(RecordingEncoder()))
    assert score_module.score(_raw()) == 0.75


def test_too_small_image_propagates_and_never_reaches_encoder():
    encoder = RecordingEncoder()
    with pytest.raises(ImageTooSmall):
        _scorer(encoder)(Image.new("RGB", (200, 200)))
    assert encoder.inputs == []


def test_normalized_input_is_not_the_pre_jpeg_image():
    raw = _raw()
    encoder = RecordingEncoder()
    _scorer(encoder)(raw)
    with Image.open(BytesIO(normalize_image(raw).jpeg)) as decoded:
        np.testing.assert_array_equal(encoder.inputs[0], np.asarray(decoded))
