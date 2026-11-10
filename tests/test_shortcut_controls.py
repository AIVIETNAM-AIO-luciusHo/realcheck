"""ADV-10 behavioral fixtures; no network, encoder, real model or test cohort."""

import csv
import json
from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from PIL import Image
from sklearn.metrics import roc_auc_score

from scripts import shortcut_controls as controls
from scripts.shortcut_metrics import (
    group_weights,
    interval,
    summarize_probabilities,
    verdict,
    weighted_stats,
)


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def experiment(tmp_path, monkeypatch):
    rows = []
    for si, source in enumerate(controls.SOURCES):
        for split in ("train", "val"):
            for index in range(2):
                path = tmp_path / f"{source}-{split}-{index}.png"
                rng = np.random.default_rng(si * 20 + index + (split == "val") * 2)
                Image.fromarray(
                    rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
                ).save(path)
                rows.append(
                    {
                        "raw_path": path.name,
                        "source": source,
                        "label": int(si > 0),
                        "split": split,
                    }
                )
    # A test path must never be opened, even for inventory or pixel hashing.
    rows.append(
        {
            "raw_path": "MUST_NOT_OPEN_TEST.png",
            "source": "genimage_glide",
            "label": 1,
            "split": "test",
        }
    )
    labels = tmp_path / "labels.csv"
    with labels.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    model = tmp_path / "model.joblib"
    model.write_bytes(b"not deserialized by preparation")
    digest = controls.sha256_file(model)
    model.with_suffix(".joblib.sha256").write_text(digest)
    monkeypatch.setattr(controls, "MODEL_SHA", digest)
    monkeypatch.setattr(controls, "LABELS_SHA", controls.sha256_file(labels))
    monkeypatch.setattr(
        controls, "COUNTS", {s: {"train": 2, "val": 2} for s in controls.SOURCES}
    )
    monkeypatch.setattr(controls, "runtime", lambda: {"python": "fixture"})
    monkeypatch.setattr(
        controls, "provenance", lambda: {"git_commit": "a" * 40, "git_dirty": False}
    )
    protocol = {
        "schema_version": 1,
        "status": "proposed",
        "code_commit": "a" * 40,
        "design": deepcopy(controls.DESIGN),
        "profile": {
            "clip_model_id": controls.CLIP_MODEL_ID,
            "clip_revision": controls.CLIP_REVISION,
            "normalization_version": "1",
        },
        "runtime": {"python": "fixture"},
        "exposure": "previous model selection validation",
        "history_limitations": "exact supplied history only",
        "independent_qa_approved": False,
        "expected_counts": controls.COUNTS,
        "dataset_root": ".",
        "model": {"path": model.name, "sha256": digest},
        "labels": {"path": labels.name, "sha256": controls.LABELS_SHA},
        "history": [{"path": labels.name, "sha256": controls.LABELS_SHA}],
    }
    path = tmp_path / "proposed.json"
    dump(path, protocol)
    return path, tmp_path / "prepared"


def test_prepare_train_val_only_and_reuse(experiment, monkeypatch):
    path, prepared = experiment
    calls = []
    normalize = controls.normalize_image
    monkeypatch.setattr(
        controls,
        "normalize_image",
        lambda image: (calls.append(image.size), normalize(image))[1],
    )
    controls.prepare(path, prepared)
    protocol, _, samples, variants = controls.validate_prepared(
        prepared / "protocol.json", prepared
    )
    assert len(samples) == 16 and len(variants) == 64
    assert all(r["split"] in {"train", "val"} for r in samples)
    assert protocol["status"] == "locked"
    assert len(calls) == 4 + 16 + 8 + 8  # real B; GLIDE four; MJ/SD B and J
    for row in samples:
        base = next(
            v
            for v in variants
            if v["sample_id"] == row["sample_id"] and v["arm"] == "B"
        )
        with Image.open(path.parent / row["raw_path"]) as image:
            assert (
                controls.sha256_file(prepared / base["post"]["path"])
                == controls.hashlib.sha256(normalize(image).jpeg).hexdigest()
            )
    assert not (path.parent / "MUST_NOT_OPEN_TEST.png").exists()
    with pytest.raises(FileExistsError):
        controls.prepare(path, prepared)


@pytest.mark.parametrize(
    "arm,encodes,size", [("B", 0, 256), ("J", 1, 256), ("R", 0, 512), ("JR", 1, 512)]
)
def test_intervention_order_and_no_original_mutation(arm, encodes, size, monkeypatch):
    image = Image.fromarray(
        np.random.default_rng(42).integers(0, 256, (256, 256, 3), dtype=np.uint8)
    )
    before = image.tobytes()
    events = []
    save, resize = Image.Image.save, Image.Image.resize

    def track_save(self, fp, format=None, **kwargs):
        events.append((format, self.size, kwargs))
        return save(self, fp, format, **kwargs)

    def track_resize(self, *args, **kwargs):
        events.append(("resize", args[0]))
        return resize(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", track_save)
    monkeypatch.setattr(Image.Image, "resize", track_resize)
    result, data, extension = controls.intervention(image, arm)
    assert image.tobytes() == before and result.size == (size, size)
    jpeg = [event for event in events if event[0] == "JPEG"]
    assert len(jpeg) == encodes
    if jpeg:
        assert jpeg[0][2] == controls.DESIGN["jpeg"]
        with Image.open(BytesIO(data)) as decoded:
            assert not decoded.getexif() and "icc_profile" not in decoded.info
    if arm == "JR":
        assert events[0][0] == "resize" and events[1][0] == "JPEG"
    if arm == "R":
        assert extension == ".png"


def test_exif_is_not_applied_twice():
    image = Image.new("RGB", (300, 256), "red")
    image.getexif()[274] = 6
    converted, _, _ = controls.intervention(image, "B")
    assert converted.size == (256, 300)
    assert (
        controls.normalize_image(image).jpeg == controls.normalize_image(converted).jpeg
    )


@pytest.mark.parametrize("source", controls.SOURCES)
def test_effective_arm_preserves_unaffected_inputs(source):
    if source == controls.SOURCES[0]:
        assert {controls.effective_arm(source, a) for a in controls.ARMS} == {"B"}
    elif source != "genimage_glide":
        assert controls.effective_arm(source, "R") == "B"
        assert controls.effective_arm(source, "JR") == "J"


def test_groups_link_transitive_duplicates_and_reject_leakage():
    rows = [
        {
            "sample_id": str(i),
            "raw_sha256": str(i),
            "decoded_pixel_sha256": str(i),
            "label": 0,
            "split": "train",
        }
        for i in range(3)
    ]
    rows[1]["raw_sha256"] = rows[0]["raw_sha256"]
    rows[2]["decoded_pixel_sha256"] = rows[1]["decoded_pixel_sha256"]
    controls.assign_groups(rows)
    assert len({r["group_id"] for r in rows}) == 1
    rows[2]["split"] = "val"
    with pytest.raises(ValueError, match="crosses"):
        controls.assign_groups(rows)
    rows[2]["split"] = "train"
    rows[2]["label"] = 1
    with pytest.raises(ValueError, match="contradictory"):
        controls.assign_groups(rows)


@pytest.mark.parametrize(
    "change",
    [
        "model",
        "labels",
        "runtime",
        "design",
        "code",
        "qa",
        "counts",
        "profile",
        "history",
    ],
)
def test_protocol_rejects_wrong_identity(experiment, change):
    path, _ = experiment
    p = controls.read_json(path)
    if change in {"model", "labels", "history"}:
        artifact = p[change][0] if change == "history" else p[change]
        artifact["sha256"] = "0" * 64
    elif change == "runtime":
        p["runtime"] = {}
    elif change == "design":
        p["design"]["jpeg"]["quality"] = 70
    elif change == "code":
        p["code_commit"] = "b" * 40
    elif change == "qa":
        p["independent_qa_approved"] = True
    elif change == "counts":
        p["expected_counts"] = {}
    else:
        p["profile"]["normalization_version"] = "2"
    dump(path, p)
    with pytest.raises(ValueError):
        controls.load_protocol(path)


def test_preflight_retains_invalid_image_evidence(experiment):
    path, prepared = experiment
    image = next(path.parent.glob("genimage_glide*.png"))
    image.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="Preflight"):
        controls.prepare(path, prepared)
    preflight = controls.read_json(prepared / "preflight.json")
    assert preflight["errors"][0]["error_code"] == "INVALID_IMAGE"
    assert not (prepared / "protocol.json").exists()


def test_small_image_and_non_256_glide_stop(experiment):
    path, prepared = experiment
    image = next(path.parent.glob("genimage_glide*.png"))
    Image.new("RGB", (255, 256)).save(image)
    with pytest.raises(ValueError, match="Preflight"):
        controls.prepare(path, prepared)
    assert (
        controls.read_json(prepared / "preflight.json")["errors"][0]["error_code"]
        == "IMAGE_TOO_SMALL"
    )


def test_non_256_glide_requires_new_protocol(experiment):
    path, prepared = experiment
    image = next(path.parent.glob("genimage_glide*.png"))
    Image.fromarray(
        np.random.default_rng(8).integers(0, 256, (300, 300, 3), dtype=np.uint8)
    ).save(image)
    with pytest.raises(ValueError, match="256x256"):
        controls.prepare(path, prepared)
    assert (prepared / "inventory.json").exists() and not (
        prepared / "protocol.json"
    ).exists()


def test_prepared_raw_or_variant_mutation_detected(experiment):
    path, prepared = experiment
    controls.prepare(path, prepared)
    variant = next(prepared.glob("images/*/*/post.jpg"))
    data = variant.read_bytes()
    variant.write_bytes(b"modified")
    with pytest.raises(ValueError, match="Variant hash"):
        controls.validate_prepared(prepared / "protocol.json", prepared)
    variant.write_bytes(data)
    original = next(path.parent.glob("genimage_real*.png"))
    original.write_bytes(b"modified")
    with pytest.raises(ValueError, match="Raw hash"):
        controls.validate_prepared(prepared / "protocol.json", prepared)


def test_unknown_metadata_category_is_missing():
    train = [
        {"format": "JPEG", "mode": "RGB", "width": 256},
        {"format": "PNG", "mode": "RGB", "width": 256},
    ]
    _, categories = controls.metadata_matrix(train)
    val, _ = controls.metadata_matrix(
        [{"format": "WEBP", "mode": "P", "width": 512}], categories
    )
    assert pd.isna(val.loc[0, "format"]) and pd.isna(val.loc[0, "mode"])


def metric_rows():
    return [
        {"group_id": str(i), "source": "real" if i < 2 else "ai", "label": int(i >= 2)}
        for i in range(4)
    ]


def test_metric_boundaries_accuracy_and_degradation():
    assert verdict([0.29, 0.3, 0.5, 0.7, 0.71]).tolist() == [0, 1, 1, 1, 2]
    rows = metric_rows()
    result = summarize_probabilities(
        rows, [0.3, 0.6, 0.5, 0.7], [0.1, 0.1, 0.9, 0.9], replicates=50
    )
    assert result["accuracy"] == 0.75 and result["uncertain_rate"] == 1
    assert result["paired"]["flip_rate"] == 1
    assert result["paired"]["deltas"]["accuracy_degradation"]["value"] == 0.25
    assert result["confusion_matrix"] == [[1, 1], [0, 2]]
    assert np.asarray(result["paired"]["transitions"]).sum() == 4


def test_weighted_auroc_matches_sklearn_with_ties():
    y = np.array([0, 0, 1, 1, 0, 1])
    p = np.array([0.1, 0.5, 0.5, 0.9, 0.9, 0.5])
    weights = np.array([[1, 2, 3, 1, 1, 2], [2, 1, 1, 2, 3, 1]])
    actual = weighted_stats(y, p, weights)["auroc"]
    assert actual == pytest.approx(
        [roc_auc_score(y, p, sample_weight=w) for w in weights]
    )


def test_bootstrap_whole_groups_seed_and_reordered_rows():
    rows = metric_rows()
    rows.append(dict(rows[2]))
    weights = group_weights(rows, 100)
    assert np.array_equal(weights, group_weights(rows, 100))
    assert np.array_equal(weights[:, 2], weights[:, 4])
    reverse = group_weights(rows[::-1], 100)
    assert np.array_equal(weights, reverse[:, ::-1])


def test_single_class_and_undefined_metrics():
    rows = [{"group_id": "one", "source": "real", "label": 0}]
    result = summarize_probabilities(rows, [0.1], replicates=30)
    assert (
        result["precision"] == 0
        and result["metric_definition"]["precision"]["defined"] is False
    )
    assert result["intervals"]["precision"]["ci95"] is None
    assert result["intervals"]["accuracy"]["reason"] == "fewer_than_two_groups"
    assert result["balanced_accuracy"] is None
    assert interval(np.array([1, np.nan]), 4)["n_boot_valid"] == 1
    assert interval(np.array([1, np.nan]), 4)["ci95"] is None


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_scores_rejected(score):
    with pytest.raises(ValueError):
        summarize_probabilities(metric_rows(), [score, 0.2, 0.8, 0.9], replicates=10)


def test_json_never_silently_converts_nonfinite(tmp_path):
    path = tmp_path / "out.json"
    with pytest.raises(ValueError):
        controls.write_json(path, {"invalid": float("nan")})
    with pytest.raises(FileExistsError):
        controls.write_json(path, {})


@pytest.fixture
def fake_scorer(monkeypatch):
    from models import score as score_module

    calls = []
    encoder = SimpleNamespace(training=False, parameters=list)

    def encode(images, encoder):
        calls.append(images[0].size)
        return np.array([[np.asarray(images[0]).mean() / 255]])

    class FakeScorer:
        encoder = None

        def predict_features(self, features):
            return features[:, 0]

        def __call__(self, image):
            return float(np.asarray(controls.normalize_image(image).image).mean() / 255)

    scorer = FakeScorer()
    scorer.encoder = encoder
    monkeypatch.setattr(score_module, "load_scorer", lambda *a, **kw: scorer)
    monkeypatch.setattr(controls, "encode_images", encode)
    return calls, scorer


def test_inference_cached_pixels_and_all_parity_before_main(experiment, fake_scorer):
    path, prepared = experiment
    controls.prepare(path, prepared)
    _, _, samples, variants = controls.validate_prepared(
        prepared / "protocol.json", prepared
    )
    output = prepared / "run"
    output.mkdir()
    result = controls.infer_validation(
        samples, variants, prepared, path.parent / "model.joblib", output
    )
    calls, _ = fake_scorer
    assert result["logical_predictions"] == 32
    assert len(calls) == result["unique_post_inferences"] == 18
    assert result["parity"] == {s: 0 for s in controls.SOURCES}
    assert set(calls) == {(256, 256)}
    with (output / "predictions.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    assert all(r["split"] == "val" and r["status"] == "ok" for r in rows)


def test_parity_failure_stops_before_predictions(experiment, fake_scorer, monkeypatch):
    path, prepared = experiment
    controls.prepare(path, prepared)
    _, _, samples, variants = controls.validate_prepared(
        prepared / "protocol.json", prepared
    )
    output = prepared / "failed"
    output.mkdir()
    monkeypatch.setattr(type(fake_scorer[1]), "__call__", lambda self, image: 0)
    with pytest.raises(ValueError, match="parity"):
        controls.infer_validation(
            samples, variants, prepared, path.parent / "model.joblib", output
        )
    assert not (output / "predictions.csv").exists()


def test_probes_fit_only_train_and_save_all_cells(experiment, monkeypatch):
    path, prepared = experiment
    controls.prepare(path, prepared)
    _, _, samples, variants = controls.validate_prepared(
        prepared / "protocol.json", prepared
    )
    sizes = []
    for cls in (
        controls.LogisticRegression,
        controls.DecisionTreeClassifier,
        controls.HistGradientBoostingClassifier,
    ):
        original = cls.fit

        def track(self, x, y, original=original, **kwargs):
            sizes.append(len(y))
            return original(self, x, y, **kwargs)

        monkeypatch.setattr(cls, "fit", track)
    predictions, diagnostics = controls.audit_probes(samples, variants)
    assert set(sizes) == {4}
    assert len(predictions) == 3 * 3 * 9 * 4
    assert all(
        r["sample_id"] in {s["sample_id"] for s in samples if s["split"] == "val"}
        for r in predictions
    )
    post = diagnostics["genimage_glide/post/B"]
    assert len(post["constant_features"]) == 13
    assert "genimage_glide/raw/controls" in diagnostics


@pytest.fixture
def saved_run(experiment, fake_scorer, monkeypatch):
    path, prepared = experiment
    controls.prepare(path, prepared)
    _, _, samples, variants = controls.validate_prepared(
        prepared / "protocol.json", prepared
    )
    output = prepared / "run"
    output.mkdir()
    inference = controls.infer_validation(
        samples, variants, prepared, path.parent / "model.joblib", output
    )
    audits = []
    for pair in controls.SOURCES[1:]:
        for stage in ("raw", "post"):
            for probe in ("logreg", "tree_depth3", "metadata"):
                for mode in ("refit",) if stage == "raw" else ("fixed", "refit"):
                    for arm in ("B",) if stage == "raw" else controls.ARMS:
                        for sample in samples:
                            if sample["split"] == "val" and sample["source"] in (
                                controls.SOURCES[0],
                                pair,
                            ):
                                audits.append(
                                    {
                                        "sample_id": sample["sample_id"],
                                        "pair": pair,
                                        "stage": stage,
                                        "probe": probe,
                                        "mode": mode,
                                        "arm": arm,
                                        "score": 0.9 if sample["label"] else 0.1,
                                    }
                                )
    dump(output / "audit-predictions.json", audits)
    dump(output / "audit-diagnostics.json", {})
    dump(
        output / "run-start.json",
        {
            "protocol_sha256": controls.sha256_file(prepared / "protocol.json"),
            "prepared": "..",
            "run": {"git_commit": "a" * 40, "git_dirty": False},
            "runtime": controls.runtime(),
        },
    )
    checksums = {
        name: controls.sha256_file(output / name)
        for name in (
            "audit-predictions.json",
            "audit-diagnostics.json",
            "run-start.json",
            "predictions.csv",
        )
    }
    dump(output / "run-complete.json", {"checksums": checksums, "inference": inference})
    original = controls.summarize_probabilities
    monkeypatch.setattr(
        controls,
        "summarize_probabilities",
        lambda *a, **kw: original(*a, replicates=10, **kw),
    )
    return output


def test_summary_is_reproducible_and_refuses_overwrite(saved_run):
    output = saved_run / "result.json"
    result = controls.summarize(saved_run, output)
    assert result["status"] == "measured_pending_independent_review"
    assert (
        result["independent_qa_approved"] is False
        and result["shortcut_excluded"] is False
    )
    assert len(result["audit"]) == 81
    assert result["model"]["real_vs_genimage_glide"]["B"]["n_total"] == 4
    with pytest.raises(ValueError, match="exists"):
        controls.summarize(saved_run, output)


@pytest.mark.parametrize(
    "tamper",
    ["missing", "duplicate", "group", "hash", "nan", "verdict", "audit_missing"],
)
def test_summary_rejects_inconsistent_saved_predictions(saved_run, tamper):
    if tamper == "audit_missing":
        path = saved_run / "audit-predictions.json"
        rows = controls.read_json(path)
        rows.pop()
        dump(path, rows)
    else:
        path = saved_run / "predictions.csv"
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        if tamper == "missing":
            rows.pop()
        elif tamper == "duplicate":
            rows[-1] = dict(rows[0])
        elif tamper == "group":
            rows[0]["group_id"] = "wrong"
        elif tamper == "hash":
            rows[0]["post_sha256"] = "wrong"
        elif tamper == "nan":
            rows[0]["score"] = "nan"
        else:
            rows[0]["verdict"] = "wrong"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    completed = controls.read_json(saved_run / "run-complete.json")
    completed["checksums"][path.name] = controls.sha256_file(path)
    dump(saved_run / "run-complete.json", completed)
    with pytest.raises(ValueError):
        controls.summarize(saved_run, saved_run / "result.json")


def test_summary_reports_partial_and_matched_counts(saved_run):
    path = saved_run / "predictions.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    child = next(r for r in rows if r["arm"] == "J")
    child.update(status="error", score="", verdict="", error_code="INFERENCE_ERROR")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    completed = controls.read_json(saved_run / "run-complete.json")
    completed["checksums"][path.name] = controls.sha256_file(path)
    dump(saved_run / "run-complete.json", completed)
    result = controls.summarize(saved_run, saved_run / "partial.json")
    assert result["status"] == "partial"
    cell = result["model"][child["source"]]["J"]
    assert cell["n_total"] == 2 and cell["n_scored"] == 1 and cell["n_failed"] == 1
    assert cell["paired"]["n_pairs"] == 1
