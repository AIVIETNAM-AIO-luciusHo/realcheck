"""Release checker audit: chặn đúng các ca của chính sách 2026-11-12 (dữ liệu tổng hợp)."""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_release_audit as cra

ROOT = Path(__file__).resolve().parents[1]
VALID = {"valid": True, "test_counts": {"0": 120, "1": 130}, "a_eff": 0.5}
GOOD = {
    "n_features": 13,
    "constant_features": {"post": ["format"]},
    "slices": {"all": {"raw": VALID, "post": VALID}},
    "controls": {"positive": {"a_eff": 1.0}, "negative": {"a_eff": 0.5}},
}


def report(**edit):
    r = copy.deepcopy(GOOD)
    for path, v in edit.items():
        d = r
        *head, last = path.split("__")
        for k in head:
            d = d[k]
        d[last] = v
    return {"cifake": r, "gate": {"max_a_eff": 0.55, "passed": True}}


def test_bao_cao_tot_dat():
    assert cra.problems(report()) == []


@pytest.mark.parametrize(
    "edit",
    [
        {"slices__all__post": {**VALID, "a_eff": 0.56}},
        {"slices__all__post": {"valid": False, "test_counts": {"0": 5}}},
        {"slices__all__post": {**VALID, "test_counts": {"0": 120}}},
        {"slices__all__post": {**VALID, "a_eff": float("nan")}},
        {"slices__all__post": {**VALID, "valid": False}},  # đủ 2 lớp nhưng valid=false
        {"slices__all__post": {**VALID, "a_eff": 0.3}},
        {"slices__all__post": {**VALID, "a_eff": 1.2}},
        {"slices__all__post": {**VALID, "a_eff": -0.1}},
        {"controls__negative": {"a_eff": 0.3}},
        {"controls__positive": {"a_eff": 1.7}},
        {"controls__positive": {"a_eff": 0.9}},
        {"controls__positive": {"a_eff": float("nan")}},
        {"controls__negative": {"a_eff": 0.7}},
        {"controls__negative": {}},
    ],
)
def test_ca_bi_chan(edit):
    assert cra.problems(report(**edit))


@pytest.mark.parametrize("a", [0.5, 0.55, 1.0 - 1e-12])
def test_bien_con_dat(a):
    # 1.0 chỉ hợp lệ cho control dương; slice post > 0.55 vẫn chặn riêng
    r = report(slices__all__post={**VALID, "a_eff": a})
    assert (cra.problems(r) == []) == (a <= 0.55)


def test_bien_khoang_aeff_1_0_va_0_5():
    assert cra.problems(report(controls__positive={"a_eff": 1.0})) == []
    assert cra.problems(report(controls__negative={"a_eff": 0.5})) == []
    msg = cra.problems(report(slices__all__post={**VALID, "a_eff": 0.3}))[0]
    assert "ngoài [0.5, 1.0]" in msg


def test_thieu_slice_all():
    r = report()
    r["cifake"]["slices"] = {"real_vs_x": r["cifake"]["slices"]["all"]}
    assert any("slice 'all'" in p for p in cra.problems(r))


def run(*args):
    return subprocess.run(
        [sys.executable, "scripts/check_release_audit.py", *args],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",  # Windows mặc định cp1252, không giải mã được tiếng Việt
        env={**os.environ, "PYTHONUTF8": "1"},
    )


def test_ma_thoat(tmp_path):
    ok, bad = tmp_path / "ok.json", tmp_path / "bad.json"
    ok.write_text(json.dumps(report()))
    bad.write_text(json.dumps(report(slices__all__post={**VALID, "a_eff": 0.9})))
    assert run(str(ok)).returncode == 0
    assert run(str(bad)).returncode == 1
    assert run(str(tmp_path / "none.json")).returncode == 2
    (tmp_path / "x.json").write_text("{}")  # thiếu bộ dữ liệu: bị chặn
    assert run(str(tmp_path / "x.json")).returncode == 1
    (tmp_path / "y.json").write_text('{"a": {}}')  # sai cấu trúc: đầu vào hỏng
    assert run(str(tmp_path / "y.json")).returncode == 2


ALL_CONST = {"constant_features__post": [f"f{i}" for i in range(13)]}


def test_hang_so_la_vacuous_khong_chan_mac_dinh(tmp_path):
    assert cra.problems(report(**ALL_CONST)) == []
    assert cra.vacuous(report(**ALL_CONST)) == ["cifake"]
    assert cra.vacuous(report()) == []
    f = tmp_path / "v.json"
    f.write_text(json.dumps(report(**ALL_CONST)))
    r = run(str(f))
    assert r.returncode == 0
    assert "CẢNH BÁO MẠNH" in r.stdout and '"vacuous": true' in r.stdout
    assert "Release audit: ĐẠT NHƯNG RỖNG" in r.stdout
    assert "không chứng minh dữ liệu sạch" in r.stdout


def test_fail_on_vacuous_chan(tmp_path):
    f = tmp_path / "v.json"
    f.write_text(json.dumps(report(**ALL_CONST)))
    r = run("--fail-on-vacuous", str(f))
    assert r.returncode == 1
    assert "Release audit: BỊ CHẶN" in r.stdout
    f.write_text(json.dumps(report()))  # không rỗng: cờ không ảnh hưởng
    r = run("--fail-on-vacuous", str(f))
    assert r.returncode == 0
    assert "Release audit: ĐẠT\n" in r.stdout
    assert "RỖNG" not in r.stdout


def flags(r):
    return json.loads(next(l for l in r.stdout.splitlines() if l.startswith("{")))


def test_khoa_blocked_dung_tung_ca(tmp_path):
    f = tmp_path / "r.json"
    cases = [
        (report(), (), {"vacuous": False, "blocked": False}),
        (report(**ALL_CONST), (), {"vacuous": True, "blocked": False}),
        (
            report(**ALL_CONST),
            ("--fail-on-vacuous",),
            {"vacuous": True, "blocked": True},
        ),
        (
            report(slices__all__post={**VALID, "a_eff": 0.9}),
            (),
            {"vacuous": False, "blocked": True},
        ),
        (
            report(**ALL_CONST, controls__positive={"a_eff": 1.7}),
            (),
            {"vacuous": True, "blocked": True},
        ),
    ]
    for rep, args, want in cases:
        f.write_text(json.dumps(rep))
        assert flags(run(*args, str(f))) == want


def test_bao_cao_cu_thieu_n_features_cung_ket_luan_voi_bao_cao_moi():
    allc = {"constant_features__post": list(cra.FEATURES)}
    new = report(**allc)
    old = report(**allc)
    del old["cifake"]["n_features"]
    assert cra.vacuous(new) == cra.vacuous(old) == ["cifake"]
    assert cra.problems(new) == cra.problems(old) == []
    part = report(constant_features__post=list(cra.FEATURES[:-1]))
    del part["cifake"]["n_features"]
    assert cra.vacuous(part) == []  # thiếu một đặc trưng: không rỗng


def test_features_khop_cot_extract(tmp_path):
    from PIL import Image

    from scripts import metadata_audit as ma

    p = tmp_path / "a.jpg"
    Image.new("RGB", (8, 8)).save(p)
    assert set(ma.extract(str(p))) == set(ma.FEATURES)


REAL = ROOT / "data" / "metadata_audit.json"


@pytest.mark.skipif(not REAL.is_file(), reason="chưa có báo cáo audit thật trong repo")
def test_bao_cao_that_trong_repo_doc_duoc(tmp_path):
    f = tmp_path / "metadata_audit.json"
    f.write_bytes(REAL.read_bytes())
    real = json.loads(f.read_text())
    assert "n_features" not in real["cifake"]  # báo cáo cũ, tạo trước khóa n_features
    r = run(str(f))
    assert r.returncode == 0, r.stdout
    for ds in ("cifake", "genimage"):  # cả hai bộ: 13/13 đặc trưng post hằng số
        assert f"CẢNH BÁO MẠNH: {ds}:" in r.stdout
    assert "Release audit: ĐẠT NHƯNG RỖNG" in r.stdout
    assert flags(r) == {"vacuous": True, "blocked": False}
    r = run("--fail-on-vacuous", str(f))
    assert r.returncode == 1
    assert flags(r) == {"vacuous": True, "blocked": True}
