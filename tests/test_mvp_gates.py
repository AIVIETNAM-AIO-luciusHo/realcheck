"""KAN-57/58/59: mẫu SLO, scope check_performance, bảng gate nghiệm thu (không cần locust/mạng)."""

import json
import shutil
from pathlib import Path

import pytest

from scripts import check_mvp_gates, check_performance
from tests.test_evaluate import locked  # noqa: F401  (fixture)
from tests.test_ml_release import candidate, release_data  # noqa: F401  (fixture)
from tests.test_performance_reporting import GOOD_SLO, _req, _write

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "performance" / "slo.template.json"


def _side(path, scenario, n_ok=10, lat=100):
    rows = [{"type": "meta", "scenario": scenario}]
    rows += [_req(i, "200", 200, lat) for i in range(n_ok)]
    return _write(path, rows)


def _slo_file(tmp_path, **over):
    p = tmp_path / "slo.json"
    p.write_text(json.dumps(GOOD_SLO | over), encoding="utf-8")
    return p


# --- KAN-57: mẫu SLO ---------------------------------------------------------
def test_mau_slo_bi_tu_choi_va_khong_co_slo_json():
    assert not (ROOT / "docs" / "performance" / "slo.json").exists()
    with pytest.raises(ValueError, match="p95_ms_max"):
        check_performance.load_slo(TEMPLATE)


def test_mau_slo_dien_du_thi_chi_con_thieu_duyet(tmp_path):
    t = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    filled = GOOD_SLO | {"approved": False}
    assert set(GOOD_SLO) <= set(t)  # mẫu có đủ trường mà schema đòi
    p = tmp_path / "s.json"
    p.write_text(json.dumps(filled), encoding="utf-8")
    with pytest.raises(ValueError, match="chưa được duyệt"):
        check_performance.load_slo(p)


def test_slo_day_du_da_duyet_duoc_nhan(tmp_path):
    assert check_performance.load_slo(_slo_file(tmp_path))["approved"] is True


def test_slo_chua_duyet_thoat_2_chi_la_baseline(tmp_path, capsys):
    side = _side(tmp_path / "s.jsonl", "baseline")
    slo = _slo_file(tmp_path, approved=False)
    assert check_performance.main(["--sidecar", str(side), "--slo", str(slo)]) == 2
    assert "chỉ là baseline" in capsys.readouterr().err


# --- KAN-58: scope ------------------------------------------------------------
def test_scope_lech_kich_ban_thoat_2(tmp_path):
    slo = _slo_file(tmp_path)
    for scenario, scope in [
        ("rate_only", "load"),
        ("baseline", "soak"),
        (None, "load"),
    ]:
        side = _side(tmp_path / "s.jsonl", scenario)
        code, lines = check_performance.run(side, slo, scope)
        assert code == 2 and "scenario" in lines[0]


def test_soak_can_rss_va_do_tang_rss(tmp_path):
    slo = _slo_file(tmp_path, rps200_min=0)
    side = _side(tmp_path / "s.jsonl", "soak")
    assert check_performance.run(side, slo, "soak")[0] == 2  # thiếu --rss
    rss = tmp_path / "rss.json"
    rss.write_text('{"rss_after_warmup_mb": 100, "rss_end_mb": 110}', encoding="utf-8")
    assert check_performance.run(side, slo, "soak", rss)[0] == 0  # đúng 10% = biên
    rss.write_text(
        '{"rss_after_warmup_mb": 100, "rss_end_mb": 110.1}', encoding="utf-8"
    )
    code, lines = check_performance.run(side, slo, "soak", rss)
    assert code == 1 and any("RSS" in ln for ln in lines)
    rss.write_text('{"rss_after_warmup_mb": 0, "rss_end_mb": 1}', encoding="utf-8")
    assert check_performance.run(side, slo, "soak", rss)[0] == 2


def test_recovery_bo_qua_rps_nhung_giu_p95_va_loi(tmp_path):
    side = _side(tmp_path / "s.jsonl", "recovery", n_ok=3)
    slo = _slo_file(tmp_path, rps200_min=1000)
    assert check_performance.run(side, slo, "recovery")[0] == 0
    assert (
        check_performance.run(_side(tmp_path / "s.jsonl", "baseline", 3), slo)[0] == 1
    )
    slow = _side(tmp_path / "slow.jsonl", "recovery", n_ok=3, lat=5000)
    assert check_performance.run(slow, slo, "recovery")[0] == 1


# --- KAN-59: bảng gate --------------------------------------------------------
JUNIT_OK = '<testsuites><testsuite tests="{n}">{cases}</testsuite></testsuites>'


def _junit(path, n=20, extra=""):
    cases = "".join(f'<testcase name="t{i}"/>' for i in range(n)) + extra
    path.write_text(JUNIT_OK.format(n=n, cases=cases), encoding="utf-8")


def _cov(path, rate):
    path.write_text(f'<coverage line-rate="{rate}"></coverage>', encoding="utf-8")


def _eval(path, **over):
    """Khóa theo models/evaluate.py (dataset, test, quality.status); xem test báo cáo thật bên dưới."""
    d = {
        "dataset": {"version": "genimage", "hash": "h"},
        "test": {"n": 100, "accuracy": 0.93},
        "quality": {"target_accuracy": 0.9, "status": "pass"},
    } | over
    path.write_text(json.dumps(d), encoding="utf-8")


def _audit_report(**over):
    """Báo cáo audit hợp lệ, không rỗng (còn đặc trưng post không hằng số), theo metadata_audit.py."""
    ds = {
        "constant_features": {"post": ["format"]},
        "n_features": 13,
        "slices": {
            "all": {
                "post": {
                    "valid": True,
                    "test_counts": {"0": 50, "1": 50},
                    "a_eff": 0.52,
                }
            }
        },
        "controls": {"positive": {"a_eff": 1.0}, "negative": {"a_eff": 0.5}},
    } | over
    return {"genimage": ds, "gate": {"passed": True}}


def _write_audit(art, report):
    (art / "metadata-audit.json").write_text(json.dumps(report), encoding="utf-8")


def _full(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    _junit(art / "unit.xml")
    _cov(art / "coverage.xml", 0.8)
    _write_audit(art, _audit_report())
    _eval(art / "evaluation.json")
    _junit(art / "integration.xml", 3)
    _junit(art / "ui-gateway.xml", 3)
    _side(art / "load.jsonl", "baseline")
    _side(art / "soak.jsonl", "soak")
    _side(art / "recovery.jsonl", "recovery")
    (art / "soak-rss.json").write_text(
        '{"rss_after_warmup_mb": 100, "rss_end_mb": 105}'
    )
    return art, _slo_file(tmp_path, rps200_min=0)


def _run(art, slo, capsys):
    code = check_mvp_gates.main(["--artifacts", str(art), "--slo", str(slo)])
    return code, capsys.readouterr().out


def test_gate_du_bang_chung_thoat_0(tmp_path, capsys):
    art, slo = _full(tmp_path)
    code, out = _run(art, slo, capsys)
    assert code == 0 and out.count("[đạt]") == 9 and "TẤT CẢ GATE ĐẠT" in out


def test_khong_co_bang_chung_thi_khong_gate_nao_dat(tmp_path, capsys):
    code, out = _run(tmp_path / "none", tmp_path / "none.json", capsys)
    assert code == 1 and "[đạt]" not in out and out.count("[thiếu bằng chứng]") == 9


@pytest.mark.parametrize(
    "name",
    ["unit.xml", "coverage.xml", "metadata-audit.json", "evaluation.json", "integration.xml",
     "ui-gateway.xml", "load.jsonl", "soak.jsonl", "recovery.jsonl", "soak-rss.json"],
)  # fmt: skip
def test_xoa_hoac_lam_rong_mot_file_thi_that_bai(tmp_path, capsys, name):
    art, slo = _full(tmp_path)
    (art / name).write_text("")  # rỗng
    code, out = _run(art, slo, capsys)
    assert code == 1 and "[thiếu bằng chứng]" in out
    (art / name).unlink()
    code, out = _run(art, slo, capsys)
    assert code == 1 and "[thiếu bằng chứng]" in out


def test_slo_thieu_thi_gate_slo_va_ba_gate_tai_khong_dat(tmp_path, capsys):
    art, _ = _full(tmp_path)
    code, out = _run(art, tmp_path / "none.json", capsys)
    assert code == 1 and out.count("[đạt]") == 5


def test_slo_chua_duyet_thi_chua_dat(tmp_path, capsys):
    art, _ = _full(tmp_path)
    slo = _slo_file(tmp_path, approved=False)
    code, out = _run(art, slo, capsys)
    assert code == 1 and out.count("[chưa đạt]") == 4  # G06-G09


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a: _junit(a / "unit.xml", 14),  # < 15 ca
        lambda a: _cov(a / "coverage.xml", 0.69),
        lambda a: _junit(a / "unit.xml", 20, '<testcase name="x"><failure/></testcase>'),
        lambda a: _junit(a / "unit.xml", 20, '<testcase name="x"><skipped type="pytest.skip"/></testcase>'),
        lambda a: (a / "metadata-audit.json").write_text('{"gate": {"passed": true}}'),  # cờ cũ không đủ
        lambda a: _write_audit(a, _audit_report(constant_features={"post": [f"f{i}" for i in range(13)]})),
        lambda a: _write_audit(a, _audit_report(slices={"all": {"post": {"valid": True, "test_counts": {"0": 50, "1": 50}, "a_eff": 0.56}}})),
        lambda a: _eval(a / "evaluation.json", quality={"status": "fail"}),
        lambda a: _eval(a / "evaluation.json", quality={"status": True}),
        lambda a: _eval(a / "evaluation.json", test={"n": 100, "accuracy": 0.89}),
        lambda a: _eval(a / "evaluation.json", test={"n": 100, "accuracy": float("nan")}),
        lambda a: _eval(a / "evaluation.json", test={"n": 0, "accuracy": 1.0}),
        lambda a: _eval(a / "evaluation.json", test=None, split="val"),
        lambda a: _eval(a / "evaluation.json", dataset={"version": "cifake"}),
        # dạng scripts.evaluate: cờ phải đúng bool True
        lambda a: _eval(a / "evaluation.json", accuracy_target={"value": 0.9, "passed": 1}),
        lambda a: _eval(a / "evaluation.json", accuracy_target={"value": 0.9, "passed": False}),
        lambda a: (a / "evaluation.json").write_text("{"),
        lambda a: (a / "evaluation.json").write_text("{}"),
        lambda a: (a / "evaluation.json").write_text("[]"),
        lambda a: (a / "metadata-audit.json").write_text("{}"),
        lambda a: (a / "metadata-audit.json").write_text("[]"),
        lambda a: (a / "unit.xml").write_text("<testsuites><oops"),
        *[lambda a, r=r: _cov(a / "coverage.xml", r) for r in ("1.5", "inf", "nan", "-0.2")],
        lambda a: _junit(a / "integration.xml", 3, '<testcase name="x"><error/></testcase>'),
        lambda a: (a / "soak-rss.json").write_text('{"rss_after_warmup_mb": 100, "rss_end_mb": 120}'),
        lambda a: _side(a / "load.jsonl", "rate_only"),
    ],
)  # fmt: skip
def test_bang_chung_xau_la_chua_dat(tmp_path, capsys, mutate):
    art, slo = _full(tmp_path)
    mutate(art)
    code, out = _run(art, slo, capsys)
    assert code == 1 and "[chưa đạt]" in out


def test_xfail_khong_tinh_la_skip(tmp_path, capsys):
    art, slo = _full(tmp_path)
    _junit(
        art / "unit.xml",
        20,
        '<testcase name="x"><skipped type="pytest.xfail"/></testcase>',
    )
    assert _run(art, slo, capsys)[0] == 0  # fmt: skip


def test_slo_approved_by_chuoi_rong_bi_tu_choi(tmp_path):
    for bad in ([""], ["  "], ["Lực", " "]):
        with pytest.raises(ValueError, match="approved_by"):
            check_performance.load_slo(_slo_file(tmp_path, approved_by=bad))


def test_evaluate_gate_file_hong_la_chua_dat_khong_nem_loi(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    for content in ("<a", "{", "{}", "[]", "null", "1"):
        for _, _, _, files, check in check_mvp_gates.gates(art, art / "slo.json")[:5]:
            for f in files:
                f.write_text(content)
            status, why = check_mvp_gates.evaluate_gate(files, check)
            assert status == check_mvp_gates.CHUA and why, (content, files)


def test_g03_voi_bao_cao_that_cua_models_evaluate(
    tmp_path,
    candidate,  # noqa: F811
):
    """evaluation.json do chính models.evaluate.evaluate ghi (dữ liệu tổng hợp, không mở holdout thật)."""
    from models.evaluate import evaluate, prepare_lock
    from tests.test_ml_release import approve

    labels, features, model = candidate
    lock, out = tmp_path / "protocol.json", tmp_path / "result"
    prepare_lock(labels, features, model, lock)
    approve(lock)
    report = evaluate(labels, features, model, lock, out)
    status, why = check_mvp_gates.evaluate_gate(
        [out / "evaluation.json"], lambda p: check_mvp_gates._accuracy(p[0])
    )
    want = (
        check_mvp_gates.DAT
        if report["quality"]["status"] == "pass"
        else check_mvp_gates.CHUA
    )
    assert status == want and "không đọc được" not in why
    # sửa cờ thành pass khi số đo dưới 90% vẫn phải bị từ chối
    bad = json.loads((out / "evaluation.json").read_text())
    bad["test"]["accuracy"], bad["quality"]["status"] = 0.5, "pass"
    (out / "evaluation.json").write_text(json.dumps(bad))
    assert (
        check_mvp_gates.evaluate_gate(
            [out / "evaluation.json"], lambda p: check_mvp_gates._accuracy(p[0])
        )[0]
        == check_mvp_gates.CHUA
    )


def test_g03_voi_bao_cao_that_cua_scripts_evaluate_val_la_chua_dat(
    tmp_path,
    locked,  # noqa: F811
):
    """scripts.evaluate --split val không có số đo test; GenImage test do script này từ chối."""
    from scripts import evaluate as ev

    labels, features, model, _ = locked
    out = tmp_path / "evaluation.json"
    ev.main(["--split", "val", "--output", str(out), "--labels", str(labels),
             "--features", str(features), "--model", str(model)])  # fmt: skip
    status, why = check_mvp_gates.evaluate_gate(
        [out], lambda p: check_mvp_gates._accuracy(p[0])
    )
    assert status == check_mvp_gates.CHUA and "test" in why


def test_g02_ba_trang_thai(tmp_path, capsys):
    art, slo = _full(tmp_path)
    _, out = _run(art, slo, capsys)
    assert "G02" in out and "[đạt]" in out  # hợp lệ, A_eff <= 0.55
    _write_audit(
        art, _audit_report(constant_features={"post": [f"f{i}" for i in range(13)]})
    )
    _, out = _run(art, slo, capsys)
    assert any("G02" in ln and "[chưa đạt]" in ln for ln in out.splitlines())  # rỗng
    (art / "metadata-audit.json").unlink()
    _, out = _run(art, slo, capsys)
    assert any("G02" in ln and "[thiếu bằng chứng]" in ln for ln in out.splitlines())


def test_g02_ban_sao_audit_that_la_chua_dat(tmp_path, capsys):
    """data/metadata_audit.json thật: 13/13 đặc trưng post hằng số nên G02 phải 'chưa đạt' (#134)."""
    art, slo = _full(tmp_path)
    real = Path(__file__).resolve().parents[1] / "data" / "metadata_audit.json"
    shutil.copy(real, art / "metadata-audit.json")
    code, out = _run(art, slo, capsys)
    assert code == 1
    assert any("G02" in ln and "[chưa đạt]" in ln for ln in out.splitlines())
