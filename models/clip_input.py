"""One frozen CLIP encoder and preprocessing path for extraction and serving."""

from typing import Any

import numpy as np
from PIL import Image
from PIL import __version__ as PILLOW_VERSION

CLIP_MODEL_ID = "sentence-transformers/clip-ViT-B-32"
CLIP_REVISION = "327ab6726d33c0e22f920c83f2ff9e4bd38ca37f"
FEATURE_DIM = 512


def feature_contract() -> dict:
    """Identity of the feature space; persisted in features and probe bundles."""
    return {
        "clip_model_id": CLIP_MODEL_ID,
        "clip_revision": CLIP_REVISION,
        "feature_dim": FEATURE_DIM,
        "normalize_embeddings": True,
        "pillow_version": PILLOW_VERSION,
    }


def load_encoder(device: str = "cpu") -> Any:
    """Load the pinned SentenceTransformer once, outside request handling."""
    import torch
    from sentence_transformers import SentenceTransformer

    if device == "cpu":
        torch.set_num_threads(4)
    encoder = SentenceTransformer(
        CLIP_MODEL_ID, revision=CLIP_REVISION, device=device, trust_remote_code=False
    )
    encoder.eval()
    encoder.requires_grad_(False)
    return encoder


def encode_images(images: list[Image.Image], encoder: Any) -> np.ndarray:
    """Encode decoded, already normalized images; no JPEG encode here.

    SentenceTransformer owns CLIP's 224px preprocessing in both paths.
    Returns finite, L2-normalized float32 vectors in the original row order.
    """
    if not images:
        raise ValueError("Cannot encode an empty image batch")
    features = np.asarray(
        encoder.encode(
            images,
            batch_size=len(images),
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        ),
        dtype=np.float32,
    )
    if features.shape != (len(images), FEATURE_DIM) or not np.isfinite(features).all():
        raise ValueError("CLIP must return finite (N, 512) image embeddings")
    if not np.allclose(np.linalg.norm(features, axis=1), 1.0, atol=1e-5):
        raise ValueError("CLIP embeddings must be L2-normalized")
    return features
