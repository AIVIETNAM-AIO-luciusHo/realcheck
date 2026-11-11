"""Expansion policy checks use synthetic data and never read real test labels."""

import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from scripts.download_expansion import materialize, payload_bytes
from scripts.train_expansion import (
    HashTree,
    assign_splits,
    categories,
    compare,
    embeddings,
    metadata_eligible,
    model_key,
)


def test_hash_tree_matches_brute_force():
    rng = np.random.default_rng(42)
    values = [int(v) for v in rng.integers(0, 2**63, size=50)]
    tree = HashTree()
    assert not tree.near(0)
    for value in values:
        tree.add(value)
    for query in [*values, *[v ^ 15 for v in values], 0, 2**63 - 1]:
        assert tree.near(query) == any((query ^ v).bit_count() <= 4 for v in values)


def test_split_keeps_tiny_train_and_holds_out_five_entire_devices():
    rows = [{"uid": f"tiny-{i}", "stratum": "tiny/real"} for i in range(4)]
    rows += [
        {
            "uid": f"D{d:02}-{i}",
            "stratum": "community/vision",
            "image_name": f"D{d:02}_I_nat_{i}.jpg",
        }
        for d in range(1, 36)
        for i in range(3)
    ]
    rows += [
        {"uid": f"open-{i}", "stratum": "openfake/ai", "selection_group": "openfake/ai"}
        for i in range(100)
    ]
    devices = assign_splits(rows)
    assert len(devices) == 5
    assert all(r["split"] == "train" for r in rows if r["stratum"].startswith("tiny/"))
    for row in rows:
        if row["stratum"] == "community/vision":
            assert (row["split"] == "val") == (row["image_name"][:3] in devices)
    assert sum(r["split"] == "val" for r in rows if r["stratum"] == "openfake/ai") == 15
    with pytest.raises(ValueError, match="device identity"):
        assign_splits([{"uid": "missing", "stratum": "community/vision"}])


@pytest.mark.parametrize(
    "extra",
    [
        {"type": "video"},
        {"model": "animagine-xl"},
        {"model": "pony-diffusion"},
        {"nsfw_flag": True},
    ],
)
def test_training_metadata_rejects_video_anime_and_flagged(extra):
    assert not metadata_eligible({"stratum": "openfake/ai", **extra})
    assert metadata_eligible(
        {"stratum": "openfake/ai", "model": "flux-realism", "type": "image"}
    )


def test_portrait_landscape_and_diffusion_pools_remain_explicit():
    row = {
        "stratum": "community/ai",
        "topic": 0,
        "architecture": "StableDiffusion",
        "real_source": "LAION",
    }
    assert categories(row) == ["community/portrait_ai", "community/diffusion_ai"]
    assert categories({**row, "topic": 1}) == [
        "community/landscape_ai",
        "community/diffusion_ai",
    ]
    assert (
        categories({**row, "topic": 3, "architecture": "GAN", "real_source": "ffhq"})
        == []
    )


def test_tool_identity_matches_normalized_names_without_claiming_family_identity():
    assert model_key({"source": "genimage_glide"}) == model_key({"model": "GLIDE"})
    assert model_key({"model_name": "repo/Some-Tool_v2"}) == "sometoolv2"
    assert model_key({"model": "flux-1.1-pro"}) != model_key({"model": "flux.2-dev"})
    assert not metadata_eligible(
        {"stratum": "community/ai", "model_name": "BigGAN-deep"}
    )
    assert not metadata_eligible(
        {"stratum": "community/ai", "model_name": "vq-diffusion"}
    )


def test_materialization_preserves_bytes_and_rejects_changed_output(tmp_path):
    stream = BytesIO()
    Image.new("RGB", (300, 280), "green").save(stream, "PNG")
    data = stream.getvalue()
    assert payload_bytes({"bytes": data}) == data
    assert payload_bytes(base64.b64encode(data).decode()) == data
    row = {
        "repo": "test",
        "revision": "pinned",
        "parquet": "data/a.parquet",
        "row_group": 0,
        "offset": 0,
        "stratum": "community/ai",
    }
    result = materialize(row, data, tmp_path)
    assert Path(result["raw_path"]).read_bytes() == data
    with Image.open(result["filepath"]) as image:
        assert image.size == (256, 256) and image.mode == "RGB"
    Path(result["raw_path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="overwrite"):
        materialize(row, data, tmp_path)


def test_evaluation_calls_each_probe_once_and_reports_cohorts():
    scorer = Mock()
    scorer.predict_features.return_value = np.array([0.1, 0.8])
    rows = [
        {"source": "openfake_real", "label": 0, "cohort": "core_test"},
        {"source": "openfake_ai", "label": 1, "cohort": "reddit_test"},
    ]
    result, predictions = compare({"candidate": scorer}, np.ones((2, 512)), rows)
    scorer.predict_features.assert_called_once()
    assert result["candidate"]["all"]["accuracy"] == 1
    assert result["candidate"]["core_test"]["n"] == 1
    np.testing.assert_array_equal(predictions["candidate"], [0.1, 0.8])


def test_feature_cache_reuses_exact_images_and_rejects_corruption(
    tmp_path, monkeypatch
):
    import scripts.train_expansion as module

    rows = [
        {"uid": "one", "normalized_sha256": "image-sha", "filepath": "never-opened.jpg"}
    ]
    vector = np.zeros((1, 512), dtype=np.float32)
    vector[:, 0] = 1
    monkeypatch.setattr(
        module,
        "load_features",
        lambda *_: (vector, [], {"image_sha256": ["image-sha"]}),
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    encoder = Mock()
    embeddings(rows, cache, encoder, None, None)
    encoder.encode.assert_not_called()
    second = tmp_path / "second"
    second.mkdir()
    monkeypatch.setattr(
        module,
        "load_features",
        lambda *_: (np.empty((0, 512), dtype=np.float32), [], {"image_sha256": []}),
    )
    result = embeddings(rows, second, encoder, None, None, reuse_cache=cache)
    np.testing.assert_array_equal(result, vector)
    encoder.encode.assert_not_called()
    index = json.loads((cache / "pool-feature-index.json").read_text())
    index["contract"]["clip_revision"] = "different"
    (cache / "pool-feature-index.json").write_text(json.dumps(index))
    third = tmp_path / "third"
    third.mkdir()
    with pytest.raises(ValueError, match="Incompatible reused"):
        embeddings(rows, third, encoder, None, None, reuse_cache=cache)


def test_selection_caps_tools_and_separates_test_and_device_groups(
    tmp_path, monkeypatch
):
    import scripts.train_expansion as module

    monkeypatch.setattr(
        module,
        "QUOTAS",
        {
            "tiny/real": 2,
            "community/vision": 35,
            "community/portrait_ai": 20,
            "community/diffusion_ai": 20,
        },
    )
    rng = np.random.default_rng(987)
    rows = []

    def add(stratum, label, **extra):
        index = len(rows)
        rows.append(
            {
                "uid": str(index),
                "stratum": stratum,
                "label": label,
                "upstream_split": "test" if stratum.endswith("_test") else "train",
                "pixel_sha256": str(index),
                "dhash": int(rng.integers(0, 2**63)),
                "model": "heldout" if stratum.endswith("_test") else "training-tool",
                **extra,
            }
        )

    for cohort, n in (("core_test", 520), ("reddit_test", 420)):
        for label in (0, 1):
            for _ in range(n):
                add(cohort, label)
    for dev in range(1, 36):
        add("community/vision", 0, image_name=f"D{dev:02}_I_nat.jpg")
    for shard in ("a.parquet", "b.parquet"):
        add("tiny/real", 0, parquet=shard)
    for model in ("tool-one", "tool-two"):
        for _ in range(20):
            add(
                "community/ai",
                1,
                model=model,
                model_name=model,
                architecture="LatDiff",
                real_source="LAION",
            )
    values = np.zeros((len(rows), 512), dtype=np.float32)
    values[:, 0] = 1
    prompts = np.zeros(
        (len(module.PHOTO + module.ART + module.TOPICS), 512), dtype=np.float32
    )
    prompts[: len(module.PHOTO), 0] = 1
    prompts[len(module.PHOTO) : len(module.PHOTO + module.ART), 0] = -1
    selected = module.select(
        rows, values, prompts, (set(), HashTree(), HashTree()), tmp_path
    )
    summary = json.loads((tmp_path / "selection-summary.json").read_text())
    assert summary["community_max_images_per_tool"] == 10
    assert len(summary["vision_devices"]) == 35
    assert len(summary["vision_validation_devices"]) == 5
    assert sum(r["split"] == "test" for r in selected) == 1880
    assert all(r["split"] == "test" for r in selected if r["upstream_split"] == "test")
    assert {r["parquet"] for r in selected if r["stratum"] == "tiny/real"} == {
        "a.parquet",
        "b.parquet",
    }
