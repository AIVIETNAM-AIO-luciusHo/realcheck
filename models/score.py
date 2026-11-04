"""Backend contract: original decoded PIL image -> finite P(AI), no HTTP logic."""

import argparse
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from models.clip_input import FEATURE_DIM, encode_images, feature_contract, load_encoder
from models.normalize import NORMALIZATION_VERSION, normalize_image

DEFAULT_MODEL_PATH = Path(__file__).with_name("clip_probe.joblib")
_default_scorer = None


class Scorer:
    """A loaded probe and frozen encoder, owned by one inference worker."""

    def __init__(self, probe: Any, encoder: Any) -> None:
        classes = np.asarray(probe.classes_)
        if classes.shape != (2,) or set(classes.tolist()) != {0, 1}:
            raise ValueError("Probe classes must be real=0 and AI=1")
        if probe.n_features_in_ != FEATURE_DIM:
            raise ValueError("Probe must expect 512 features")
        self.probe, self.encoder = probe, encoder
        self.ai_column = int(np.flatnonzero(classes == 1)[0])

    def __call__(self, image: Image.Image) -> float:
        """Normalize once; propagate ImageTooSmall and all inference failures."""
        normalized = normalize_image(image)
        features = encode_images([normalized.image], self.encoder)
        probabilities = np.asarray(self.probe.predict_proba(features))
        if probabilities.shape != (1, 2) or not np.isfinite(probabilities).all():
            raise ValueError("Probe returned invalid probabilities")
        if (probabilities < 0).any() or (probabilities > 1).any():
            raise ValueError("Probe probabilities must be in [0, 1]")
        if not np.isclose(probabilities.sum(), 1):
            raise ValueError("Probe probabilities must sum to 1")
        return float(probabilities[0, self.ai_column])


def load_scorer(path: Path = DEFAULT_MODEL_PATH, device: str = "cpu") -> Scorer:
    """Load a trusted local joblib at startup; reject incompatible bundles.

    Never call with a user-uploaded artifact: joblib deserialization executes code.
    """
    import joblib

    from models.extract_features import sha256_file

    path = Path(path)
    expected_hash = path.with_suffix(path.suffix + ".sha256").read_text().strip()
    if sha256_file(path) != expected_hash:
        raise ValueError("Model checksum mismatch")
    bundle = joblib.load(path)
    if not isinstance(bundle, dict) or not isinstance(bundle.get("metadata"), dict):
        raise TypeError("Legacy model lacks metadata; retrain with models.train")
    metadata = bundle["metadata"]
    expected = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "dataset": "genimage",
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"Incompatible model: {key}; retrain before serving")
    # Validate the probe before downloading/loading the heavier encoder.
    scorer = Scorer(bundle["probe"], None)
    scorer.encoder = load_encoder(device)
    scorer(Image.new("RGB", (256, 256)))
    return scorer


def load_model(path: Path = DEFAULT_MODEL_PATH, device: str = "cpu") -> Scorer:
    """Initialize the module-level score function during backend startup."""
    global _default_scorer
    _default_scorer = None
    _default_scorer = load_scorer(path, device)
    return _default_scorer


def score(image: Image.Image) -> float:
    """Score an original PIL image after load_model(); never download on request."""
    if _default_scorer is None:
        raise RuntimeError("Model not initialized; call load_model() during startup")
    return _default_scorer(image)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Original image, not processed JPEG")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    scorer = load_scorer(args.model)
    with Image.open(args.image) as image:
        image.load()
        print(f"AI score: {scorer(image):.8f}")


if __name__ == "__main__":
    main()
