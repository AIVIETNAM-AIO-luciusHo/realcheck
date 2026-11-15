"""scripts/calibrate_scores.py: dữ liệu tổng hợp có đáp án biết trước."""

import json

import numpy as np
import pytest

from scripts import calibrate_scores as cs


def test_ece_brier_nll_so_tay():
    y = np.array([0, 0, 1, 1])
    p = np.array(
        [0.1, 0.1, 0.9, 0.9]
    )  # hai bin: |0 - 0.1| và |1 - 0.9|, mỗi bin một nửa
    assert cs.ece(y, p, 15) == pytest.approx(0.1)
    assert cs.brier(y, p) == pytest.approx(0.01)
    assert cs.nll(y, p) == pytest.approx(-np.log(0.9))


def test_ece_hoan_hao_bang_khong_va_diem_bang_mot_vao_bin_cuoi():
    y = np.array([1, 1, 0, 0])
    p = np.array([1.0, 1.0, 0.0, 0.0])
    assert cs.ece(y, p, 15) == pytest.approx(0)


def synthetic(n=20000, scale=2.0, shift=0.0, seed=1):
    """Nhãn lấy từ xác suất thật sigmoid(z); model báo sigmoid(scale * z + shift)."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1.5, n)
    y = (rng.random(n) < cs.sigmoid(z)).astype(int)
    return y, cs.sigmoid(scale * z + shift)


def test_temperature_va_platt_khoi_phuc_do_tu_tin_qua_muc():
    y, p = synthetic(scale=2.0)  # quá tự tin gấp đôi: T gần 2, Platt a gần 0.5
    assert cs.fit_temperature(y, p) == pytest.approx(2.0, rel=0.1)
    a, b = cs.fit_platt(y, p)
    assert a == pytest.approx(0.5, rel=0.1) and abs(b) < 0.1
    r = cs.calibrate(y, p, 0.2)
    assert r["temperature"]["after"]["nll"] < r["before"]["nll"]
    assert r["platt"]["after"]["ece"] < r["before"]["ece"]
    assert r["temperature"]["after"]["ece"] < 0.02


def test_da_hieu_chuan_thi_T_gan_1():
    y, p = synthetic(scale=1.0)
    assert cs.fit_temperature(y, p) == pytest.approx(1.0, rel=0.1)


def test_chon_nguong_theo_muc_tieu_fpr_so_tay():
    y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    p = np.array([0.1, 0.2, 0.3, 0.6, 0.4, 0.7, 0.8, 0.9])
    t = cs.pick_threshold(
        y, p, 0.25
    )  # 1/4 ảnh thật cho phép: ngưỡng nhỏ nhất đạt là 0.4 (chỉ ảnh thật 0.6 bị gọi AI)
    assert t == {"threshold": 0.4, "fpr": 0.25, "recall": 1.0}
    t0 = cs.pick_threshold(
        y, p, 0.0
    )  # không ảnh thật nào: t phải > 0.6; điểm AI >= 0.7 giữ lại
    assert (
        t0["fpr"] == 0
        and t0["recall"] == pytest.approx(3 / 4)
        and 0.6 < t0["threshold"] <= 0.7
    )


def test_muc_tieu_khong_dat_duoc_cho_nguong_tren_moi_diem():
    y = np.array([1, 0])
    p = np.array([0.4, 0.9])  # ảnh thật có điểm cao nhất
    t = cs.pick_threshold(y, p, 0.0)
    assert t["threshold"] > 0.9 and t["fpr"] == 0 and t["recall"] == 0


def test_bao_cao_ghi_ro_chon_tren_validation(tmp_path, capsys):
    y, p = synthetic(n=400)
    f = tmp_path / "v.csv"
    f.write_text(
        "sample_id,label,score\n"
        + "\n".join(f"s{i},{y[i]},{p[i]:.6f}" for i in range(len(y)))
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "o.json"
    assert (
        cs.main(["--scores", str(f), "--target-fpr", "0.1", "--output", str(out)]) == 0
    )
    d = json.loads(out.read_text())
    assert "không dùng cho đánh giá cuối" in d["note"]
    assert d["threshold"]["fpr"] <= 0.1
    assert "không dùng cho đánh giá cuối" in capsys.readouterr().err


@pytest.mark.parametrize(
    "rows,msg",
    [
        (["a,0,0.1", "a,1,0.9"], "trùng"),
        (["a,2,0.1", "b,1,0.9"], "label"),
        (["a,0,nan", "b,1,0.9"], "hữu hạn"),
        (["a,0,1.2", "b,1,0.9"], "ngoài"),
        (["a,0,0.1", "b,0,0.9"], "hai lớp"),
    ],
)
def test_du_lieu_hong_bi_tu_choi(tmp_path, rows, msg):
    f = tmp_path / "v.csv"
    f.write_text("sample_id,label,score\n" + "\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=msg):
        cs.read_scores(f)


def test_main_tham_so_sai_va_file_thieu(tmp_path):
    assert cs.main(["--scores", str(tmp_path / "none.csv"), "--target-fpr", "0.1"]) == 2
    assert cs.main(["--scores", str(tmp_path / "none.csv"), "--target-fpr", "2"]) == 2


def test_diem_bang_0_va_1_khong_tao_vo_han():
    y = np.array([0, 0, 1, 1, 1, 0])
    p = np.array([0.0, 0.2, 1.0, 0.9, 0.3, 0.6])
    r = cs.calibrate(y, p, 0.5)
    json.dumps(r, allow_nan=False)


def test_platt_he_so_am_bi_tu_choi_thoat_2(tmp_path, capsys):
    y, p = synthetic(n=600)
    f = tmp_path / "v.csv"
    f.write_text(
        "sample_id,label,score\n"
        + "\n".join(f"s{i},{y[i]},{1 - p[i]:.6f}" for i in range(len(y)))
        + "\n"
    )
    with pytest.raises(ValueError, match="a = .* <= 0"):
        cs.calibrate(y, 1 - p, 0.1)
    assert cs.main(["--scores", str(f), "--target-fpr", "0.1"]) == 2
    assert "đảo thứ tự" in capsys.readouterr().err


def test_diem_khong_doi_bi_tu_choi():
    y = np.array([0, 1, 0, 1])
    for value in (0.0, 1.0, 0.5):
        with pytest.raises(ValueError, match="bằng nhau"):
            cs.calibrate(y, np.full(4, value), 0.1)


def test_diem_chi_0_va_1_canh_bao():
    y = np.array([0, 0, 0, 1, 1, 1, 1, 0])
    p = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0])
    r = cs.calibrate(y, p, 0.5)
    assert any("chỉ gồm 0 và 1" in w for w in r["warnings"])
    assert 0 <= r["threshold"]["raw_score"] <= 1


def test_nguong_tren_moi_diem_duoc_kep_va_canh_bao():
    ai = np.linspace(0.55, 0.99, 20)
    real = np.r_[
        np.linspace(0.02, 0.45, 19), 1.0
    ]  # một ảnh thật có điểm cao nhất (1.0)
    y, p = np.r_[np.ones(20), np.zeros(20)].astype(int), np.r_[ai, real]
    r = cs.calibrate(y, p, 0.0)
    assert (
        r["threshold"]["raw_score"] <= 1
        and r["threshold"]["fpr"] == 0
        and r["threshold"]["recall"] == 0
    )
    assert any("nằm trên mọi điểm" in w for w in r["warnings"])


def test_T_cham_can_canh_bao():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 400)
    p = np.clip(
        0.5 + (y - 0.5) * 1e-4 * rng.random(400) + 1e-7, 0, 1
    )  # điểm tách nhãn nhưng cực kỳ thiếu tự tin: T chạm cận dưới
    r = cs.calibrate(y, p, 0.2)
    assert r["temperature"]["T"] < 0.02 and any("chạm cận" in w for w in r["warnings"])


def test_bao_cao_co_truong_warnings_va_quy_tac_nguong(tmp_path):
    y, p = synthetic(n=400)
    r = cs.calibrate(y, p, 0.1)
    assert (
        r["warnings"] == []
        and ">= t" in r["threshold"]["rule"]
        and "> high" in r["threshold"]["rule"]
    )


def test_o_csv_qua_lon_va_output_loi_la_exit_2(tmp_path, capsys):
    big = tmp_path / "big.csv"
    big.write_text("sample_id,label,score\n" + "x" * 200000 + ",0,0.1\n")
    assert cs.main(["--scores", str(big), "--target-fpr", "0.1"]) == 2
    y, p = synthetic(n=300)
    f = tmp_path / "v.csv"
    f.write_text(
        "sample_id,label,score\n"
        + "\n".join(f"s{i},{y[i]},{p[i]:.6f}" for i in range(len(y)))
        + "\n"
    )
    out = tmp_path / "khong_co" / "o.json"
    assert (
        cs.main(["--scores", str(f), "--target-fpr", "0.1", "--output", str(out)]) == 2
    )
    assert "không ghi được" in capsys.readouterr().err


def test_doc_csv_co_bom(tmp_path):
    f = tmp_path / "v.csv"
    f.write_text("sample_id,label,score\na,0,0.1\nb,1,0.9\n", encoding="utf-8-sig")
    y, _ = cs.read_scores(f)
    assert y.tolist() == [0, 1]
