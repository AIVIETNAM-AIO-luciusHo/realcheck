"""ADV-07: robustness manifest (variants, external cohorts) and the --robustness runner.

Synthetic images and a fake scorer that runs the real normalizer; no CLIP download.
"""

import csv
import json

import joblib
import numpy as np
import pytest
from PIL import Image
from sklearn.linear_model import LogisticRegression

from models.clip_input import FEATURE_DIM, feature_contract
from models.extract_features import sha256_file
from models.normalize import MIN_SIDE, NORMALIZATION_VERSION, normalize_image
from scripts import evaluate as ev
from scripts import robustness_manifest as rm

THRESHOLDS = {"binary": 0.5, "low": 0.3, "high": 0.7}
VARIANT_COHORTS = [
    "jpeg90",
    "jpeg70",
    "jpeg50",
    "rotate",
    "crop",
    "downscale",
    "brightness",
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


@pytest.fixture
def parents(tmp_path):
    """Two parents (real 320x300, AI 1024x768) in their own folder with a parents CSV."""
    folder = tmp_path / "parents"
    folder.mkdir()
    save(folder / "real.png")
    save(folder / "ai.jpg", size=(1024, 768), color=(30, 160, 200), fmt="JPEG")
    return write_csv(
        tmp_path / "parents.csv",
        [
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
        ],
    )


def build_variants(parents_csv, output):
    rows = rm.make_variants(parents_csv, output)
    rm.write_manifest(rows, output)
    return rows


def test_each_parent_gets_all_variants_with_inherited_lineage(parents, tmp_path):
    output = tmp_path / "out" / "variants.jsonl"
    rows = build_variants(parents, output)
    assert len(rows) == 2 * (1 + len(VARIANT_COHORTS))
    assert len({row["sample_id"] for row in rows}) == len(rows)
    roots = {row["sample_id"]: row for row in rows if row["parent_id"] is None}
    assert {row["cohort"] for row in roots.values()} == {"parents"}
    for row in rows:
        assert set(row) == ev.MANIFEST_FIELDS and row["split"] == "test"
        assert sha256_file(output.parent / row["path"]) == row["sha256"]
        if row["parent_id"]:
            parent = roots[row["parent_id"]]
            assert (row["group_id"], row["label"], row["source"]) == (
                parent["group_id"],
                parent["label"],
                parent["source"],
            )
            assert row["transform"] == rm.VARIANTS[row["cohort"]][0]
    assert read_jsonl(output) == [
        json.loads(json.dumps(row, sort_keys=True)) for row in rows
    ]


def test_transforms_change_only_what_their_cohort_names(parents, tmp_path):
    output = tmp_path / "variants.jsonl"
    rows = build_variants(parents, output)
    by = {(row["source"], row["cohort"]): output.parent / row["path"] for row in rows}

    def image(source, cohort):
        with Image.open(by[(source, cohort)]) as img:
            img.load()
            return img

    sizes = {q: by[("genimage_sd15", f"jpeg{q}")].stat().st_size for q in (90, 70, 50)}
    assert sizes[90] > sizes[70] > sizes[50]
    assert image("genimage_sd15", "jpeg50").format == "JPEG"
    assert image("genimage_sd15", "rotate").size == (768, 1024)
    assert image("genimage_sd15", "crop").size == (819, 614)
    assert image("genimage_sd15", "downscale").size == (512, 384)
    # A 300 px short side only shrinks to the serving minimum, never below it.
    assert min(image("genimage_real", "crop").size) == MIN_SIDE
    assert min(image("genimage_real", "downscale").size) == MIN_SIDE
    bright, base = (
        image("genimage_real", "brightness"),
        image("genimage_real", "rotate"),
    )
    assert np.asarray(bright).mean() > np.asarray(base).mean()
    assert image("genimage_real", "brightness").format == "PNG"


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


def test_duplicate_parent_bytes(parents, tmp_path):
    rows = list(csv.DictReader(parents.open(encoding="utf-8")))
    same_group = write_csv(tmp_path / "dup.csv", [*rows, rows[0]])
    assert len(rm.make_variants(same_group, tmp_path / "one" / "v.jsonl")) == 2 * 8
    other_group = write_csv(
        tmp_path / "bad.csv", [*rows, {**rows[0], "group_id": "other"}]
    )
    with pytest.raises(ValueError, match="another group"):
        rm.make_variants(other_group, tmp_path / "two" / "v.jsonl")


def test_parent_rows_need_label_source_and_group(tmp_path):
    save(tmp_path / "p.png")
    bad = write_csv(
        tmp_path / "p.csv",
        [{"path": "p.png", "label": "2", "source": "x", "group_id": "g"}],
    )
    with pytest.raises(ValueError, match="label 0/1"):
        rm.make_variants(bad, tmp_path / "v.jsonl")


def test_main_refuses_existing_manifest_or_image_folder(parents, tmp_path):
    output = tmp_path / "v.jsonl"
    rm.main(["variants", "--parents", str(parents), "--output", str(output)])
    with pytest.raises(SystemExit):
        rm.main(["variants", "--parents", str(parents), "--output", str(output)])
    output.unlink()
    with pytest.raises(FileExistsError):
        rm.make_variants(parents, output)


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


def test_cohort_refuses_gps_and_unlisted_files(tmp_path):
    folder = cohort_folder(
        tmp_path, "phone", {"a.jpg": {"source": "iPhone", "label": "0"}}
    )
    exif = Image.Exif()
    exif.get_ifd(rm.GPS_IFD)[2] = (10.0, 45.0, 0.0)
    save(folder / "a.jpg", size=(300, 300), fmt="JPEG", exif=exif.tobytes())
    save(folder / "extra.png")
    with pytest.raises(ValueError) as info:
        rm.make_cohort("phone", folder, tmp_path / "c.jsonl")
    assert "a.jpg: has GPS" in str(info.value)
    assert "extra.png: need source" in str(info.value)


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
        pixels = np.asarray(normalize_image(image).image, dtype=np.float32)
        return float(pixels.mean() / 255)


@pytest.fixture
def locked(tmp_path, parents):
    """Variant manifest plus a small/broken extra row, a valid model bundle and manifests."""
    manifest = tmp_path / "run" / "manifest.jsonl"
    rows = rm.make_variants(parents, manifest)
    small = save(tmp_path / "run" / "small.png", size=(200, 200))
    broken = tmp_path / "run" / "broken.jpg"
    broken.write_bytes(b"not an image")
    for path, cohort in ((small, "phone"), (broken, "zalo")):
        digest = sha256_file(path)
        rows.append(
            rm._row(
                f"{cohort}-x",
                path.name,
                digest,
                cohort,
                None,
                rm.ROOT_TRANSFORM,
                label=0,
                source="test",
                group_id=f"{cohort}-x",
            )
        )
    rm.write_manifest(rows, manifest)
    rng = np.random.default_rng(0)
    probe = LogisticRegression().fit(rng.normal(size=(20, FEATURE_DIM)), [0, 1] * 10)
    model = tmp_path / "model.joblib"
    metadata = {
        **feature_contract(),
        "norm_version": NORMALIZATION_VERSION,
        "dataset": "genimage",
    }
    joblib.dump({"probe": probe, "metadata": metadata, "thresholds": THRESHOLDS}, model)
    model.with_suffix(".joblib.sha256").write_text(sha256_file(model) + "\n")
    model_manifest = tmp_path / "model_manifest.json"
    model_manifest.write_text(
        json.dumps(
            {
                "model_sha256": sha256_file(model),
                "clip_model_id": feature_contract()["clip_model_id"],
                "clip_revision": feature_contract()["clip_revision"],
                "normalization_version": NORMALIZATION_VERSION,
                "thresholds": THRESHOLDS,
            }
        )
    )
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"status": "locked"}))
    return {
        "manifest": manifest,
        "model": model,
        "model_manifest": model_manifest,
        "protocol": protocol,
        "rows": rows,
    }


def run(locked, output, scorer=None):
    return ev.run_robustness(
        locked["manifest"],
        locked["model"],
        locked["model_manifest"],
        locked["protocol"],
        output,
        scorer or FakeScorer(),
    )


def test_runner_writes_one_prediction_per_image_like_the_api(locked, tmp_path):
    output = tmp_path / "out" / "predictions.csv"
    counts = run(locked, output)
    assert counts == {"ok": 16, "error": 2}
    assert not output.with_name(output.name + ".partial").exists()
    with output.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        predictions = list(reader)
    assert reader.fieldnames == ev.PREDICTION_FIELDS
    assert [p["sample_id"] for p in predictions] == [
        r["sample_id"] for r in locked["rows"]
    ]
    hashes = [sha256_file(locked[k]) for k in ("model", "manifest", "protocol")]
    for prediction, row in zip(predictions, locked["rows"]):
        assert [
            prediction[k]
            for k in ("model_sha256", "manifest_sha256", "protocol_sha256")
        ] == hashes
        assert prediction["parent_id"] == (row["parent_id"] or "")
        if prediction["status"] == "ok":
            score = float(prediction["score"])
            assert 0 <= score <= 1 and prediction["error_code"] == ""
            expected = (
                "likely_real"
                if score < 0.3
                else "likely_ai"
                if score > 0.7
                else "uncertain"
            )
            assert prediction["verdict"] == expected
    errors = {p["sample_id"]: p for p in predictions if p["status"] == "error"}
    assert errors["phone-x"]["error_code"] == "IMAGE_TOO_SMALL"
    assert errors["zalo-x"]["error_code"] == "INVALID_IMAGE"
    assert errors["zalo-x"]["score"] == errors["zalo-x"]["verdict"] == ""


def test_scorer_failure_is_recorded_as_model_error(locked, tmp_path):
    def broken(image):
        raise RuntimeError("boom")

    output = tmp_path / "p.csv"
    assert run(locked, output, broken)["error"] == 18
    with output.open(newline="", encoding="utf-8") as handle:
        codes = {row["error_code"] for row in csv.DictReader(handle)}
    assert codes == {"MODEL_ERROR", "INVALID_IMAGE"}


def test_runner_refuses_a_model_manifest_for_another_model(locked, tmp_path):
    data = json.loads(locked["model_manifest"].read_text())
    locked["model_manifest"].write_text(json.dumps({**data, "model_sha256": "0" * 64}))
    output = tmp_path / "p.csv"
    with pytest.raises(ValueError, match="model_sha256"):
        run(locked, output)
    assert not output.exists() and not output.with_name("p.csv.partial").exists()


def test_runner_stops_when_an_image_changed_after_listing(locked, tmp_path):
    first = locked["manifest"].parent / locked["rows"][0]["path"]
    first.write_bytes(first.read_bytes() + b"\0")
    output = tmp_path / "p.csv"
    with pytest.raises(ValueError, match="changed since listing"):
        run(locked, output)
    assert not output.exists()
    assert output.with_name("p.csv.partial").exists()  # kept as an unfinished run


def test_runner_never_overwrites(locked, tmp_path):
    output = tmp_path / "p.csv"
    output.write_text("old")
    with pytest.raises(FileExistsError):
        run(locked, output)
    assert output.read_text() == "old"


def test_manifest_rows_must_be_complete_and_unique(locked):
    rows = read_jsonl(locked["manifest"])
    locked["manifest"].write_text(
        "\n".join(json.dumps(r) for r in [*rows, rows[0]]) + "\n"
    )
    with pytest.raises(ValueError, match="unique ID"):
        ev.read_robustness_manifest(locked["manifest"])
    del rows[0]["group_id"]
    locked["manifest"].write_text(json.dumps(rows[0]) + "\n")
    with pytest.raises(ValueError, match="missing"):
        ev.read_robustness_manifest(locked["manifest"])


def test_cli_robustness_needs_all_inputs(tmp_path):
    with pytest.raises(SystemExit):
        ev.main(["--robustness", "--output", str(tmp_path / "p.csv")])
    with pytest.raises(SystemExit):
        ev.main(["--split", "val", "--robustness", "--output", str(tmp_path / "p.csv")])
