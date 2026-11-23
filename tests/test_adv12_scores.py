"""Synthetic contracts for validation fitting, frozen application and paired fusion."""

import csv
import json

import numpy as np
import pytest

from scripts import adv12_scores as run
from scripts import compare_models as cm

SHA_A, SHA_B = "1" * 64, "2" * 64


@pytest.fixture
def inputs(tmp_path):
    labels = tmp_path / "labels.csv"
    labels.write_text(
        "filepath,label,source,split,raw_path,norm_version,group_id\n"
        + "".join(
            f"s{i},{i % 2},genimage_{'sd14' if i % 2 else 'real'},val,raw{i},1,g{i}\n"
            for i in range(40)
        ),
        encoding="utf-8",
    )
    files = []
    for k in range(2):
        path = tmp_path / f"{k}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["sample_id", "label", "score", "group_id", "source"])
            for i in reversed(range(40)) if k else range(40):
                score = 0.1 + 0.5 * (i % 2) + (i % 7) * 0.04 + k * 0.03
                writer.writerow(
                    [
                        f"s{i}",
                        i % 2,
                        score,
                        f"g{i}",
                        "genimage_sd14" if i % 2 else "genimage_real",
                    ]
                )
        files.append(path)
    return labels, *files


def fit_args(inputs, output, mode="platt"):
    labels, a, b = inputs
    args = [
        "fit",
        "--mode",
        mode,
        "--labels",
        str(labels),
        "--a",
        str(a),
        "--a-model-sha",
        SHA_A,
        "--target-fpr",
        "0.0",
        "--e0",
        str(a),
        "--replicates",
        "30",
        "--output-dir",
        str(output),
    ]
    return args + (["--b", str(b), "--b-model-sha", SHA_B] if mode == "mean" else [])


@pytest.mark.parametrize("mode", ["platt", "mean"])
def test_fit_then_apply_frozen_on_one_class_without_fit(
    inputs, tmp_path, monkeypatch, mode
):
    fitted = tmp_path / "fit"
    assert run.main(fit_args(inputs, fitted, mode)) == 0
    report = json.loads((fitted / "report.json").read_text())
    params = json.loads((fitted / "params.json").read_text())
    assert report["status"] == "completed" and report["n"] == 40
    assert report["probability_verified"] is False
    assert "same_validation" in report["metrics_scope"]
    assert report["selected_operating_point"]["genimage_real"]["fnr"]["value"] is None
    assert report["selected_operating_point"]["__all__"]["fpr"]["ci95"] is not None
    assert (
        report["fixed_thresholds_A_vs_result"]["slices"]["__all__"]["paired_A_minus_B"][
            "auroc"
        ]["ci95"]
        is not None
    )
    for name, digest in report["output_sha256"].items():
        assert cm.sha256_file(fitted / name) == digest
    # Apply to a new, all-real cohort. Fit and threshold selection must never be called.
    a, b = tmp_path / "new-a.csv", tmp_path / "new-b.csv"
    a.write_text("sample_id,label,score\nnew,0,0.8\n")
    b.write_text("sample_id,label,score\nnew,0,0.4\n")
    monkeypatch.setattr(run, "fit", lambda *args: pytest.fail("apply must not fit"))
    monkeypatch.setattr(
        run.cs, "pick_threshold", lambda *args: pytest.fail("apply must not tune")
    )
    applied = tmp_path / "apply"
    args = [
        "apply",
        "--params",
        str(fitted / "params.json"),
        "--a",
        str(a),
        "--a-model-sha",
        SHA_A,
        "--output-dir",
        str(applied),
    ]
    if mode == "mean":
        args += ["--b", str(b), "--b-model-sha", SHA_B]
    assert run.main(args) == 0
    score = cm.read_scores(applied / "scores.csv")["new"]["score"]
    expected = (
        0.6
        if mode == "mean"
        else float(
            run.cs.sigmoid(params["a"] * run.cs.logit(np.array([0.8])) + params["b"])[0]
        )
    )
    assert score == pytest.approx(expected)
    assert json.loads((applied / "params.json").read_text()) == params


def test_mean_joins_by_id_and_is_symmetric(inputs, tmp_path):
    output = tmp_path / "mean"
    assert run.main(fit_args(inputs, output, "mean")) == 0
    a, b, actual = [cm.read_scores(p) for p in (*inputs[1:], output / "scores.csv")]
    for sid in a:
        assert actual[sid]["score"] == pytest.approx(
            (a[sid]["score"] + b[sid]["score"]) / 2
        )
    params = json.loads((output / "params.json").read_text())
    assert run.transform(b, a, params) == actual


def test_separate_e0_reference_and_prelocked_fpr(inputs, tmp_path):
    e0 = tmp_path / "e0.csv"
    e0.write_text(inputs[1].read_text().replace(",0.1,", ",0.9,", 1))
    output = tmp_path / "different-reference"
    args = fit_args(inputs, output)
    args[args.index("--e0") + 1] = str(e0)
    args[args.index("--target-fpr") + 1] = "0.05"
    assert run.main(args) == 0
    report = json.loads((output / "report.json").read_text())
    reference = report["fixed_thresholds_E0_vs_result"]["slices"]["__all__"]
    assert reference["A"]["fpr_high"] == pytest.approx(0.05)
    assert reference["B"]["fpr_high"] == 0
    assert report["input_sha256"]["e0"] == cm.sha256_file(e0)


def test_unlocked_target_mismatch_rejected_before_fitting(
    inputs, tmp_path, monkeypatch
):
    args = fit_args(inputs, tmp_path / "wrong-target")
    args[args.index("--target-fpr") + 1] = "0.1"
    monkeypatch.setattr(
        run.cs, "calibrate", lambda *a: pytest.fail("must reject before fit")
    )
    assert run.main(args) == 2


@pytest.mark.parametrize(
    "corruption", ["test", "train", "source", "group", "missing", "nan"]
)
def test_refuse_untrusted_validation_inputs(inputs, tmp_path, corruption):
    labels, a, _ = inputs
    if corruption in ("test", "train"):
        labels.write_text(labels.read_text().replace(",val,", f",{corruption},", 1))
    elif corruption in ("source", "group"):
        a.write_text(
            a.read_text().replace(
                "genimage_real" if corruption == "source" else "g0", "wrong", 1
            )
        )
    elif corruption == "missing":
        a.write_text("\n".join(a.read_text().splitlines()[:-1]) + "\n")
    else:
        a.write_text(a.read_text().replace(",0.1,", ",nan,", 1))
    output = tmp_path / "bad"
    assert run.main(fit_args(inputs, output)) == 2
    assert json.loads((output / "report.json").read_text())["status"] == "failed"
    assert not (output / "scores.csv").exists()


@pytest.mark.parametrize(
    "column,replacement",
    [("score", "0.4"), ("label", "1"), ("group_id", "wrong"), ("source", "wrong")],
)
def test_mismatched_pair_rejected_except_scores(inputs, tmp_path, column, replacement):
    b = inputs[2]
    with b.open(newline="") as stream:
        reader = csv.DictReader(stream)
        names = reader.fieldnames
        rows = list(reader)
    rows[-1][column] = replacement
    with b.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)
    assert run.main(fit_args(inputs, tmp_path / "pair", "mean")) == (
        0 if column == "score" else 2
    )


def test_existing_output_rejected_before_reading(inputs, tmp_path, monkeypatch):
    output = tmp_path / "old"
    output.mkdir()
    (output / "keep").write_text("evidence")
    monkeypatch.setattr(
        cm, "read_scores", lambda *args: pytest.fail("must reject before reading")
    )
    assert run.main(fit_args(inputs, output)) == 2
    assert (output / "keep").read_text() == "evidence"


def test_input_changed_during_fit_preserves_failure(inputs, tmp_path, monkeypatch):
    original = run.transform

    def changing(*args):
        inputs[1].write_text(inputs[1].read_text() + "\n")
        return original(*args)

    monkeypatch.setattr(run, "transform", changing)
    output = tmp_path / "changed"
    assert run.main(fit_args(inputs, output)) == 2
    assert json.loads((output / "report.json").read_text())["status"] == "failed"
    assert not (output / "scores.csv").exists()


@pytest.mark.parametrize(
    "change", ["hash", "nan", "negative", "weight", "threshold", "schema"]
)
def test_frozen_parameters_reject_corruption(tmp_path, change):
    params = {
        "schema_version": 1,
        "model_sha256": [SHA_A],
        "mode": "platt",
        "a": 1.0,
        "b": 0.0,
        "threshold": 0.8,
        "target_fpr": 0.1,
    }
    if change == "hash":
        params["model_sha256"] = [SHA_B]
    if change == "nan":
        params["b"] = float("nan")
    if change == "negative":
        params["a"] = -1
    if change == "threshold":
        params["threshold"] = 2.0
    if change == "schema":
        params["schema_version"] = 2
    hashes = [SHA_A]
    if change == "weight":
        params.update(mode="mean", model_sha256=[SHA_A, SHA_B], weights=[0.4, 0.6])
        hashes.append(SHA_B)
    path = tmp_path / "params.json"
    path.write_text(json.dumps(params))
    with pytest.raises(ValueError):
        run.read_params(path, hashes)
