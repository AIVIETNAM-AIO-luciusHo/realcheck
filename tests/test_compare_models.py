"""scripts/compare_models.py: số tính tay, lệch ID/dữ liệu hỏng bị từ chối, bootstrap tất định."""

import json
from argparse import Namespace

import numpy as np
import pytest

from scripts import compare_models as cm

ARGS = Namespace(low=0.3, binary=0.5, high=0.7, replicates=200, seed=42)


def write(path, rows, header="sample_id,label,score,group_id,source"):
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


# 4 ảnh thật (label 0) và 4 ảnh AI (label 1); điểm A và B đã chọn để tính tay.
LAB = [0, 0, 0, 0, 1, 1, 1, 1]
SCORE_A = [0.1, 0.4, 0.6, 0.8, 0.2, 0.55, 0.75, 0.9]
SCORE_B = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]


def rows(scores, src=("s1",) * 8):
    return [f"i{k},{LAB[k]},{scores[k]},g{k},{src[k]}" for k in range(8)]


def test_so_tay_model_a(tmp_path):
    a = cm.read_scores(write(tmp_path / "a.csv", rows(SCORE_A)))
    b = cm.read_scores(write(tmp_path / "b.csv", rows(SCORE_B)))
    out = cm.compare(a, b, ARGS)["slices"]["__all__"]
    A = out["A"]
    # AUROC A: cặp (AI > thật): AI 0.2 thắng 1/4, 0.55 thắng 2/4, 0.75 thắng 3/4, 0.9 thắng 4/4 => 10/16
    assert A["auroc"] == pytest.approx(10 / 16)
    assert A["fpr_binary"] == pytest.approx(2 / 4)  # thật 0.6, 0.8 >= 0.5
    assert A["fpr_high"] == pytest.approx(1 / 4)  # chỉ 0.8 > 0.7
    assert A["recall_binary"] == pytest.approx(3 / 4)  # 0.55, 0.75, 0.9
    assert A["recall_high"] == pytest.approx(2 / 4)  # 0.75, 0.9
    assert A["uncertain_count"] == 3  # 0.4, 0.55, 0.6 trong [0.3, 0.7]
    B = out["B"]
    assert B["auroc"] == pytest.approx(
        1.0
    )  # mọi ảnh AI (0.6..0.9) cao hơn mọi ảnh thật (0.1..0.4)
    assert B["fpr_binary"] == 0 and B["recall_binary"] == 1
    assert B["uncertain_count"] == 4  # 0.3, 0.4, 0.6, 0.7
    assert out["paired_A_minus_B"]["auroc"]["delta"] == pytest.approx(10 / 16 - 1.0)
    delta = out["paired_A_minus_B"]["fpr_binary"]["delta"]
    assert delta == pytest.approx(A["fpr_binary"] - out["B"]["fpr_binary"])


def test_ties_nua_trong_so():
    y = np.array([0, 1])
    p = np.array([0.5, 0.5])
    m = cm.weighted_metrics(y, p, np.ones((1, 2)), 0.3, 0.5, 0.7)
    assert m["auroc"][0] == pytest.approx(0.5)


def test_thieu_mot_lop_cho_nan_va_json_null(tmp_path):
    r = ["a,0,0.1,ga,x", "b,0,0.2,gb,x"]
    a = write(tmp_path / "a.csv", r)
    out = tmp_path / "o.json"
    assert (
        cm.main(
            ["--a", str(a), "--b", str(a), "--output", str(out), "--replicates", "20"]
        )
        == 0
    )
    d = json.loads(out.read_text())
    assert d["slices"]["__all__"]["A"]["auroc"] is None
    assert d["slices"]["__all__"]["paired_A_minus_B"]["auroc"]["ci95"] is None


def test_lech_id_bi_tu_choi(tmp_path):
    a = cm.read_scores(write(tmp_path / "a.csv", rows(SCORE_A)))
    b = cm.read_scores(write(tmp_path / "b.csv", rows(SCORE_B)[:-1]))
    with pytest.raises(ValueError, match="khác tập sample_id"):
        cm.align(a, b)


def test_lech_nhan_hoac_nhom_bi_tu_choi(tmp_path):
    a = cm.read_scores(write(tmp_path / "a.csv", rows(SCORE_A)))
    r = rows(SCORE_B)
    r[0] = "i0,1,0.1,g0,s1"
    b = cm.read_scores(write(tmp_path / "b.csv", r))
    with pytest.raises(ValueError, match="label khác nhau"):
        cm.align(a, b)


@pytest.mark.parametrize(
    "bad,msg",
    [
        ("a,0,0.1,g,s\na,1,0.2,g,s", "trùng"),
        ("a,2,0.1,g,s", "label phải là 0 hoặc 1"),
        ("a,0,nan,g,s", "không hữu hạn"),
        ("a,0,1.5,g,s", "ngoài \\[0, 1\\]"),
        ("a,0,abc,g,s", "không phải số"),
        (" ,0,0.1,g,s", "sample_id rỗng"),
    ],
)
def test_du_lieu_hong_bi_tu_choi(tmp_path, bad, msg):
    with pytest.raises(ValueError, match=msg):
        cm.read_scores(write(tmp_path / "a.csv", bad.split("\n")))


def test_nhom_hai_nhan_bi_tu_choi(tmp_path):
    r = ["a,0,0.1,g,s", "b,1,0.9,g,s"]
    s = cm.read_scores(write(tmp_path / "a.csv", r))
    with pytest.raises(ValueError, match="hai nhãn"):
        cm.align(s, s)


def test_thieu_cot_bi_tu_choi(tmp_path):
    with pytest.raises(ValueError, match="cần cột"):
        cm.read_scores(write(tmp_path / "a.csv", ["a,0"], header="sample_id,label"))


def test_bootstrap_tat_dinh_va_theo_nhom(tmp_path):
    rng = np.random.default_rng(0)
    n = 60
    lab = [k % 2 for k in range(n)]
    base = [0.7 * lab[k] + 0.3 * float(rng.random()) for k in range(n)]
    other = [min(1.0, max(0.0, v + 0.1 * float(rng.normal()))) for v in base]

    def make(sc):
        return [
            f"i{k},{lab[k]},{sc[k]:.6f},g{k // 3 * 2 + lab[k]},s{k % 2}"
            for k in range(n)
        ]

    a = write(tmp_path / "a.csv", make(base))
    b = write(tmp_path / "b.csv", make(other))
    outs = []
    for name in ("o1.json", "o2.json"):
        assert (
            cm.main(
                [
                    "--a",
                    str(a),
                    "--b",
                    str(b),
                    "--output",
                    str(tmp_path / name),
                    "--replicates",
                    "100",
                ]
            )
            == 0
        )
        outs.append((tmp_path / name).read_text())
    assert outs[0] == outs[1]
    d = json.loads(outs[0])
    assert set(d["slices"]) == {"__all__", "s0", "s1"}
    ci = d["slices"]["__all__"]["paired_A_minus_B"]["auroc"]["ci95"]
    delta = d["slices"]["__all__"]["paired_A_minus_B"]["auroc"]["delta"]
    assert ci[0] <= delta <= ci[1] + 0.2 and ci[0] <= ci[1]
    # trọng số theo nhóm: mọi ảnh cùng nhóm có cùng trọng số trong mỗi replicate
    groups = [f"g{k // 3 * 2 + lab[k]}" for k in range(n)]
    w = cm.group_weights(groups, lab, 50, 42)
    for g in set(groups):
        cols = w[:, [i for i, x in enumerate(groups) if x == g]]
        assert (cols == cols[:, :1]).all()
    assert np.array_equal(w, cm.group_weights(groups, lab, 50, 42))
    assert not np.array_equal(w, cm.group_weights(groups, lab, 50, 43))


def test_main_tu_choi_tham_so_va_file_hong(tmp_path, capsys):
    a = write(tmp_path / "a.csv", rows(SCORE_A))
    assert cm.main(["--a", str(a), "--b", str(a), "--replicates", "0"]) == 2
    assert cm.main(["--a", str(a), "--b", str(tmp_path / "none.csv")]) == 2
    assert "LỖI" in capsys.readouterr().err


def test_o_csv_qua_lon_la_loi_ro_rang(tmp_path, capsys):
    f = tmp_path / "a.csv"
    f.write_text(
        "sample_id,label,score\n" + "x" * 200000 + ",0,0.1\n", encoding="utf-8"
    )
    assert cm.main(["--a", str(f), "--b", str(f)]) == 2
    assert "LỖI" in capsys.readouterr().err


def test_output_khong_ghi_duoc_la_loi_ro_rang(tmp_path, capsys):
    a = write(tmp_path / "a.csv", rows(SCORE_A))
    out = tmp_path / "khong_co" / "o.json"
    assert (
        cm.main(
            ["--a", str(a), "--b", str(a), "--output", str(out), "--replicates", "5"]
        )
        == 2
    )
    assert "không ghi được" in capsys.readouterr().err


def test_doc_csv_co_bom(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("sample_id,label,score\na,0,0.1\nb,1,0.9\n", encoding="utf-8-sig")
    assert set(cm.read_scores(f)) == {"a", "b"}


def test_source_ten_all_la_slice_rieng_va_khong_gop_voi_slice_tong(tmp_path):
    r = [
        f"i{k},{LAB[k]},{SCORE_A[k]},g{k},{'all' if k < 4 else 'other'}"
        for k in range(8)
    ]
    a = cm.read_scores(write(tmp_path / "a.csv", r))
    out = cm.compare(a, a, ARGS)["slices"]
    assert set(out) == {"__all__", "all", "other"}
    assert out["__all__"]["n"] == 8 and out["all"]["n"] == 4


def test_source_ten_slice_tong_bi_tu_choi(tmp_path):
    r = [f"i{k},{LAB[k]},{SCORE_A[k]},g{k},__all__" for k in range(8)]
    a = cm.read_scores(write(tmp_path / "a.csv", r))
    with pytest.raises(ValueError, match="__all__"):
        cm.compare(a, a, ARGS)


def test_khong_co_cot_source_thi_chi_co_slice_tong(tmp_path):
    f = write(
        tmp_path / "a.csv",
        [f"i{k},{LAB[k]},{SCORE_A[k]}" for k in range(8)],
        header="sample_id,label,score",
    )
    a = cm.read_scores(f)
    assert list(cm.compare(a, a, ARGS)["slices"]) == ["__all__"]
