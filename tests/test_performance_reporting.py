"""scripts/perf_report.py và scripts/check_performance.py trên sidecar tổng hợp (không cần locust/mạng)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_performance, perf_report

T0 = 1000.0


def _req(t, outcome, status, latency_ms, code=None):
    return {
        "type": "req",
        "t": T0 + t,
        "outcome": outcome,
        "status": status,
        "error_code": code,
        "latency_ms": latency_ms,
    }


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return path


def _mixed():
    rows = [{"type": "meta", "commit": "abc123"}]
    # 10 request 200 với latency 100..1000 ms, mỗi giây một request
    rows += [_req(i, "200", 200, 100 * (i + 1)) for i in range(10)]
    rows += [_req(10 + i, "429", 429, 5, "RATE_LIMITED") for i in range(5)]
    rows += [
        _req(15, "503", 503, 20, "SERVICE_BUSY"),
        _req(16, "504", 504, 30000, "MODEL_TIMEOUT"),
    ]
    return rows


def _slo(tmp_path, **over):
    slo = {"p95_ms_max": 2000, "rps200_min": 0.1, "error_ratio_max": 0.5} | over
    p = tmp_path / "slo.json"
    p.write_text(json.dumps(slo), encoding="utf-8")
    return p


def test_classify_tach_outcome():
    c = perf_report.classify
    assert [c(200), c(200, False), c(429), c(503), c(504), c(500), c(502), c(0), c(404)] == [
        "200", "invalid200", "429", "503", "504", "5xx", "5xx", "other", "other",
    ]  # fmt: skip


def test_percentile_chi_tren_200(tmp_path):
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", _mixed()))
    s = perf_report.summarize(meta, recs)
    # nearest-rank trên {100..1000}: p50=500, p95=1000; 504 30000 ms không được lọt vào
    assert s["latency_200_ms"] == {"p50": 500, "p95": 1000, "p99": 1000}
    assert (
        s["counts"]["429"] == 5 and s["counts"]["503"] == 1 and s["counts"]["504"] == 1
    )
    assert s["meta"]["commit"] == "abc123" and s["meta"]["image"] == perf_report.MISSING


def test_rps_thanh_cong_khong_cong_429(tmp_path):
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", _mixed()))
    s = perf_report.summarize(meta, recs)
    assert s["offered_rps"] == pytest.approx(17 / s["window_s"])
    assert s["rps200"] == pytest.approx(10 / s["window_s"])
    assert s["rps200"] < s["offered_rps"]
    # lỗi bất ngờ = 2 / (17 - 5 request 429)
    assert s["error_ratio_excl_429"] == pytest.approx(2 / 12)


def test_chi_429_khong_co_rps_thanh_cong(tmp_path):
    rows = [_req(i * 0.1, "429", 429, 3) for i in range(20)]
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", rows))
    s = perf_report.summarize(meta, recs)
    assert s["rps200"] == 0
    assert s["latency_200_ms"]["p95"] == perf_report.MISSING
    assert s["counts"]["200"] == 0 and s["counts"]["429"] == 20
    # SLO có RPS tối thiểu 1 phải thất bại dù offered rps rất cao
    slo = check_performance.load_slo(_slo(tmp_path))
    assert check_performance.evaluate(s, slo)


def test_warmup_giay_va_so_request_bi_loai(tmp_path):
    rows = [_req(0, "200", 200, 9000), _req(1, "200", 200, 9000)]
    rows += [_req(10 + i, "200", 200, 100) for i in range(4)]
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", rows))
    by_sec = perf_report.summarize(meta, recs, warmup_seconds=5)
    assert by_sec["measured_requests"] == 4 and by_sec["warmup_skipped_requests"] == 2
    assert by_sec["latency_200_ms"]["p99"] == 100
    by_n = perf_report.summarize(meta, recs, warmup_requests=2)
    assert by_n["latency_200_ms"]["p99"] == 100
    assert perf_report.summarize(meta, recs)["latency_200_ms"]["p99"] == 9000


def test_warmup_lay_tu_meta_neu_khong_co_co(tmp_path):
    rows = [
        {"type": "meta", "warmup_seconds": 5},
        _req(0, "200", 200, 9000),
        _req(10, "200", 200, 50),
    ]
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", rows))
    assert perf_report.summarize(meta, recs)["measured_requests"] == 1


def test_warmup_het_request_ghi_thieu(tmp_path):
    meta, recs = perf_report.load_sidecar(
        _write(tmp_path / "s.jsonl", [_req(0, "200", 200, 5)])
    )
    s = perf_report.summarize(meta, recs, warmup_requests=1)
    assert s["measured_requests"] == 0
    assert (
        s["rps200"] == perf_report.MISSING and s["offered_rps"] == perf_report.MISSING
    )


@pytest.mark.parametrize("content", ["", "\n\n", '{"type":"meta"}\n', "khong phai json\n", "[1]\n",
                                     '{"type":"req","t":1,"outcome":"200"}\n',
                                     '{"type":"req","t":1,"outcome":"zzz","latency_ms":1}\n',
                                     '{"type":"lạ"}\n'])  # fmt: skip
def test_sidecar_rong_hoac_hong_bi_tu_choi(tmp_path, content):
    p = tmp_path / "s.jsonl"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        perf_report.load_sidecar(p)
    assert perf_report.main([str(p)]) == 2


def test_sidecar_khong_ton_tai(tmp_path):
    assert perf_report.main([str(tmp_path / "none.jsonl")]) == 2


def test_check_performance_thieu_slo_thoat_khac_0(tmp_path, capsys):
    side = _write(tmp_path / "s.jsonl", _mixed())
    assert (
        check_performance.main(
            ["--sidecar", str(side), "--slo", str(tmp_path / "none.json")]
        )
        == 2
    )
    assert "chỉ là baseline, không kết luận đạt SLA" in capsys.readouterr().err


@pytest.mark.parametrize("missing", check_performance.SLO_KEYS)
def test_check_performance_slo_thieu_truong(tmp_path, capsys, missing):
    side = _write(tmp_path / "s.jsonl", _mixed())
    slo = {"p95_ms_max": 2000, "rps200_min": 0.1, "error_ratio_max": 0.5}
    del slo[missing]
    (tmp_path / "slo.json").write_text(json.dumps(slo), encoding="utf-8")
    assert (
        check_performance.main(
            ["--sidecar", str(side), "--slo", str(tmp_path / "slo.json")]
        )
        == 2
    )
    assert missing in capsys.readouterr().err


def test_check_performance_slo_khong_phai_json(tmp_path):
    (tmp_path / "slo.json").write_text("{", encoding="utf-8")
    side = _write(tmp_path / "s.jsonl", _mixed())
    assert (
        check_performance.main(
            ["--sidecar", str(side), "--slo", str(tmp_path / "slo.json")]
        )
        == 2
    )


def test_check_performance_dat_va_khong_dat(tmp_path):
    side = _write(tmp_path / "s.jsonl", _mixed())
    ok = _slo(tmp_path, p95_ms_max=1000, rps200_min=0.1, error_ratio_max=0.5)
    assert check_performance.main(["--sidecar", str(side), "--slo", str(ok)]) == 0
    # error ratio không tính 429: (1+1)/(17-5)=1/6; ngân sách 0.1 phải thất bại
    bad_err = _slo(tmp_path, error_ratio_max=0.1)
    assert check_performance.main(["--sidecar", str(side), "--slo", str(bad_err)]) == 1
    bad_p95 = _slo(tmp_path, p95_ms_max=999)
    assert check_performance.main(["--sidecar", str(side), "--slo", str(bad_p95)]) == 1


def test_check_performance_sidecar_hong(tmp_path):
    side = tmp_path / "s.jsonl"
    side.write_text("rác\n", encoding="utf-8")
    assert (
        check_performance.main(["--sidecar", str(side), "--slo", str(_slo(tmp_path))])
        == 2
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"p95_ms_max": float("nan")},
        {"p95_ms_max": float("inf")},
        {"rps200_min": float("-inf")},
        {"error_ratio_max": float("nan")},
        {"p95_ms_max": True},
        {"rps200_min": False},
        {"p95_ms_max": "2000"},
        {"p95_ms_max": 0},
        {"p95_ms_max": -5},
        {"rps200_min": -1},
        {"error_ratio_max": -0.1},
        {"error_ratio_max": 1.5},
    ],
)
def test_slo_gia_tri_khong_hop_le_thoat_2(tmp_path, capsys, bad):
    side = _write(tmp_path / "s.jsonl", _mixed())
    slo = {"p95_ms_max": 2000, "rps200_min": 0.1, "error_ratio_max": 0.5} | bad
    p = tmp_path / "slo.json"
    p.write_text(
        json.dumps(slo), encoding="utf-8"
    )  # json ghi NaN/Infinity, loads đọc lại được
    assert check_performance.main(["--sidecar", str(side), "--slo", str(p)]) == 2
    assert "chỉ là baseline, không kết luận đạt SLA" in capsys.readouterr().err


def test_slo_bien_hop_le_van_qua(tmp_path):
    p = _slo(tmp_path, p95_ms_max=0.001, rps200_min=0, error_ratio_max=1)
    assert check_performance.load_slo(p)["rps200_min"] == 0


def _good_summary():
    return {
        "latency_200_ms": {"p95": 100},
        "rps200": 5.0,
        "error_ratio_excl_429": 0.0,
    }


SLO_OK = {"p95_ms_max": 1000, "rps200_min": 1, "error_ratio_max": 0.1}


def test_evaluate_dat_khi_so_do_tot():
    assert check_performance.evaluate(_good_summary(), SLO_OK) == []


def test_evaluate_thieu_p95_la_khong_dat():
    s = _good_summary()
    s["latency_200_ms"]["p95"] = perf_report.MISSING
    assert len(check_performance.evaluate(s, SLO_OK)) == 1


def test_evaluate_thieu_rps200_la_khong_dat():
    s = _good_summary() | {"rps200": perf_report.MISSING}
    assert len(check_performance.evaluate(s, SLO_OK)) == 1


def test_evaluate_thieu_ti_le_loi_la_khong_dat():
    s = _good_summary() | {"error_ratio_excl_429": perf_report.MISSING}
    assert len(check_performance.evaluate(s, SLO_OK)) == 1


def test_window_la_tu_request_dau_den_khi_request_cuoi_ket_thuc(tmp_path):
    rows = [_req(0, "200", 200, 100), _req(4, "200", 200, 2000)]
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", rows))
    s = perf_report.summarize(meta, recs)
    assert s["window_s"] == pytest.approx(6.0)  # 4 + 2s - 0
    assert s["rps200"] == pytest.approx(2 / 6.0)


def test_invalid200_tinh_vao_ti_le_loi(tmp_path):
    rows = [
        _req(0, "200", 200, 10),
        _req(1, "invalid200", 200, 10),
        _req(2, "429", 429, 1),
    ]
    meta, recs = perf_report.load_sidecar(_write(tmp_path / "s.jsonl", rows))
    s = perf_report.summarize(meta, recs)
    assert s["counts"]["200"] == 1 and s["counts"]["invalid200"] == 1
    assert s["error_ratio_excl_429"] == pytest.approx(0.5)
    assert s["rps200"] == pytest.approx(
        1 / s["window_s"]
    )  # invalid200 không phải thành công


@pytest.mark.parametrize("lat", [-1, -0.001, float("nan"), float("inf")])
def test_latency_am_hoac_khong_huu_han_la_dong_hong(tmp_path, lat):
    p = _write(tmp_path / "s.jsonl", [_req(0, "200", 200, 5), _req(1, "200", 200, lat)])
    with pytest.raises(ValueError):
        perf_report.load_sidecar(p)
    assert perf_report.main([str(p)]) == 2


def test_latency_bang_0_van_hop_le(tmp_path):
    _meta, recs = perf_report.load_sidecar(
        _write(tmp_path / "s.jsonl", [_req(0, "200", 200, 0)])
    )
    assert recs[0]["latency_ms"] == 0


@pytest.mark.parametrize(
    "flag", [["--warmup-requests", "-1"], ["--warmup-seconds", "-1"]]
)
def test_warmup_am_bi_tu_choi(tmp_path, flag):
    side = _write(tmp_path / "s.jsonl", _mixed())
    assert perf_report.main([str(side), *flag]) == 2
    assert (
        check_performance.main(
            ["--sidecar", str(side), "--slo", str(_slo(tmp_path)), *flag]
        )
        == 2
    )


# Hai bản phân loại (locustfile._outcome/_valid và perf_report.classify / pydantic AnalyzeResponse)
# phải khớp. locust không nằm trong requirements.txt chính nên test này chỉ chạy khi có locust,
# và chạy trong subprocess vì import locust monkey-patch gevent toàn process.
LOCUSTFILE = Path(__file__).resolve().parent.parent / "locust" / "locustfile.py"
VALID_BODY = {"verdict": "uncertain", "score": 0.5, "exif": "x", "reason": "y"}
BODIES = [
    VALID_BODY,
    VALID_BODY | {"score": 0},
    VALID_BODY | {"score": 1},
    VALID_BODY | {"score": 1.0001},
    VALID_BODY | {"score": -0.1},
    VALID_BODY | {"score": float("nan")},
    VALID_BODY | {"score": float("inf")},
    VALID_BODY | {"score": True},
    VALID_BODY | {"score": "0.5"},
    VALID_BODY | {"verdict": "khac"},
    VALID_BODY | {"exif": ""},
    VALID_BODY | {"extra": 1},
    {"verdict": "uncertain"},
    None,
    [1],
]
STATUSES = [
    (s, v)
    for s in (200, 400, 404, 413, 429, 499, 500, 502, 503, 504, 599, 0)
    for v in (True, False)
]


def _locust_probe() -> bool:
    # find_spec/importorskip bị thư mục locust/ của repo (namespace package) đánh lừa; -I + cwd lạ
    # buộc python chỉ thấy locust thật trong site-packages.
    r = subprocess.run(
        [sys.executable, "-I", "-c", "import locust.env"],
        capture_output=True,
        cwd="/",
        check=False,
    )
    return r.returncode == 0


@pytest.fixture(scope="module")
def need_locust():
    if not _locust_probe():
        pytest.skip(
            "locust không nằm trong requirements.txt chính (CI nhẹ); "
            "cài bằng `pip install -r locust/requirements.txt` để chạy test này"
        )


def _run_lf(code: str, payload=None) -> dict:
    """Chạy `code` trong subprocess sạch (import locust monkey-patch gevent) với module `m` = locustfile."""
    driver = (
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('lf', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "inp = json.loads(sys.stdin.read())\n" + code
    )
    out = subprocess.run(
        [sys.executable, "-I", "-c", driver, str(LOCUSTFILE)],
        input=json.dumps(payload), capture_output=True, text=True, cwd="/", check=True,
    )  # fmt: skip
    return json.loads(out.stdout)


_MIXES = ["jpeg=0,png=0", "jpeg=-1,png=2", "jpeg=nan", "jpeg", "khac=1", "jpeg=x"]
_DRIVER_CODE = """
import argparse
def mix(t):
    try:
        m._parse_mix(t, {"jpeg": 1, "png": 1})
        return False
    except SystemExit as e:
        return "RC_MIX" in str(e)
p = argparse.ArgumentParser(); m._args(p)
print(json.dumps({
    "valid": [m._valid(b) for b in inp["bodies"]],
    "outcome": [m._outcome(s, v) for s, v in inp["statuses"]],
    "default": p.parse_args([]).rc_scenario,
    "wait_rate_only": list(m._wait_bounds("rate_only")),
    "wait_baseline": list(m._wait_bounds("baseline")),
    "mix_bad": [mix(t) for t in inp["mixes"]],
    "mix_ok": [m._parse_mix("jpeg=40,png=0", {"jpeg": 1, "png": 1}), m._parse_mix("", {"jpeg": 1, "png": 1})],
}))
"""


def test_locustfile_voi_locust_that(need_locust):
    """Một test gộp (một skip duy nhất khi thiếu locust): phân loại, schema, kịch bản, wait, RC_MIX."""
    from pydantic import ValidationError

    from app.schemas import AnalyzeResponse

    got = _run_lf(
        _DRIVER_CODE, {"bodies": BODIES, "statuses": STATUSES, "mixes": _MIXES}
    )

    def api_ok(body):
        try:
            AnalyzeResponse.model_validate(body)
        except ValidationError:
            return False
        return True

    # Khác biệt có chủ ý: locust chặt hơn pydantic ở score là bool hoặc chuỗi số (pydantic lax chấp nhận).
    def locust_expected(body):
        score = body.get("score") if isinstance(body, dict) else None
        return api_ok(body) and not isinstance(score, (bool, str))

    assert got["valid"] == [locust_expected(b) for b in BODIES]
    assert got["outcome"] == [perf_report.classify(s, v) for s, v in STATUSES]
    assert got["default"] == "baseline"  # mặc định không được là rate_only
    assert got["wait_rate_only"] == [
        0,
        0,
    ]  # rate_only bắt buộc wait=0, meta dùng cùng hàm
    assert got["wait_baseline"] == [1, 3]
    assert got["mix_bad"] == [True] * len(
        _MIXES
    )  # mọi mix sai bị từ chối với thông báo RC_MIX
    assert got["mix_ok"] == [{"jpeg": 40.0, "png": 0.0}, {"jpeg": 1.0, "png": 1.0}]


def test_slo_khong_phai_object(tmp_path):
    (tmp_path / "slo.json").write_text("[1, 2]", encoding="utf-8")
    side = _write(tmp_path / "s.jsonl", _mixed())
    assert (
        check_performance.main(
            ["--sidecar", str(side), "--slo", str(tmp_path / "slo.json")]
        )
        == 2
    )


def test_conf_ghim_dung_kich_ban():
    conf = LOCUSTFILE.parent
    assert "rc-scenario = rate_only" in (conf / "rate_only.conf").read_text(
        encoding="utf-8"
    )
    assert "rc-scenario = baseline" in (conf / "baseline.conf").read_text(
        encoding="utf-8"
    )
    assert "rc-scenario" not in (conf / "baseline.conf").read_text(
        encoding="utf-8"
    ).replace("rc-scenario = baseline", "")


@pytest.mark.parametrize(
    "flag", [["--warmup-seconds", "nan"], ["--warmup-seconds", "inf"]]
)
def test_warmup_khong_huu_han_bi_tu_choi(tmp_path, flag):
    side = _write(tmp_path / "s.jsonl", _mixed())
    assert perf_report.main([str(side), *flag]) == 2
    assert (
        check_performance.main(
            ["--sidecar", str(side), "--slo", str(_slo(tmp_path)), *flag]
        )
        == 2
    )
