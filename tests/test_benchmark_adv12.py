"""Offline cost contract with synthetic images/probes; no pretrained model or timing claims."""

import json
from argparse import Namespace

import numpy as np
import pytest
from PIL import Image

from scripts import adv12_run
from scripts import benchmark_adv12 as bench


@pytest.fixture
def args(tmp_path):
    rows = []
    for i, split in enumerate(("train", "val", "val", "test")):
        image = tmp_path / f"{i}.jpg"
        Image.new("RGB", (256, 256), (i * 30, 40, 50)).save(image)
        rows.append(f"{image},0,genimage_real,{split},{image},1,g{i}")
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "filepath,label,source,split,raw_path,norm_version,group_id\n"
        + "\n".join(rows),
        encoding="utf-8",
    )
    samples = tmp_path / "ids.json"
    samples.write_text(json.dumps([str(tmp_path / "2.jpg"), str(tmp_path / "1.jpg")]))
    model = tmp_path / "model.joblib"
    model.write_bytes(b"synthetic")
    return Namespace(
        model=model,
        feature_manifest=None,
        labels=labels,
        sample_ids=samples,
        output=tmp_path / "cost.json",
        warmup=3,
        device="cpu",
    )


def test_batch1_warmup_order_memory_and_percentiles(args, monkeypatch):
    ticks = iter(range(12))  # load plus five batch-1 invocations
    monkeypatch.setattr(bench.time, "perf_counter", lambda: next(ticks))
    calls = []
    report = bench.run(
        args, loader=lambda _: lambda image: calls.append(image.size) or 0.25
    )
    assert calls == [(256, 256)] * 5
    assert report["batch_size"] == 1 and report["status"] == "complete"
    assert [r["sample_id"] for r in report["samples"]] == json.loads(
        args.sample_ids.read_text()
    )
    assert report["latency_ms"] == {"p50": 1000, "p95": 1000, "p99": 1000}
    assert report["peak_rss_process_mib"] > 0 and report["rss_before_load_mib"] > 0
    assert report["kind"] == "offline_batch1_not_http_slo"
    assert json.loads(args.output.read_text(encoding="utf-8")) == report


@pytest.mark.parametrize(
    "case", ["train", "test", "duplicate", "empty", "overwrite", "warmup"]
)
def test_refuses_before_loading(args, case):
    ids = json.loads(args.sample_ids.read_text())
    if case in ("train", "test"):
        ids = [str(args.labels.parent / ("0.jpg" if case == "train" else "3.jpg"))]
    if case == "duplicate":
        ids = ids * 2
    if case == "empty":
        ids = []
    if case == "overwrite":
        args.output.write_text("old")
    if case == "warmup":
        args.warmup = -1
    args.sample_ids.write_text(json.dumps(ids))
    with pytest.raises((ValueError, FileExistsError)):
        bench.run(args, loader=lambda _: pytest.fail("must reject before model load"))
    if case == "overwrite":
        assert args.output.read_text() == "old"


@pytest.mark.parametrize("score", [float("nan"), 2.0])
def test_keeps_failed_report(args, score):
    with pytest.raises(ValueError, match="score"):
        bench.run(args, loader=lambda _: lambda image: score)
    saved = json.loads(args.output.read_text())
    assert saved["status"] == "failed" and saved["error_type"] == "ValueError"
    assert "latency_ms" not in saved


def test_changed_input_invalidates_run(args):
    def predict(image):
        with open(image.filename, "ab") as stream:
            stream.write(b"changed")
        return 0.25

    with pytest.raises(ValueError, match="changed"):
        bench.run(args, loader=lambda _: predict)
    assert json.loads(args.output.read_text())["status"] == "failed"


def test_unavailable_cuda_fails_before_loading(args, monkeypatch):
    import sys
    from types import SimpleNamespace

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )
    args.device = "cuda"
    with pytest.raises(ValueError, match="CUDA"):
        bench.load_predictor(args)


@pytest.mark.parametrize("attribute", ["labels", "sample_ids", "model"])
def test_changed_artifact_invalidates_run(args, attribute):
    def predict(image):
        with getattr(args, attribute).open("ab") as stream:
            stream.write(b"changed")
        return 0.25

    with pytest.raises(ValueError, match="Artifact changed"):
        bench.run(args, loader=lambda _: predict)
    assert json.loads(args.output.read_text())["status"] == "failed"


def test_real_synthetic_candidate_and_manifest_pairing(args, tmp_path, monkeypatch):
    # An actual sklearn fit, with a four-dimensional synthetic encoder.
    rows = adv12_run.read_rows(args.labels)
    rows[0]["label"] = "1"
    features = np.array(
        [[1, 0, 0, 0], [0, 1, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0]], dtype=np.float32
    )
    # Both classes in train are needed; keep validation/test rows for the benchmark fixture.
    data = {
        "features": np.vstack([features, [0, 0, 0, 1]]),
        "ids": np.array([r["filepath"] for r in rows] + ["extra"]),
        "labels": np.array([1, 0, 0, 0, 0]),
        "groups": np.array(["g0", "g1", "g2", "g3", "extra"]),
        "splits": np.array(["train", "val", "val", "test", "train"]),
        "sources": np.array(["genimage_real"] * 5),
    }
    path = tmp_path / "features.npz"
    np.savez(path, **data)
    out = tmp_path / "fit"
    adv12_run.cmd_fit(
        Namespace(
            features=path, output_dir=out, name="candidate", C=10, seed=42, split=None
        )
    )
    args.model = out / "candidate.joblib"
    args.feature_manifest = tmp_path / "features.json"
    manifest = {
        "encoder": "layers",
        "image_column": "raw_path",
        "labels_sha256": adv12_run.sha256_file(args.labels),
        "features_sha256": adv12_run.sha256_file(path),
        "shape": [5, 4],
        "layers": "1",
        "model_id": "synthetic",
        "revision": "a" * 40,
    }
    args.feature_manifest.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        bench,
        "make_embed",
        lambda _: lambda images: np.ones((len(images), 4), dtype=np.float32),
    )
    assert bench.run(args)["status"] == "complete"
    manifest["features_sha256"] = "0" * 64
    args.feature_manifest.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="mismatch"):
        bench.load_predictor(args)
    args.model.write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        bench.load_predictor(args)
