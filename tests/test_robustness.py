"""ADV-07: robustness manifest (variants, external cohorts) and the --robustness runner.

Synthetic images and a fake scorer that runs the real normalizer; no CLIP download.
Expected transforms are written from the ADV-07 spec (#51), not read from the module.
"""

import csv
import io
import json

import joblib
import numpy as np
import pytest
from PIL import Image, ImageEnhance
from sklearn.linear_model import LogisticRegression

from models.clip_input import FEATURE_DIM, feature_contract
from models.extract_features import sha256_file
from models.normalize import NORMALIZATION_VERSION, normalize_image
from scripts import evaluate as ev
from scripts import robustness_manifest as rm

THRESHOLDS = {"binary": 0.5, "low": 0.3, "high": 0.7}
SPEC_TRANSFORMS = {
    "jpeg90": {"kind": "jpeg", "params": {"quality": 90}},
    "jpeg70": {"kind": "jpeg", "params": {"quality": 70}},
    "jpeg50": {"kind": "jpeg", "params": {"quality": 50}},
    "rotate": {"kind": "rotate", "params": {"degrees": 90}},
    "crop": {"kind": "center_crop", "params": {"keep": 0.8, "min_side": 256}},
    "downscale": {"kind": "downscale", "params": {"scale": 0.5, "min_side": 256}},
    "brightness": {"kind": "brightness", "params": {"factor": 1.3}},
}
PARENT_ROWS = [
    {
        "path": "parents/real.png",
        "label": "0",
        "source": "genimage_real",
        "group_id": "g-real",
    },
    {
        "path": "parents/ai.jpg",
        "label": "1",
        "source": "genimage_sd15",
        "group_id": "g-ai",
    },
]


def save(path, size=(320, 300), color=(120, 80, 40), fmt="PNG", **kwargs):
    noise = Image.effect_noise(size, 30).convert("RGB")
    Image.blend(Image.new("RGB", size, color), noise, 0.3).save(path, fmt, **kwargs)
    return path


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def pixels(path):
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


@pytest.fixture
def parents(tmp_path):
    """Two parents (real 320x300 PNG, AI 1024x768 JPEG) and their parents CSV."""
    folder = tmp_path / "parents"
    folder.mkdir()
    save(folder / "real.png")
    save(folder / "ai.jpg", size=(1024, 768), color=(30, 160, 200), fmt="JPEG")
    return write_csv(tmp_path / "parents.csv", PARENT_ROWS)


def build_variants(parents_csv, output):
    rows = rm.make_variants(parents_csv, output)
    rm.write_manifest(rows, output)
    return rows


def test_each_parent_gets_the_spec_variants_with_its_own_lineage(parents, tmp_path):
    output = tmp_path / "out" / "variants.jsonl"
    rows = build_variants(parents, output)
    assert len(rows) == len(PARENT_ROWS) * (1 + len(SPEC_TRANSFORMS))
    assert len({row["sample_id"] for row in rows}) == len(rows)
    roots = {row["sample_id"]: row for row in rows if row["parent_id"] is None}
    declared = {row["source"]: row for row in PARENT_ROWS}
    for root in roots.values():
        csv_row = declared[root["source"]]
        assert root["cohort"] == "parents" and root["transform"]["kind"] == "original"
        assert (root["label"], root["group_id"]) == (
            int(csv_row["label"]),
            csv_row["group_id"],
        )
    for row in rows:
        assert set(row) == ev.MANIFEST_FIELDS and row["split"] == "test"
        assert sha256_file(output.parent / row["path"]) == row["sha256"]
        if row["parent_id"]:
            parent = roots[row["parent_id"]]
            assert [row[k] for k in ("group_id", "label", "source")] == [
                parent[k] for k in ("group_id", "label", "source")
            ]
            assert row["transform"] == SPEC_TRANSFORMS[row["cohort"]]
    assert {r["cohort"] for r in rows} == {"parents", *SPEC_TRANSFORMS}
    assert read_jsonl(output) == [
        json.loads(json.dumps(r, sort_keys=True)) for r in rows
    ]


@pytest.mark.parametrize("quality", [90, 70, 50])
def test_jpeg_variant_is_encoded_at_the_spec_quality(parents, tmp_path, quality):
    output = tmp_path / "variants.jsonl"
    rows = build_variants(parents, output)
    for source in ("genimage_real", "genimage_sd15"):
        root = next(r for r in rows if r["source"] == source and not r["parent_id"])
        child = next(
            r for r in rows if r["source"] == source and r["cohort"] == f"jpeg{quality}"
        )
        reference = io.BytesIO()
        Image.fromarray(pixels(output.parent / root["path"])).save(
            reference, "JPEG", quality=quality
        )
        with Image.open(output.parent / child["path"]) as image:
            assert image.format == "JPEG"
            # Quantization tables identify the quality the file was really saved with.
            assert image.quantization == Image.open(reference).quantization


def test_geometry_and_brightness_match_the_spec_exactly(parents, tmp_path):
    output = tmp_path / "variants.jsonl"
    rows = build_variants(parents, output)
    path = {(r["source"], r["cohort"]): output.parent / r["path"] for r in rows}
    for source, (width, height) in (
        ("genimage_sd15", (1024, 768)),
        ("genimage_real", (320, 300)),
    ):
        base = Image.fromarray(pixels(path[(source, "parents")]))
        keep = max(
            0.8, 256 / min(width, height)
        )  # never below the 256 px serving minimum
        crop_w, crop_h = round(width * keep), round(height * keep)
        left, top = (width - crop_w) // 2, (height - crop_h) // 2
        scale = max(0.5, 256 / min(width, height))
        expected = {
            "rotate": base.transpose(
                Image.Transpose.ROTATE_90
            ),  # 90° counter-clockwise
            "crop": base.crop((left, top, left + crop_w, top + crop_h)),
            "downscale": base.resize(
                (round(width * scale), round(height * scale)), Image.Resampling.BICUBIC
            ),
            "brightness": ImageEnhance.Brightness(base).enhance(1.3),
        }
        for cohort, image in expected.items():
            with Image.open(path[(source, cohort)]) as saved:
                assert saved.format == "PNG", cohort
            assert np.array_equal(pixels(path[(source, cohort)]), np.asarray(image)), (
                cohort
            )
    with Image.open(path[("genimage_sd15", "crop")]) as image:
        assert image.size == (819, 614)
    with Image.open(path[("genimage_sd15", "downscale")]) as image:
        assert image.size == (512, 384)


def test_variants_are_reproducible(parents, tmp_path):
    first = build_variants(parents, tmp_path / "a" / "variants.jsonl")
    second = build_variants(parents, tmp_path / "b" / "variants.jsonl")
    assert [r["sha256"] for r in first] == [r["sha256"] for r in second]


def test_exif_orientation_is_applied_before_variants(tmp_path):
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 on display
    save(tmp_path / "p.jpg", size=(400, 300), fmt="JPEG", exif=exif.tobytes())
    parents_csv = write_csv(
        tmp_path / "p.csv",
        [{"path": "p.jpg", "label": "0", "source": "phone_x", "group_id": "g"}],
    )
    rows = build_variants(parents_csv, tmp_path / "v.jsonl")
    jpeg90 = next(r for r in rows if r["cohort"] == "jpeg90")
    with Image.open(tmp_path / jpeg90["path"]) as img:
        assert img.size == (300, 400)


def test_duplicate_parent_bytes_must_share_a_group(parents, tmp_path):
    same_group = write_csv(tmp_path / "dup.csv", [*PARENT_ROWS, PARENT_ROWS[0]])
    assert len(rm.make_variants(same_group, tmp_path / "one" / "v.jsonl")) == 2 * 8
    other = write_csv(
        tmp_path / "bad.csv", [*PARENT_ROWS, {**PARENT_ROWS[0], "group_id": "x"}]
    )
    with pytest.raises(ValueError, match="another group"):
        rm.make_variants(other, tmp_path / "two" / "v.jsonl")


def test_every_bad_parent_is_listed_before_anything_is_written(parents, tmp_path):
    save(tmp_path / "parents" / "small.png", size=(255, 400))
    (tmp_path / "parents" / "broken.jpg").write_bytes(b"not an image")
    rows = [
        *PARENT_ROWS,
        {"path": "parents/small.png", "label": "0", "source": "s", "group_id": "g1"},
        {"path": "parents/broken.jpg", "label": "0", "source": "s", "group_id": "g2"},
        {"path": "parents/missing.png", "label": "0", "source": "s", "group_id": "g3"},
        {"path": "parents/real.png", "label": "2", "source": "s", "group_id": "g4"},
    ]
    output = tmp_path / "v.jsonl"
    with pytest.raises(ValueError) as info:
        rm.make_variants(write_csv(tmp_path / "bad.csv", rows), output)
    message = str(info.value)
    assert "bad.csv:4: short side 255 px < 256 px" in message
    assert "bad.csv:5: cannot be decoded" in message
    assert "bad.csv:6: file not found" in message
    assert "bad.csv:7: need path, label 0/1" in message
    assert not (tmp_path / "v").exists()


def test_failure_while_writing_leaves_no_variant_folder(parents, tmp_path, monkeypatch):
    def fail(image):
        raise OSError("disk full")

    monkeypatch.setitem(
        rm.VARIANTS, "brightness", (SPEC_TRANSFORMS["brightness"], fail)
    )
    with pytest.raises(OSError, match="disk full"):
        rm.make_variants(parents, tmp_path / "v.jsonl")
    assert not (tmp_path / "v").exists()


def test_variants_cli_reports_errors_with_exit_code_2(parents, tmp_path, capsys):
    output = tmp_path / "v.jsonl"
    rm.main(["variants", "--parents", str(parents), "--output", str(output)])
    assert len(read_jsonl(output)) == 16
    for argv in (
        ["variants", "--parents", str(parents), "--output", str(output)],
        ["variants", "--parents", str(parents), "--output", str(tmp_path / "v")],
        [
            "variants",
            "--parents",
            str(tmp_path / "none.csv"),
            "--output",
            str(tmp_path / "n.jsonl"),
        ],
    ):
        with pytest.raises(SystemExit) as exit_info:
            rm.main(argv)
        assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "already exists" in err and "Not found" in err and "Traceback" not in err


def cohort_folder(tmp_path, name, files):
    """files: {file name: sources.csv row without 'file'}; images are 300x300."""
    folder = tmp_path / name
    folder.mkdir(parents=True)
    for index, file in enumerate(files):
        save(folder / file, size=(300, 300), color=(20 * index, 90, 150))
    write_csv(
        folder / "sources.csv", [{"file": f, **info} for f, info in files.items()]
    )
    return folder


def test_phone_cohort_rows_are_independent_roots(tmp_path):
    folder = cohort_folder(
        tmp_path,
        "phone",
        {
            "a.png": {"source": "iPhone 13", "label": "0", "parent_file": ""},
            "b.png": {"source": "Galaxy S21", "label": "0", "parent_file": ""},
        },
    )
    rows = rm.make_cohort("phone", folder, tmp_path / "phone.jsonl")
    assert [r["source"] for r in rows] == ["iPhone 13", "Galaxy S21"]
    for row in rows:
        assert row["cohort"] == "phone" and row["label"] == 0
        assert row["parent_id"] is None and row["group_id"] == row["sample_id"]
        assert row["transform"] == {"kind": "original", "params": {}}


@pytest.mark.parametrize(
    ("name", "info", "message"),
    [
        ("phone", {"source": "iPhone", "label": "1"}, "label 0"),
        ("ai_new", {"source": "Midjourney v7", "label": "0"}, "label 1"),
        ("ai_new", {"source": "", "label": "1"}, "need source"),
    ],
)
def test_cohort_rejects_wrong_label_or_missing_source(tmp_path, name, info, message):
    folder = cohort_folder(tmp_path, name, {"a.png": info})
    with pytest.raises(ValueError, match=message):
        rm.make_cohort(name, folder, tmp_path / "c.jsonl")


def test_cohort_lists_every_problem(tmp_path):
    folder = cohort_folder(
        tmp_path,
        "phone",
        {
            "a.jpg": {"source": "iPhone", "label": "0"},
            "b.png": {"source": "iPhone", "label": "0"},
            "c.png": {"source": "iPhone", "label": "0"},
        },
    )
    exif = Image.Exif()
    exif.get_ifd(rm.GPS_IFD)[2] = (10.0, 45.0, 0.0)
    save(folder / "a.jpg", size=(300, 300), fmt="JPEG", exif=exif.tobytes())
    (folder / "b.png").write_bytes(b"broken")
    (folder / "c.png").unlink()
    save(folder / "extra.png")
    with pytest.raises(ValueError) as info:
        rm.make_cohort("phone", folder, tmp_path / "c.jsonl")
    message = str(info.value)
    assert "a.jpg: has GPS" in message
    assert "b.png: cannot be decoded" in message
    assert "c.png: listed in sources.csv but not in folder" in message
    assert "extra.png: need source" in message


def test_cohort_without_sources_csv_is_a_clear_error(tmp_path):
    folder = tmp_path / "phone"
    folder.mkdir()
    save(folder / "a.png")
    with pytest.raises(ValueError, match="Not found: .*sources.csv"):
        rm.make_cohort("phone", folder, tmp_path / "c.jsonl")


def test_zalo_copy_keeps_the_phone_parent_group(tmp_path):
    phone = cohort_folder(
        tmp_path, "phone", {"p.png": {"source": "iPhone", "label": "0"}}
    )
    phone_manifest = tmp_path / "phone.jsonl"
    rm.write_manifest(rm.make_cohort("phone", phone, phone_manifest), phone_manifest)
    zalo = cohort_folder(
        tmp_path,
        "zalo",
        {
            "z.png": {"source": "Zalo", "label": "0", "parent_file": "p.png"},
            "y.png": {"source": "Zalo", "label": "0", "parent_file": ""},
        },
    )
    rows = {
        r["path"]: r
        for r in rm.make_cohort("zalo", zalo, tmp_path / "z.jsonl", phone_manifest)
    }
    parent = read_jsonl(phone_manifest)[0]
    assert rows["zalo/z.png"]["parent_id"] == parent["sample_id"]
    assert rows["zalo/z.png"]["group_id"] == parent["group_id"]
    assert rows["zalo/z.png"]["source"] == "iPhone"  # camera, not the app
    assert {r["transform"]["kind"] for r in rows.values()} == {"zalo"}
    assert rows["zalo/y.png"]["parent_id"] is None
    missing = cohort_folder(
        tmp_path / "x",
        "zalo",
        {"z.png": {"source": "Zalo", "label": "0", "parent_file": "nope.png"}},
    )
    with pytest.raises(ValueError, match="parent_file not found"):
        rm.make_cohort("zalo", missing, tmp_path / "x.jsonl", phone_manifest)


class FakeScorer:
    """Runs the real normalizer (so too-small images fail like serving); score = brightness."""

    def __call__(self, image):
        values = np.asarray(normalize_image(image).image, dtype=np.float32)
        return float(values.mean() / 255)


def write_model(tmp_path, thresholds):
    rng = np.random.default_rng(0)
    probe = LogisticRegression().fit(rng.normal(size=(20, FEATURE_DIM)), [0, 1] * 10)
    model = tmp_path / "model.joblib"
    metadata = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "dataset": "genimage",
    }
    joblib.dump({"probe": probe, "metadata": metadata, "thresholds": thresholds}, model)
    model.with_suffix(".joblib.sha256").write_text(sha256_file(model) + "\n")
    model_manifest = tmp_path / "model_manifest.json"
    model_manifest.write_text(
        json.dumps(
            {
                "model_sha256": sha256_file(model),
                "clip_model_id": feature_contract()["clip_model_id"],
                "clip_revision": feature_contract()["clip_revision"],
                "normalization_version": NORMALIZATION_VERSION,
                "thresholds": thresholds,
            }
        )
    )
    return model, model_manifest


def write_protocol(locked, **overrides):
    """A locked ADV-08 protocol naming exactly the fixture's inputs."""
    rows = read_jsonl(locked["manifest"])
    protocol = {
        "schema_version": 1,
        "status": "locked",
        "manifest_lock_ref": "test lock",
        "split_review_ref": "test review",
        "profile": {
            "clip_model_id": feature_contract()["clip_model_id"],
            "clip_revision": feature_contract()["clip_revision"],
            "normalization_version": NORMALIZATION_VERSION,
        },
        "thresholds": json.loads(locked["model_manifest"].read_text())["thresholds"],
        "artifacts": {
            name: {"path": locked[name].name, "sha256": sha256_file(locked[name])}
            for name in ("model", "model_manifest", "manifest")
        },
        "cohorts": [
            {
                "name": c,
                "status": "present",
                "transform": next(r["transform"] for r in rows if r["cohort"] == c),
            }
            for c in sorted({r["cohort"] for r in rows})
        ],
        **overrides,
    }
    locked["protocol"].write_text(json.dumps(protocol))
    return protocol


@pytest.fixture
def locked(tmp_path, parents):
    """Variant manifest plus a too-small phone image and a broken Zalo file, a valid
    model with its manifest, and a locked protocol naming all of them."""
    manifest = tmp_path / "run" / "manifest.jsonl"
    rows = rm.make_variants(parents, manifest)
    small = save(tmp_path / "run" / "small.png", size=(200, 200))
    broken = tmp_path / "run" / "broken.jpg"
    broken.write_bytes(b"not an image")
    for path, cohort, transform in (
        (small, "phone", rm.ROOT_TRANSFORM),
        (broken, "zalo", rm.ZALO_TRANSFORM),
    ):
        rows.append(
            rm._row(
                f"{cohort}-x",
                path.name,
                sha256_file(path),
                cohort,
                None,
                transform,
                label=0,
                source="test",
                group_id=f"{cohort}-x",
            )
        )
    rm.write_manifest(rows, manifest)
    model, model_manifest = write_model(tmp_path, THRESHOLDS)
    files = {
        "manifest": manifest,
        "model": model,
        "model_manifest": model_manifest,
        "protocol": tmp_path / "protocol.json",
        "rows": rows,
    }
    write_protocol(files)
    return files


def run(locked, output, scorer=None):
    return ev.run_robustness(
        locked["manifest"],
        locked["model"],
        locked["model_manifest"],
        locked["protocol"],
        output,
        lambda: scorer or FakeScorer(),
    )


def expected_verdict(score, low, high):
    return (
        "likely_real" if score < low else "likely_ai" if score > high else "uncertain"
    )


def read_predictions(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames, list(reader)


def test_runner_writes_one_prediction_per_image_like_the_api(locked, tmp_path):
    output = tmp_path / "out" / "predictions.csv"
    assert run(locked, output) == {"ok": 16, "error": 2}
    assert not output.with_name(output.name + ".partial").exists()
    fields, predictions = read_predictions(output)
    assert fields == ev.PREDICTION_FIELDS
    assert [p["sample_id"] for p in predictions] == [
        r["sample_id"] for r in locked["rows"]
    ]
    hashes = [sha256_file(locked[k]) for k in ("model", "manifest", "protocol")]
    for prediction, row in zip(predictions, locked["rows"]):
        assert [
            prediction[f"{k}_sha256"] for k in ("model", "manifest", "protocol")
        ] == hashes
        assert prediction["parent_id"] == (row["parent_id"] or "")
        if prediction["status"] == "ok":
            score = float(prediction["score"])
            assert prediction["verdict"] == expected_verdict(score, 0.3, 0.7)
    errors = {p["sample_id"]: p for p in predictions if p["status"] == "error"}
    assert errors["phone-x"]["error_code"] == "IMAGE_TOO_SMALL"
    assert errors["zalo-x"]["error_code"] == "INVALID_IMAGE"
    assert errors["zalo-x"]["score"] == errors["zalo-x"]["verdict"] == ""


def test_verdicts_follow_the_model_thresholds(locked, tmp_path):
    thresholds = {"binary": 0.5, "low": 0.45, "high": 0.55}
    other = tmp_path / "other"
    other.mkdir()
    locked["model"], locked["model_manifest"] = write_model(other, thresholds)
    write_protocol(locked)
    output = tmp_path / "p.csv"
    run(locked, output)
    scored = [p for p in read_predictions(output)[1] if p["status"] == "ok"]
    assert {p["verdict"] for p in scored} - {
        "uncertain"
    }  # narrower band decides more images
    for prediction in scored:
        assert prediction["verdict"] == expected_verdict(
            float(prediction["score"]), 0.45, 0.55
        )


def test_scorer_failure_is_recorded_as_model_error(locked, tmp_path):
    def broken(image):
        raise RuntimeError("boom")

    output = tmp_path / "p.csv"
    assert run(locked, output, broken)["error"] == 18
    codes = {row["error_code"] for row in read_predictions(output)[1]}
    assert codes == {"MODEL_ERROR", "INVALID_IMAGE"}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "protocol not found"),
        ("", "not valid JSON"),
        ("rác không phải JSON", "not valid JSON"),
        ("[]", "must be a JSON object"),
    ],
)
def test_unreadable_protocol_is_refused_before_loading_clip(
    locked, tmp_path, content, message
):
    if content is None:
        locked["protocol"].unlink()
    else:
        locked["protocol"].write_text(content, encoding="utf-8")
    loaded = []
    with pytest.raises(ev.RobustnessInputError, match=message):
        ev.run_robustness(
            locked["manifest"],
            locked["model"],
            locked["model_manifest"],
            locked["protocol"],
            tmp_path / "p.csv",
            lambda: loaded.append(1),
        )
    assert loaded == []


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"status": "draft"}, "status must be locked"),
        ({"schema_version": 2}, "schema_version must be 1"),
        ({"split_review_ref": ""}, "split_review_ref are required"),
        ({"thresholds": {"binary": 0.5, "low": 0.2, "high": 0.8}}, "thresholds differ"),
        ({"profile": {}}, "profile differs"),
        ({"cohorts": []}, "cohorts not registered"),
    ],
)
def test_protocol_must_be_locked_for_exactly_these_inputs(
    locked, tmp_path, overrides, message
):
    write_protocol(locked, **overrides)
    with pytest.raises(ev.RobustnessInputError, match=message):
        run(locked, tmp_path / "p.csv")
    assert not locked["protocol"].with_name("protocol.json.used.json").exists()


@pytest.mark.parametrize("artifact", ["model", "model_manifest", "manifest"])
def test_protocol_must_name_the_files_given(locked, tmp_path, artifact):
    protocol = write_protocol(locked)
    protocol["artifacts"][artifact]["sha256"] = "0" * 64
    locked["protocol"].write_text(json.dumps(protocol))
    with pytest.raises(ev.RobustnessInputError, match=f"artifacts.{artifact}.sha256"):
        run(locked, tmp_path / "p.csv")


def test_a_locked_protocol_scores_only_once(locked, tmp_path):
    run(locked, tmp_path / "first.csv")
    used = json.loads(
        locked["protocol"].with_name("protocol.json.used.json").read_text()
    )
    assert used["protocol_sha256"] == sha256_file(locked["protocol"])
    with pytest.raises(ev.RobustnessInputError, match="already used"):
        run(locked, tmp_path / "second.csv")
    assert not (tmp_path / "second.csv").exists()


def test_runner_refuses_a_model_manifest_for_another_model(locked, tmp_path):
    data = json.loads(locked["model_manifest"].read_text())
    locked["model_manifest"].write_text(json.dumps({**data, "model_sha256": "0" * 64}))
    write_protocol(locked)
    with pytest.raises(ev.RobustnessInputError, match="model_sha256"):
        run(locked, tmp_path / "p.csv")


def test_runner_refuses_a_changed_image_before_spending_the_protocol(locked, tmp_path):
    """Hash all images before CLIP loads and before .used.json: one bad byte must not burn the protocol."""
    first = locked["manifest"].parent / locked["rows"][0]["path"]
    first.write_bytes(first.read_bytes() + b"\0")
    output, loaded = tmp_path / "p.csv", []
    with pytest.raises(ev.RobustnessInputError, match="changed since listing"):
        ev.run_robustness(
            locked["manifest"],
            locked["model"],
            locked["model_manifest"],
            locked["protocol"],
            output,
            lambda: loaded.append(1),
        )
    assert loaded == []
    assert not output.exists()
    assert not output.with_name("p.csv.partial").exists()
    assert not locked["protocol"].with_name("protocol.json.used.json").exists()


def test_runner_refuses_a_missing_image_before_spending_the_protocol(locked, tmp_path):
    (locked["manifest"].parent / locked["rows"][0]["path"]).unlink()
    with pytest.raises(ev.RobustnessInputError, match="not readable"):
        run(locked, tmp_path / "p.csv")
    assert not locked["protocol"].with_name("protocol.json.used.json").exists()


@pytest.mark.parametrize("existing", ["p.csv", "p.csv.partial", "p.csv.run.json"])
def test_runner_never_overwrites_outputs(locked, tmp_path, existing):
    (tmp_path / existing).write_text("old")
    with pytest.raises(FileExistsError, match=existing.replace(".", r"\.")):
        run(locked, tmp_path / "p.csv")
    assert (tmp_path / existing).read_text() == "old"


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda rows: rows + [rows[0]], "duplicate sample_id"),
        (lambda rows: [{**rows[0], "label": True}], "integer 0 or 1"),
        (lambda rows: [{**rows[0], "split": "val"}], "split must be test"),
        (
            lambda rows: [{k: v for k, v in rows[0].items() if k != "group_id"}],
            "need fields",
        ),
        (
            lambda rows: [
                rows[0],
                {**rows[0], "sample_id": "other", "group_id": "other"},
            ],
            "same image bytes in another group",
        ),
    ],
)
def test_manifest_rows_are_checked(locked, change, message):
    rows = change(read_jsonl(locked["manifest"]))
    locked["manifest"].write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    with pytest.raises(ev.RobustnessInputError, match=message):
        ev.read_robustness_manifest(locked["manifest"])


def test_cli_end_to_end_and_exit_codes(locked, tmp_path, monkeypatch, capsys):
    loads = []
    monkeypatch.setattr(
        ev, "load_scorer", lambda path: loads.append(path) or FakeScorer()
    )
    output = tmp_path / "cli" / "predictions.csv"
    argv = [
        "--robustness",
        "--manifest",
        str(locked["manifest"]),
        "--model",
        str(locked["model"]),
        "--model-manifest",
        str(locked["model_manifest"]),
        "--protocol",
        str(locked["protocol"]),
        "--output",
        str(output),
    ]
    ev.main(argv)
    assert loads == [locked["model"]]
    assert len(read_predictions(output)[1]) == 18
    run_log = json.loads(output.with_name("predictions.csv.run.json").read_text())
    assert run_log["counts"] == {"ok": 16, "error": 2} and "git_commit" in run_log
    with pytest.raises(SystemExit) as exit_info:  # the protocol is now used
        ev.main([*argv[:-1], str(tmp_path / "again.csv")])
    assert exit_info.value.code == 2 and loads == [locked["model"]]
    with pytest.raises(SystemExit) as exit_info:
        ev.main(["--robustness", "--output", str(tmp_path / "x.csv")])
    assert exit_info.value.code == 2
    assert "Traceback" not in capsys.readouterr().err
