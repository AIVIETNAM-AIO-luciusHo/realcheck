"""scripts/g02_h4.py: chỉ dữ liệu tổng hợp, không đọc ảnh thật (H4 chưa khóa)."""

import numpy as np
import pandas as pd
import pytest
from PIL import Image

from scripts import g02_h4 as h4

PARAMS = h4.Params(n_perm=6, n_boot=60, min_per_class=20)


@pytest.fixture(scope="module")
def syn():
    return h4.synthetic(n_groups=30)


def test_a_eff_doi_xung():
    y = np.array([0, 0, 1, 1])
    assert (
        h4.a_eff(y, np.array([0.1, 0.2, 0.8, 0.9]))
        == h4.a_eff(y, np.array([0.9, 0.8, 0.2, 0.1]))
        == 1.0
    )


def test_buoc0_sha_trung_tung_byte(tmp_path):
    f = tmp_path / "r.json"
    f.write_bytes(b"{}")
    ok = h4.step0_reproduce(f, h4.sha256_file(f))
    bad = h4.step0_reproduce(f, "0" * 64)
    assert ok["reproduced"] and not bad["reproduced"]


def test_buoc1_khoa_hash_va_dem(syn, tmp_path):
    df = syn[0]
    csv = tmp_path / "labels.csv"
    df.to_csv(csv, index=False)
    lock = h4.step1_lock(csv, df, PARAMS)
    assert lock["labels_sha256"] == h4.sha256_file(csv)
    assert set(lock["slice_counts"]) >= {
        "G1",
        "G2",
        "G3",
        "cifake",
        "genimage_all",
        "real_vs_glide",
    }


def test_lat_cat_khong_chua_test(syn):
    df = syn[0].copy()
    df.loc[df.index[:10], "split"] = "test"
    for s in (*h4.real_slices(df).values(), *h4.pseudo_slices(df).values()):
        assert "test" not in set(s.split)


def test_ket_qua_khong_phu_thuoc_nhan_test(syn):
    a = syn[0].copy()
    a.loc[a.split == "validation", "split"] = (
        "test"  # không còn validation: đổi nhãn test không được ảnh hưởng
    )
    b = a.copy()
    b.loc[b.split == "test", "label"] = 1 - b.loc[b.split == "test", "label"]
    sa, sb = h4.real_slices(a)["cifake"], h4.real_slices(b)["cifake"]
    assert sa.equals(sb)


def test_hoan_vi_theo_group_giu_nhan_dong_nhat_trong_group(syn):
    s = h4.real_slices(syn[0])["cifake"]
    p = h4.permute_by_group(s, np.random.default_rng(1))
    assert (p.groupby(s.group_id).nunique() == 1).all()
    assert sorted(p.groupby(s.group_id).first()) == sorted(
        s.groupby("group_id").label.first()
    )


def test_chia_nua_can_bang_va_khong_tach_group(syn):
    s = h4.pseudo_slices(syn[0])["G1"]
    half = h4.assign_halves(s, np.random.default_rng(3))
    assert (half.groupby(s.group_id).nunique() == 1).all()
    sizes = half.value_counts()
    assert abs(sizes[0] - sizes[1]) <= 2


def test_hop_le_theo_so_dem_va_null():
    s = pd.DataFrame({"split": ["validation"] * 40, "label": [0] * 20 + [1] * 20})
    assert h4.valid_slice(s, 0.55, h4.Params(min_per_class=20))
    assert not h4.valid_slice(s, 0.61, h4.Params(min_per_class=20))
    assert not h4.valid_slice(s, 0.55, h4.Params(min_per_class=21))


@pytest.mark.parametrize(
    ("neg_ok", "pos_ok", "n", "want"),
    [
        (True, True, 3, "Âm đạt, dương đạt"),
        (False, True, 3, "Âm hỏng"),
        (False, False, 3, "Âm hỏng"),
        (True, False, 3, "Dương hỏng"),
        (True, True, 2, "Không đủ sức"),
    ],
)
def test_ket_cuc_viet_truoc(neg_ok, pos_ok, n, want):
    neg = {"G1": {"ok": neg_ok, "valid": True}, "G2": {"ok": True, "valid": True}}
    pos = {"G1": {"ok": pos_ok}}
    assert h4.verdict(neg, pos, n) == want


def test_lat_cat_khong_hop_le_khong_lam_hong_ket_cuc():
    neg = {"G1": {"ok": False, "valid": False}, "G2": {"ok": True, "valid": True}}
    assert h4.verdict(neg, {"G2": {"ok": True}}, 3) == "Âm đạt, dương đạt"


def test_bootstrap_ghep_cap_xac_dinh_va_dung_chung_mau():
    y = np.array([0, 1] * 20)
    g = np.repeat(np.arange(20), 2)
    p = np.random.default_rng(0).random(40)
    a = h4.cluster_bootstrap(y, g, [p, p], 50, 7)
    assert np.array_equal(a, h4.cluster_bootstrap(y, g, [p, p], 50, 7))
    assert np.array_equal(a[:, 0], a[:, 1])  # cùng điểm số, cùng mẫu ⇒ Δ = 0


def test_nen_lam_tang_tin_hieu_o_lat_cat_giua_hop_le(syn):
    df, load, norm = syn
    labelled = h4.label_halves({"G3": h4.pseudo_slices(df)["G3"]}, PARAMS)
    r = h4.step4_positive(labelled, load, norm, PARAMS, "P1")["G3"]
    assert r["delta_point"][2] > 0.1
    assert r["i_ok"] is True


def test_p2_chay_duoc(syn):
    df, load, norm = syn
    labelled = h4.label_halves({"G3": h4.pseudo_slices(df)["G3"]}, h4.Params(n_boot=30))
    r = h4.step4_positive(labelled, load, norm, h4.Params(n_boot=30), "P2")["G3"]
    assert r["phase"] == "P2" and len(r["delta_point"]) == 3


def test_dhash_va_gan_trung():
    im = Image.fromarray(
        np.random.default_rng(0).integers(0, 255, (32, 32, 3), dtype=np.uint8)
    )
    assert h4.dhash(im) == h4.dhash(im.copy())
    df = pd.DataFrame(
        {
            "id": ["a", "b", "c"],
            "group_id": ["ga", "gb", "gc"],
            "split": ["train", "test", "test"],
        }
    )
    hashes = {
        "a": 0b1111,
        "b": 0b1110,
        "c": 0xFF0,
    }  # a-b khác split, 1 bit; b-c cùng split
    r = h4.near_duplicate_groups(df, hashes)
    assert r["n_pairs"] == 1 and r["groups"] == ["ga", "gb"]


def test_chay_het_khong_trung_thi_khong_lap(syn):
    out = h4.run(*syn, PARAMS)
    assert out["step5"]["outcome"] == "không thấy gần-trùng bằng dHash"
    assert "after_removal" not in out
    assert out["first"]["verdict"] in {
        "Âm đạt, dương đạt",
        "Âm hỏng",
        "Dương hỏng",
        "Không đủ sức",
    }


def test_co_trung_xuyen_split_thi_loai_group_va_lap_dung_mot_lan(syn):
    df, load, norm = syn
    df = df.copy()
    src = df[(df.split == "train") & (df.source == "cifake_real")].iloc[0]
    dup = df[(df.split == "validation") & (df.source == "cifake_real")].index[0]
    df.loc[dup, "id"] = src["id"] + "-dup"
    imgs = {i: load(i) for i in syn[0]["id"]}
    imgs[src["id"] + "-dup"] = imgs[src["id"]]
    out = h4.run(df, imgs.__getitem__, norm, PARAMS)
    assert out["step5"]["n_pairs"] >= 1 and "after_removal" in out
    removed = set(out["step5"]["groups"])
    assert (
        removed
        and "after_removal" in out
        and not (out["after_removal"].get("removed") or [])
    )


def test_main_tu_choi_khi_khong_co_synthetic(capsys):
    assert h4.main([]) == 2
    assert "chưa được Lực khóa" in capsys.readouterr().err


def test_main_synthetic_chay(capsys):
    assert h4.main(["--synthetic", "--n-perm", "4", "--n-boot", "30"]) == 0
    assert '"verdict"' in capsys.readouterr().out
