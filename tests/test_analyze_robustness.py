"""ADV-08 contracts: only synthetic images/predictions, no encoder or model load."""

import csv
import json
from copy import deepcopy

import pytest
from PIL import Image

from scripts import analyze_robustness as ar


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def write_manifest(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def write_predictions(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def handoff(tmp_path, monkeypatch):
    # Small bootstrap for integration/schema cases; separate tests exercise 2000 draws.
    monkeypatch.setattr(
        ar, "BOOTSTRAP", {"replicates": 20, "seed": 42, "confidence": 0.95}
    )
    model = tmp_path / "probe.joblib"
    model.write_bytes(b"synthetic checksum fixture, never unpickle")
    monkeypatch.setattr(ar, "MODEL_SHA256", ar.sha256_file(model))
    model.with_suffix(".joblib.sha256").write_text(
        ar.MODEL_SHA256 + "\n", encoding="ascii"
    )
    profile = {
        "clip_model_id": ar.CLIP_ID,
        "clip_revision": ar.CLIP_REVISION,
        "normalization_version": "1",
    }
    model_manifest = tmp_path / "model.json"
    write_json(
        model_manifest,
        {**profile, "model_sha256": ar.MODEL_SHA256, "thresholds": ar.THRESHOLDS},
    )
    history = tmp_path / "history.csv"
    history.write_text(
        "group_id,split\nold-training,train\nold-val,val\n", encoding="utf-8"
    )
    rows = []
    for cohort, kind in (("parents", "original"), ("jpeg90", "jpeg")):
        for label in (0, 1):
            sid = f"{cohort}-{label}"
            path = tmp_path / f"{sid}.png"
            Image.new("RGB", (256, 256), (label * 150, len(rows) * 20, 5)).save(path)
            rows.append(
                {
                    "sample_id": sid,
                    "path": path.name,
                    "sha256": ar.sha256_file(path),
                    "label": label,
                    "source": "genimage_real" if label == 0 else "genimage_ai",
                    "cohort": cohort,
                    "split": "test",
                    "group_id": f"g{label}",
                    "parent_id": None if kind == "original" else f"parents-{label}",
                    "transform": {
                        "kind": kind,
                        "params": {} if kind == "original" else {"quality": 90},
                    },
                }
            )
    manifest = tmp_path / "manifest.jsonl"
    write_manifest(manifest, rows)
    cohorts = [
        {
            "name": name,
            "status": "present",
            "n_expected": 2,
            "transform": rows[index]["transform"],
        }
        for name, index in (("parents", 0), ("jpeg90", 2))
    ]
    cohorts += [
        {"name": name, "status": "missing", "reason": "not supplied"}
        for name in sorted(ar.EXPECTED_COHORTS - {"parents", "jpeg90"})
    ]
    protocol = {
        "schema_version": 1,
        "status": "locked",
        "manifest_lock_ref": "fixture-approval",
        "split_review_ref": "fixture-split-review",
        "parent_exposure": "synthetic only",
        "runner": {
            "commit": "a" * 40,
            "handoff_ref": "fixture #51",
            "tests_ref": "fixture tests",
        },
        "analysis_commit": "b" * 40,
        "thresholds": deepcopy(ar.THRESHOLDS),
        "bootstrap": deepcopy(ar.BOOTSTRAP),
        "profile": profile,
        "cohorts": cohorts,
        "artifacts": {
            name: {"path": path.name, "sha256": ar.sha256_file(path)}
            for name, path in (
                ("model", model),
                ("model_manifest", model_manifest),
                ("manifest", manifest),
            )
        },
        "history": [{"path": history.name, "sha256": ar.sha256_file(history)}],
    }
    protocol_path = tmp_path / "protocol.json"
    write_json(protocol_path, protocol)
    monkeypatch.setattr(
        ar,
        "run_info",
        lambda _: {
            "git_commit": "b" * 40,
            "git_dirty": False,
            "command": ["C:/Users/private/python"],
            "working_directory": "private",
        },
    )
    predictions = []
    for row, score in zip(rows, (0.1, 0.9, 0.8, 0.5)):
        predictions.append(
            {
                "sample_id": row["sample_id"],
                "group_id": row["group_id"],
                "parent_id": row["parent_id"] or "",
                "label": str(row["label"]),
                "status": "ok",
                "score": score,
                "verdict": ar.verdict(score),
                "error_code": "",
                "model_sha256": ar.MODEL_SHA256,
                "manifest_sha256": ar.sha256_file(manifest),
                "protocol_sha256": ar.sha256_file(protocol_path),
            }
        )
    pred_path = tmp_path / "predictions.csv"
    write_predictions(pred_path, predictions)
    return {
        "protocol": protocol,
        "protocol_path": protocol_path,
        "manifest": manifest,
        "rows": rows,
        "predictions": predictions,
        "pred_path": pred_path,
        "tmp": tmp_path,
    }


def refresh(h):
    write_manifest(h["manifest"], h["rows"])
    h["protocol"]["artifacts"]["manifest"]["sha256"] = ar.sha256_file(h["manifest"])
    write_json(h["protocol_path"], h["protocol"])
    for p in h["predictions"]:
        p["manifest_sha256"] = ar.sha256_file(h["manifest"])
        p["protocol_sha256"] = ar.sha256_file(h["protocol_path"])
    write_predictions(h["pred_path"], h["predictions"])


def test_boundaries_and_accuracy_including_uncertain():
    assert [ar.verdict(s) for s in (0.299, 0.3, 0.5, 0.7, 0.701)] == [
        "likely_real",
        "uncertain",
        "uncertain",
        "uncertain",
        "likely_ai",
    ]
    rows = [{"sample_id": str(i), "label": label} for i, label in enumerate((0, 1))]
    pred = {"0": {"score": 0.3}, "1": {"score": 0.5}}
    point = ar.point_metrics(rows, pred)
    assert point["n"] == 2 and point["accuracy"] == 1 and point["uncertain_rate"] == 1
    assert point["decided_accuracy"] is None


def test_analysis_pairs_by_id_and_preserves_missing(handoff):
    h = handoff
    write_predictions(h["pred_path"], list(reversed(h["predictions"])))
    report = ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])
    jpeg = next(c for c in report["cohorts"] if c["name"] == "jpeg90")
    assert jpeg["metrics"]["accuracy"] == 0.5
    assert jpeg["pairing"]["metrics"]["flip_rate"] == 1
    assert jpeg["pairing"]["metrics"]["accuracy_degradation"] == 0.5
    assert jpeg["pairing"]["parent_matched"]["accuracy"] == 1
    assert jpeg["pairing"]["transition_counts"] == [[0, 0, 1], [0, 0, 0], [0, 1, 0]]
    assert report["status"] == "incomplete" and not report["independent_qa_approved"]
    missing = next(c for c in report["cohorts"] if c["name"] == "zalo")
    assert missing["status"] == "missing" and missing["metrics"] is None
    assert "command" not in report["run"] and "working_directory" not in report["run"]
    assert "accuracy" not in report  # no overall mixture of parents and variants


def test_failed_parent_excluded_from_pairs_but_not_error_counts(handoff):
    h = handoff
    h["predictions"][0].update(
        status="error", score="", verdict="", error_code="MODEL_ERROR"
    )
    write_predictions(h["pred_path"], h["predictions"])
    report = ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])
    parents = next(c for c in report["cohorts"] if c["name"] == "parents")
    child = next(c for c in report["cohorts"] if c["name"] == "jpeg90")
    assert (
        parents["n_total"] == 2
        and parents["n_scored"] == 1
        and parents["n_failed"] == 1
    )
    assert child["pairing"]["n_pairs"] == 1
    assert child["pairing"]["parent_matched"]["n"] == 1
    assert child["pairing"]["metrics"]["accuracy_degradation"] == 0


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("sample_id", "parents-0", "Duplicate sample_id"),
        ("parent_id", "unknown", "Missing parent"),
        ("parent_id", "jpeg90-0", "Self parent"),
        ("group_id", "another", "Parent/child differ"),
        ("label", 1, "Conflicting group labels"),
        ("split", "train", "must be test"),
        ("source", "cifake_real", "CIFAKE"),
    ],
)
def test_bad_manifest_lineage_rejected(handoff, field, value, message):
    h = handoff
    h["rows"][2][field] = value
    refresh(h)
    with pytest.raises(ValueError, match=message):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


def test_parent_chains_cycles_rejected(handoff):
    h = handoff
    h["rows"][0]["parent_id"] = "jpeg90-0"
    refresh(h)
    with pytest.raises(ValueError, match="Original cannot be a child"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


def test_duplicate_bytes_cannot_hide_in_another_group(handoff):
    h = handoff
    h["rows"][2]["sha256"] = h["rows"][0]["sha256"]
    h["rows"][2]["path"] = h["rows"][0]["path"]
    h["rows"][2]["group_id"] = "hidden-duplicate"
    refresh(h)
    with pytest.raises(ValueError, match="Exact duplicates"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


@pytest.mark.parametrize(
    "case",
    ["image", "model", "model_manifest", "history", "raw_sidecar", "missing_file"],
)
def test_corrupt_artifacts_rejected(handoff, case):
    h = handoff
    paths = {
        "image": h["tmp"] / h["rows"][0]["path"],
        "model": h["tmp"] / "probe.joblib",
        "model_manifest": h["tmp"] / "model.json",
        "history": h["tmp"] / "history.csv",
        "raw_sidecar": h["tmp"] / "probe.joblib.sha256",
    }
    if case == "missing_file":
        (h["tmp"] / h["rows"][0]["path"]).unlink()
    else:
        paths[case].write_bytes(b"changed")
    with pytest.raises((ValueError, OSError)):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


def test_cross_split_history_rejected(handoff):
    h = handoff
    history = h["tmp"] / "history.csv"
    history.write_text("group_id,split\ng0,train\n", encoding="utf-8")
    h["protocol"]["history"][0]["sha256"] = ar.sha256_file(history)
    refresh(h)
    with pytest.raises(ValueError, match="Group overlaps"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("status", "draft"),
        ("thresholds", {"binary": 0.6, "low": 0.3, "high": 0.7}),
        ("bootstrap", {"replicates": 20, "seed": 100, "confidence": 0.95}),
        ("analysis_commit", None),
        ("manifest_lock_ref", ""),
        ("history", []),
    ],
)
def test_unlocked_or_missing_protocol_evidence_rejected(handoff, key, value):
    h = handoff
    h["protocol"][key] = value
    refresh(h)
    with pytest.raises(ValueError):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


def test_expected_cohort_cannot_be_silently_omitted(handoff):
    h = handoff
    h["protocol"]["cohorts"] = [
        c for c in h["protocol"]["cohorts"] if c["name"] != "phone"
    ]
    refresh(h)
    with pytest.raises(ValueError, match="explicitly missing"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


@pytest.mark.parametrize(
    "case",
    [
        "nan",
        "inf",
        "outside",
        "unknown",
        "duplicate",
        "missing",
        "wrong_model",
        "wrong_manifest",
        "wrong_protocol",
        "wrong_verdict",
        "wrong_parent",
        "error_with_score",
    ],
)
def test_invalid_predictions_rejected(handoff, case):
    h = handoff
    predictions = deepcopy(h["predictions"])
    if case in {"nan", "inf", "outside"}:
        predictions[0]["score"] = {"nan": "nan", "inf": "inf", "outside": "1.01"}[case]
    elif case == "unknown":
        predictions[0]["sample_id"] = "unknown"
    elif case == "duplicate":
        predictions.append(predictions[0])
    elif case == "missing":
        predictions.pop()
    elif case.startswith("wrong_") and case[6:] in {"model", "manifest", "protocol"}:
        predictions[0][case[6:] + "_sha256"] = "0" * 64
    elif case == "wrong_verdict":
        predictions[0]["verdict"] = "likely_ai"
    elif case == "wrong_parent":
        predictions[0]["parent_id"] = "unexpected"
    else:
        predictions[0].update(status="error", error_code="MODEL_ERROR")
    write_predictions(h["pred_path"], predictions)
    with pytest.raises(ValueError):
        ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])


def test_preflight_checks_images_without_predictions_or_model_load(handoff):
    h = handoff
    tiny = h["tmp"] / h["rows"][2]["path"]
    Image.new("RGB", (10, 10)).save(tiny)
    h["rows"][2]["sha256"] = ar.sha256_file(tiny)
    refresh(h)
    output = h["tmp"] / "preflight.json"
    code = ar.main(
        [
            "--protocol",
            str(h["protocol_path"]),
            "--manifest",
            str(h["manifest"]),
            "--preflight",
            "--output",
            str(output),
        ]
    )
    report = json.loads(output.read_text("utf-8"))
    assert code == 1 and report["image_failures"] == {"jpeg90-0": "IMAGE_TOO_SMALL"}
    assert not report["inference_performed"]


def test_cli_partial_report_is_nonzero_and_cannot_overwrite(handoff):
    h = handoff
    output = h["tmp"] / "robustness.json"
    argv = [
        "--protocol",
        str(h["protocol_path"]),
        "--manifest",
        str(h["manifest"]),
        "--predictions",
        str(h["pred_path"]),
        "--output",
        str(output),
    ]
    assert ar.main(argv) == 1
    first = output.read_bytes()
    with pytest.raises(SystemExit) as exc:
        ar.main(argv)
    assert exc.value.code == 2 and output.read_bytes() == first
    assert "NaN" not in first.decode() and "C:/Users" not in first.decode()


def test_invalid_handoff_writes_non_success_without_metrics(handoff):
    h = handoff
    h["protocol"]["status"] = "draft"
    refresh(h)
    output = h["tmp"] / "blocked.json"
    assert (
        ar.main(
            [
                "--protocol",
                str(h["protocol_path"]),
                "--manifest",
                str(h["manifest"]),
                "--preflight",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    report = json.loads(output.read_text("utf-8"))
    assert report["status"] == "invalid_handoff" and "metrics" not in report


@pytest.mark.parametrize(
    "commit,dirty", [("c" * 40, False), ("b" * 40, True), (None, None)]
)
def test_provenance_must_be_clean_and_match_lock(handoff, monkeypatch, commit, dirty):
    h = handoff
    monkeypatch.setattr(
        ar, "run_info", lambda _: {"git_commit": commit, "git_dirty": dirty}
    )
    with pytest.raises(ValueError, match="source differs|clean Git"):
        ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])


def test_stratified_group_bootstrap_is_paired_reproducible_and_uses_2000():
    assert ar.BOOTSTRAP == {"replicates": 2000, "seed": 42, "confidence": 0.95}
    parents, children, predictions = [], [], {}
    for group in range(2):
        for child in range(2):
            pid, cid = f"p{group}-{child}", f"c{group}-{child}"
            row = {
                "sample_id": cid,
                "label": 0,
                "source": "real",
                "group_id": str(group),
            }
            children.append(row)
            parents.append({**row, "sample_id": pid})
            predictions[pid] = {"score": 0.1}
            predictions[cid] = {"score": 0.9 if group else 0.1}
    first = ar.bootstrap(children, predictions, parents)
    assert first == ar.bootstrap(children, predictions, parents)
    # Two children in a group must move together: possible losses are 0, .5, 1.
    assert first["accuracy_degradation"]["interval"] == [0, 1]
    assert first["flip_rate"]["n_boot_valid"] == 2000
    assert first["delta_recall"]["interval"] is None
    assert first["delta_recall"]["n_boot_valid"] == 0


def test_single_group_and_undefined_denominators_are_explicit():
    rows = [{"sample_id": "a", "group_id": "g", "source": "real", "label": 0}]
    predictions = {"a": {"score": 0.1}}
    point = ar.point_metrics(rows, predictions)
    assert point["precision"] == 0 and point["recall"] == 0
    assert not point["defined"]["precision"] and not point["defined"]["recall"]
    assert point["denominators"] == {
        "precision": 0,
        "recall": 0,
        "false_positive_rate": 1,
    }
    assert all(v["interval"] is None for v in ar.bootstrap(rows, predictions).values())


def test_undefined_bootstrap_replicate_does_not_become_zero():
    rows = [
        {"sample_id": str(i), "group_id": str(i), "source": "real", "label": 0}
        for i in (0, 1)
    ]
    predictions = {"0": {"score": 0.1}, "1": {"score": 0.9}}
    interval = ar.bootstrap(rows, predictions)["precision"]
    assert 0 < interval["n_boot_valid"] < 2000
    assert interval["interval"] is None
    assert interval["reason"] == "undefined_metric_or_bootstrap_replicate"


def test_complete_report_is_pending_review_not_quality_gate(handoff):
    h = handoff
    by_id = {r["sample_id"]: r for r in h["rows"]}
    for cohort in h["protocol"]["cohorts"]:
        if cohort["status"] == "present":
            continue
        name = cohort["name"]
        root = name in {"phone", "ai_new"}
        label = 1 if name == "ai_new" else 0
        parent = by_id[f"parents-{label}"]
        kind = "original" if root else "jpeg" if name.startswith("jpeg") else name
        params = (
            {}
            if root
            else {"quality": int(name[4:])}
            if name.startswith("jpeg")
            else {"fixture": True}
        )
        transform = {"kind": kind, "params": params}
        row = {
            **parent,
            "sample_id": name,
            "cohort": name,
            "parent_id": None if root else parent["sample_id"],
            "transform": transform,
        }
        h["rows"].append(row)
        cohort.clear()
        cohort.update(name=name, status="present", n_expected=1, transform=transform)
        prediction = {
            **h["predictions"][label],
            "sample_id": name,
            "parent_id": row["parent_id"] or "",
            "score": 0.9,
            "verdict": "likely_ai",
        }
        h["predictions"].append(prediction)
    refresh(h)
    output = h["tmp"] / "complete.json"
    assert (
        ar.main(
            [
                "--protocol",
                str(h["protocol_path"]),
                "--manifest",
                str(h["manifest"]),
                "--predictions",
                str(h["pred_path"]),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text("utf-8"))
    assert report["status"] == "complete_pending_independent_review"
    assert not report["release_approved"] and not report["independent_qa_approved"]
    assert (
        next(c for c in report["cohorts"] if c["name"] == "phone")["metrics"][
            "accuracy"
        ]
        == 0
    )


def test_model_profile_mismatch_rejected_even_with_updated_manifest_hash(handoff):
    h = handoff
    path = h["tmp"] / "model.json"
    value = json.loads(path.read_text("utf-8"))
    value["clip_revision"] = "wrong"
    write_json(path, value)
    h["protocol"]["artifacts"]["model_manifest"]["sha256"] = ar.sha256_file(path)
    refresh(h)
    with pytest.raises(ValueError, match="Model manifest mismatch: clip_revision"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


def test_input_changed_during_analysis_is_detected(handoff, monkeypatch):
    h = handoff
    original = ar.bootstrap

    def change_after_read(*args, **kwargs):
        h["manifest"].write_text("changed", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(ar, "bootstrap", change_after_read)
    with pytest.raises(ValueError, match="Input changed during analysis"):
        ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])


def test_report_rejects_personal_paths_in_evidence(handoff):
    h = handoff
    h["protocol"]["runner"]["handoff_ref"] = "C:\\Users\\private\\handoff.txt"
    refresh(h)
    with pytest.raises(ValueError, match="personal path"):
        ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])


@pytest.mark.parametrize("value", [[], None, 12])
def test_non_object_protocol_is_invalid(handoff, value):
    h = handoff
    write_json(h["protocol_path"], value)
    with pytest.raises(ValueError, match="must be an object"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


@pytest.mark.parametrize("value", [[], None])
def test_non_object_model_manifest_is_invalid(handoff, value):
    h = handoff
    path = h["tmp"] / "model.json"
    write_json(path, value)
    h["protocol"]["artifacts"]["model_manifest"]["sha256"] = ar.sha256_file(path)
    refresh(h)
    with pytest.raises(ValueError, match="Model manifest must be an object"):
        ar.validate_handoff(h["protocol_path"], h["manifest"])


def test_preflight_receipt_binds_exact_inputs_without_authorizing_inference(handoff):
    h = handoff
    report = ar.preflight_report(h["protocol_path"], h["manifest"])
    assert report["kind"] == "adv08_preflight" and report["status"] == "ready"
    assert report["protocol_sha256"] == ar.sha256_file(h["protocol_path"])
    assert report["manifest_sha256"] == ar.sha256_file(h["manifest"])
    assert (
        report["model_manifest_sha256"]
        == h["protocol"]["artifacts"]["model_manifest"]["sha256"]
    )
    assert report["runner"] == h["protocol"]["runner"]
    assert report["ready_scope"] == "available_cohorts_only"
    assert report["missing_cohorts"] and report["preflight_is_not_run_authorization"]
    assert report["inference_performed"] is False


@pytest.mark.parametrize(
    "kind,parameter", [("center_crop", "keep"), ("downscale", "scale")]
)
def test_clamped_geometry_is_observed_without_removing_samples(kind, parameter):
    rows = [
        {"sample_id": "parent", "parent_id": None},
        {
            "sample_id": "child",
            "parent_id": "parent",
            "cohort": kind,
            "transform": {"kind": kind, "params": {parameter: 0.5, "min_side": 256}},
        },
    ]
    observations = {
        "parent": {"size": [256, 256], "pixel_sha256": "same"},
        "child": {"size": [256, 256], "pixel_sha256": "same"},
    }
    result = ar.observed_transforms(rows, observations)[kind]
    assert result["n_pairs_observed"] == result["n_same_size"] == 1
    assert result["n_identical_oriented_rgb"] == result["n_clamped_geometry"] == 1
    assert result["geometry_examples"][0]["effective_short_side_ratio"] == 1
    assert len(rows) == 2  # no post-score filtering of degenerate interventions
    observations["parent"]["size"] = [512, 512]
    observations["parent"]["pixel_sha256"] = "different"
    result = ar.observed_transforms(rows, observations)[kind]
    assert result["n_clamped_geometry"] == result["n_identical_oriented_rgb"] == 0
    assert result["geometry_examples"][0]["effective_short_side_ratio"] == 0.5


def test_decode_observations_use_oriented_pixels_and_survive_analysis(handoff):
    h = handoff
    observations = {}
    ar.validate_handoff(
        h["protocol_path"], h["manifest"], decode=True, observations=observations
    )
    assert len(observations) == len(h["rows"])
    assert observations["parents-0"]["size"] == [256, 256]
    report = ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])
    assert report["observed_transforms"]["jpeg90"]["n_pairs_observed"] == 2


def test_analysis_rejects_success_for_image_that_fails_preflight(handoff):
    h = handoff
    child = h["rows"][2]
    Image.new("RGB", (64, 64), "red").save(h["tmp"] / child["path"])
    child["sha256"] = ar.sha256_file(h["tmp"] / child["path"])
    refresh(h)
    for prediction in h["predictions"]:
        prediction["manifest_sha256"] = ar.sha256_file(h["manifest"])
        prediction["protocol_sha256"] = ar.sha256_file(h["protocol_path"])
    write_predictions(h["pred_path"], h["predictions"])
    with pytest.raises(ValueError, match="invalid image has a successful"):
        ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])
    h["predictions"][2].update(
        status="error", score="", verdict="", error_code="IMAGE_TOO_SMALL"
    )
    write_predictions(h["pred_path"], h["predictions"])
    report = ar.analyze(h["protocol_path"], h["manifest"], h["pred_path"])
    child_report = next(c for c in report["cohorts"] if c["name"] == "jpeg90")
    assert report["status"] == "incomplete" and child_report["n_failed"] == 1
