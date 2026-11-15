"""scripts/adv12_run.py con đặc trưng/ảnh tổng hợp: augment chỉ train, rò group bị chặn, tất định, CSV điểm đọc được."""

import csv
import json
from argparse import Namespace

import numpy as np
import pytest
from PIL import Image

from scripts import adv12_run as run

SOURCES = {0: "genimage_real", 1: "genimage_sd14"}
HEADER = "filepath,label,source,split,raw_path,norm_version,group_id"


def embed(images):
    """Đặc trưng giả tất định theo pixel: trung bình RGB và độ lệch chuẩn."""
    out = []
    for im in images:
        a = np.asarray(im.convert("RGB"), dtype=np.float32) / 255
        out.append([*a.mean(axis=(0, 1)), a.std()])
    return np.array(out, dtype=np.float32)


def make_dataset(tmp_path, groups=None):
    """16 ảnh JPEG 256x256: train 8, val 4, test 4, mỗi split đủ hai lớp; mỗi ảnh một group (trừ khi `groups` ghi đè)."""
    plan = [("train", 8), ("val", 4), ("test", 4)]
    rng = np.random.default_rng(0)
    lines, k = [], 0
    for split, n in plan:
        for i in range(n):
            label = i % 2
            base = 70 + 110 * label
            arr = np.clip(base + rng.normal(0, 12, (256, 256, 3)), 0, 255).astype(
                np.uint8
            )
            path = tmp_path / f"{k}.jpg"
            Image.fromarray(arr).save(path, quality=95)
            group = groups[k] if groups else f"g{k}"
            lines.append(
                f"{path},{label},{SOURCES[label]},{split},raw{k}.png,1,{group}"
            )
            k += 1
    labels = tmp_path / "labels.csv"
    labels.write_text(HEADER + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return labels


def extract_args(labels, out, **over):
    base = {
        "labels": labels, "output": out, "encoder": "last", "layers": None, "model_id": "m",
        "revision": None, "image_column": "filepath", "augment": 0.0, "augment_seed": 42, "batch_size": 4,
    }  # fmt: skip
    return Namespace(**{**base, **over})


def test_augment_chi_ap_cho_train(tmp_path):
    labels = make_dataset(tmp_path)
    rows = run.read_rows(labels)
    base, rec0 = run.extract_rows(rows, embed, augment_p=0.0)
    aug, rec = run.extract_rows(rows, embed, augment_p=1.0, augment_seed=7)
    splits = np.array([r["split"] for r in rows])
    assert rec0 == [] and len(rec) == 8 and {r["split"] for r in rec} == {"train"}
    assert np.array_equal(
        aug[splits != "train"], base[splits != "train"]
    )  # val/test không đổi
    assert not np.allclose(
        aug[splits == "train"], base[splits == "train"]
    )  # train có đổi
    assert all(len(r["applied"]) == 3 for r in rec)  # p = 1: đủ ba phép


def test_tat_dinh_va_khong_phu_thuoc_thu_tu_dong(tmp_path):
    labels = make_dataset(tmp_path)
    rows = run.read_rows(labels)
    a, ra = run.extract_rows(rows, embed, augment_p=0.7, augment_seed=3)
    b, rb = run.extract_rows(rows, embed, augment_p=0.7, augment_seed=3)
    assert np.array_equal(a, b) and ra == rb
    rev = rows[::-1]
    c, _ = run.extract_rows(rev, embed, augment_p=0.7, augment_seed=3)
    assert np.array_equal(c[::-1], a)  # cùng ảnh cùng seed dù đổi thứ tự dòng
    d, _ = run.extract_rows(rows, embed, augment_p=0.7, augment_seed=4)
    assert not np.array_equal(a, d)


def test_extract_ghi_npz_manifest_va_augment_jsonl(tmp_path):
    labels = make_dataset(tmp_path)
    out = tmp_path / "run" / "f.npz"
    assert run.cmd_extract(extract_args(labels, out, augment=0.5), embed=embed) == 0
    data = run.load_npz(out)
    assert data["features"].shape == (16, 4) and set(data["splits"].tolist()) == {
        "train",
        "val",
        "test",
    }
    manifest = json.loads(out.with_suffix(".json").read_text())
    assert manifest["labels_sha256"] == run.sha256_file(labels)
    assert manifest["features_sha256"] == run.sha256_file(out)
    assert manifest["augment"] == {"p": 0.5, "seed": 42, "applied_splits": ["train"]}
    assert manifest["counts"] == {"train": 8, "val": 4, "test": 4}
    assert "pillow" in manifest["versions"] and manifest["versions"]["python"]
    lines = out.with_suffix(".augment.jsonl").read_text().splitlines()
    assert len(lines) == 8 and all(json.loads(x)["split"] == "train" for x in lines)


def test_khong_augment_thi_khong_ghi_jsonl(tmp_path):
    out = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), out), embed=embed)
    assert not out.with_suffix(".augment.jsonl").exists()
    assert (
        json.loads(out.with_suffix(".json").read_text())["augment"]["applied_splits"]
        == []
    )


def test_labels_thieu_group_id_bi_tu_choi(tmp_path):
    labels = make_dataset(tmp_path)
    labels.write_text(
        "\n".join(
            ",".join(line.split(",")[:6]) for line in labels.read_text().splitlines()
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="group_id"):
        run.read_rows(labels)


def fit_args(feats, out, **over):
    base = {
        "features": feats,
        "output_dir": out,
        "name": "adv12_probe",
        "C": 10.0,
        "seed": 42,
    }
    return Namespace(**{**base, **over})


def test_fit_ghi_model_va_diem_dung_dinh_dang(tmp_path):
    labels = make_dataset(tmp_path)
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(labels, feats), embed=embed)
    out = tmp_path / "fit"
    assert run.cmd_fit(fit_args(feats, out)) == 0
    meta = json.loads((out / "adv12_probe.fit.json").read_text())
    assert meta["split_counts"] == {"train": 8, "val": 4, "test": 4} and meta[
        "trained_on"
    ] == ["train"]
    assert meta["model_sha256"] == run.sha256_file(out / "adv12_probe.joblib")
    assert meta["features_sha256"] == run.sha256_file(feats)
    for name, n in (("val", 4), ("test", 4)):
        with (out / f"adv12_probe.{name}_scores.csv").open(newline="") as stream:
            reader = csv.DictReader(stream)
            assert reader.fieldnames == [
                "sample_id",
                "label",
                "score",
                "group_id",
                "source",
            ]
            rows = list(reader)
        assert len(rows) == n and all(0 <= float(r["score"]) <= 1 for r in rows)
    assert not (out / "adv12_probe.train_scores.csv").exists()  # không xuất điểm train


def test_fit_tat_dinh(tmp_path):
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    for d in ("a", "b"):
        run.cmd_fit(fit_args(feats, tmp_path / d))
    for f in ("adv12_probe.val_scores.csv", "adv12_probe.test_scores.csv"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()


def test_fit_chan_ro_group_giua_hai_split(tmp_path):
    """npz dựng tay (bỏ qua extract) vẫn bị fit chặn và không ghi model."""
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    d = run.load_npz(feats)
    groups = d["groups"].copy()
    groups[9] = groups[0]
    np.savez(feats, **{**d, "groups": groups})
    with pytest.raises(ValueError, match="hai split"):
        run.cmd_fit(fit_args(feats, tmp_path / "o"))
    assert not (tmp_path / "o" / "adv12_probe.joblib").exists()
    assert (
        run.main(["fit", "--features", str(feats), "--output-dir", str(tmp_path / "o")])
        == 2
    )


def test_fit_tu_choi_ten_clip_probe_va_thu_muc_models(tmp_path, monkeypatch):
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    with pytest.raises(ValueError, match="clip_probe"):
        run.cmd_fit(fit_args(feats, tmp_path / "o", name="clip_probe_x"))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "models").mkdir()
    with pytest.raises(ValueError, match="models/"):
        run.cmd_fit(fit_args(feats, tmp_path / "models" / "sub"))


def test_fit_can_hai_lop_o_train(tmp_path):
    labels = make_dataset(tmp_path)
    labels.write_text(
        labels.read_text()
        .replace("genimage_sd14,train", "genimage_real,train")
        .replace(",1,genimage_real,train", ",0,genimage_real,train")
    )
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(labels, feats), embed=embed)
    with pytest.raises(ValueError, match="hai lớp"):
        run.cmd_fit(fit_args(feats, tmp_path / "o"))


def test_csv_diem_doc_duoc_boi_compare_models_va_calibrate_scores(tmp_path):
    compare = pytest.importorskip("scripts.compare_models")
    calibrate_scores = pytest.importorskip("scripts.calibrate_scores")

    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    run.cmd_fit(fit_args(feats, tmp_path / "o"))
    scores = tmp_path / "o" / "adv12_probe.val_scores.csv"
    parsed = compare.read_scores(scores)
    assert len(parsed) == 4 and all(
        {"label", "score", "group_id", "source"} <= v.keys() for v in parsed.values()
    )
    assert calibrate_scores.read_scores(scores)[0].tolist().count(1) == 2


def test_extract_voi_clip_vision_nho(tmp_path):
    torch = pytest.importorskip("torch")
    transformers = pytest.importorskip("transformers")
    from models import clip_layers

    config = transformers.CLIPVisionConfig(hidden_size=16, intermediate_size=32, num_hidden_layers=3,
                                           num_attention_heads=2, image_size=32, patch_size=16, projection_dim=8)  # fmt: skip
    torch.manual_seed(0)
    model = transformers.CLIPVisionModel(config).eval()
    processor = transformers.CLIPImageProcessor(
        size={"shortest_edge": 32}, crop_size={"height": 32, "width": 32}
    )
    rows = run.read_rows(make_dataset(tmp_path))
    fn = lambda images: clip_layers.extract_features(
        images, model, processor, [1, 3], batch_size=len(images)
    )
    a, _ = run.extract_rows(rows, fn, augment_p=0.5, augment_seed=1)
    b, _ = run.extract_rows(rows, fn, augment_p=0.5, augment_seed=1)
    assert a.shape == (16, 32) and np.array_equal(a, b)


@pytest.mark.parametrize(
    "name",
    [
        "",
        ".hidden",
        "a/b",
        "a\\b",
        "..",
        "a..b",
        "sub/clip_probe_x",
        "../../models/leak",
    ],
)
def test_name_khong_phai_basename_an_toan_bi_tu_choi(tmp_path, name):
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    with pytest.raises(ValueError, match="--name"):
        run.cmd_fit(fit_args(feats, tmp_path / "o", name=name))
    assert not (tmp_path / "o").exists()


def test_ten_hop_le_van_ghi_duoc(tmp_path):
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    assert run.cmd_fit(fit_args(feats, tmp_path / "o", name="e1-v2.0_a")) == 0


def test_khong_hoi_tu_la_exit_2(tmp_path, monkeypatch, capsys):
    from sklearn.exceptions import ConvergenceWarning

    def boom(self, *a, **k):
        raise ConvergenceWarning("không hội tụ")

    monkeypatch.setattr(run.LogisticRegression, "fit", boom)
    feats = tmp_path / "f.npz"
    run.cmd_extract(extract_args(make_dataset(tmp_path), feats), embed=embed)
    assert (
        run.main(["fit", "--features", str(feats), "--output-dir", str(tmp_path / "o")])
        == 2
    )
    assert "không hội tụ" in capsys.readouterr().err


def test_extract_chan_ro_group_ngay_tu_extract(tmp_path):
    groups = [f"g{k}" for k in range(16)]
    groups[9] = "g0"
    labels = make_dataset(tmp_path, groups)
    out = tmp_path / "f.npz"
    with pytest.raises(ValueError, match="hai split"):
        run.cmd_extract(extract_args(labels, out), embed=embed)
    assert not out.exists()


def test_score_can_model(tmp_path, monkeypatch):
    monkeypatch.delenv("REALCHECK_MODEL_PATH", raising=False)
    args = Namespace(
        labels=make_dataset(tmp_path),
        model=None,
        output=tmp_path / "s.csv",
        split=None,
        image_column="filepath",
    )
    with pytest.raises(ValueError, match="REALCHECK_MODEL_PATH"):
        run.cmd_score(args)


def test_score_dung_load_scorer_va_ghi_csv(tmp_path, monkeypatch):
    import models.score as ms

    class Fake:
        def __call__(self, image):
            return 0.25

    seen = {}
    monkeypatch.setattr(
        ms, "load_scorer", lambda path: seen.setdefault("path", path) and Fake()
    )
    args = Namespace(
        labels=make_dataset(tmp_path),
        model=tmp_path / "m.joblib",
        output=tmp_path / "s.csv",
        split=["val"],
        image_column="filepath",
    )
    assert run.cmd_score(args) == 0 and seen["path"] == tmp_path / "m.joblib"
    with (tmp_path / "s.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4 and {r["score"] for r in rows} == {"0.25"}
    assert list(rows[0]) == ["sample_id", "label", "score", "group_id", "source"]
