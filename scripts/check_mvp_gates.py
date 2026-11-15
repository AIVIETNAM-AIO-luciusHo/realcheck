"""Gom bằng chứng nghiệm thu core (MVP-12/KAN-59): bảng gate, file bằng chứng, trạng thái.

Nguồn gate: spec 000 (SC-01..SC-05, AC-13..29) và DoD của tasks.md T021-T031; nội dung task Jira
KAN-59 không có trong repo. Trạng thái: "đạt" / "chưa đạt" / "thiếu bằng chứng". Thiếu hoặc rỗng
một file bằng chứng thì không bao giờ là "đạt". Thoát 0 chỉ khi mọi gate đạt, 1 nếu không.
"""

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.check_performance import load_slo, run
from scripts.check_release_audit import problems, vacuous

DAT, CHUA, THIEU = "đạt", "chưa đạt", "thiếu bằng chứng"
MIN_UNIT_TESTS = 15  # AC-27
MIN_COVERAGE = 0.70  # AC-27
MIN_ACCURACY = 0.90  # AC-25


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _junit(path: Path, min_tests: int) -> str | None:
    """None nếu đạt, ngược lại lý do. xfail ghi nhận giới hạn đã biết nên không tính là skip."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    bad = [
        c
        for c in cases
        if c.find("failure") is not None
        or c.find("error") is not None
        or any(s.get("type") != "pytest.xfail" for s in c.findall("skipped"))
    ]
    if len(cases) < min_tests:
        return f"chỉ {len(cases)} test (cần >= {min_tests})"
    return f"{len(bad)} test fail/error/skip" if bad else None


def _unit(p: list[Path]) -> str | None:
    if reason := _junit(p[0], MIN_UNIT_TESTS):
        return reason
    rate = float(ET.parse(p[1]).getroot().get("line-rate", "nan"))
    if not _finite(rate) or not 0 <= rate <= 1:
        return f"line-rate = {rate} không hợp lệ"
    return None if rate >= MIN_COVERAGE else f"coverage {rate:.1%} < 70%"


def _json_is(path: Path, *keys: str, want):
    d = json.loads(path.read_text(encoding="utf-8"))
    for k in keys:
        d = d[k]
    return (
        None
        if d == want and type(d) is type(want)
        else f"{'.'.join(keys)} = {d!r}, cần {want!r}"
    )


def _accuracy(path: Path) -> str | None:
    """SC-04: đánh giá GenImage trên split test. Đọc cả hai nguồn ghi evaluation.json thật:
    models.evaluate (`quality.status`) và scripts.evaluate (`accuracy_target.passed`, chỉ khi
    split=test). Cờ phải đúng kiểu và số liệu `test` phải tự đạt >= 90%."""
    d = json.loads(path.read_text(encoding="utf-8"))
    if d["dataset"]["version"] != "genimage":
        return f"dataset = {d['dataset']['version']!r}, SC-04 cần 'genimage'"
    t = d["test"]
    if not isinstance(t, dict):
        return f"không có số đo test (split = {d.get('split')!r})"
    acc = t["accuracy"]
    if (
        not _finite(acc)
        or not 0 <= acc <= 1
        or not isinstance(t["n"], int)
        or t["n"] < 1
    ):
        return "test.accuracy/test.n không hợp lệ"
    if acc < MIN_ACCURACY:
        return f"test.accuracy = {acc} < {MIN_ACCURACY}"
    if "accuracy_target" in d:
        return _json_is(path, "accuracy_target", "passed", want=True)
    return _json_is(path, "quality", "status", want="pass")


def _audit(path: Path) -> str | None:
    """G02 dùng chính logic của check_release_audit với --fail-on-vacuous: audit rỗng (mọi đặc
    trưng post hằng số, A_eff = 0.5 không chứng minh dữ liệu sạch) là "chưa đạt"."""
    report = json.loads(path.read_text(encoding="utf-8"))
    found = problems(report)
    if vacuous(report):
        found.append(
            "audit rỗng: mọi đặc trưng post là hằng số, không chứng minh dữ liệu sạch"
        )
    return "; ".join(found) or None


def _perf(scope: str):
    def check(p: list[Path]) -> str | None:
        rss = p[2] if scope == "soak" else None
        code, lines = run(p[0], p[1], scope, rss)
        return None if code == 0 else "; ".join(lines)

    return check


def gates(art: Path, slo: Path):
    """(id, nội dung, nguồn, [file bằng chứng], hàm kiểm -> None nếu đạt hoặc lý do)."""
    return [
        ("G01", "Ruff + pytest >=15 ca + coverage app >=70%", "AC-27, T021",
         [art / "unit.xml", art / "coverage.xml"], _unit),
        ("G02", "Post metadata audit A_eff <= 0.55", "SC-02, AC-13..17, T022",
         [art / "metadata-audit.json"],
         lambda p: _audit(p[0])),
        ("G03", "Accuracy GenImage model-test >= 90%", "SC-04, AC-25",
         [art / "evaluation.json"],
         lambda p: _accuracy(p[0])),
        ("G04", "Integration Nginx/recovery (JUnit, không fail/skip)", "SC-01, AC-09/10/19..24, T025",
         [art / "integration.xml"], lambda p: _junit(p[0], 1)),
        ("G05", "UI qua gateway, session độc lập (JUnit)", "SC-01, AC-29, T026",
         [art / "ui-gateway.xml"], lambda p: _junit(p[0], 1)),
        ("G06", "SLO đã duyệt và ký", "SC-05, AC-28, T030",
         [slo], lambda p: _perf_slo(p[0])),
        ("G07", "Load đạt SLO", "AC-28, T031",
         [art / "load.jsonl", slo], _perf("load")),
        ("G08", "Soak đạt SLO + RSS", "AC-28, T031",
         [art / "soak.jsonl", slo, art / "soak-rss.json"], _perf("soak")),
        ("G09", "Recovery đạt p95/lỗi theo SLO", "AC-28, T031",
         [art / "recovery.jsonl", slo], _perf("recovery")),
    ]  # fmt: skip


def _perf_slo(path: Path) -> str | None:
    try:
        load_slo(path)
    except ValueError as exc:
        return str(exc)
    return None


def evaluate_gate(files: list[Path], check) -> tuple[str, str]:
    missing = [f.as_posix() for f in files if not f.is_file() or f.stat().st_size == 0]
    if missing:
        return THIEU, "thiếu/rỗng: " + ", ".join(missing)
    try:
        reason = check(files)
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        ET.ParseError,
    ) as exc:
        return CHUA, f"không đọc được bằng chứng: {exc}"
    return (CHUA, reason) if reason else (DAT, "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bảng gate nghiệm thu core MVP-12")
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    ap.add_argument("--slo", type=Path, default=Path("docs/performance/slo.json"))
    a = ap.parse_args(argv)
    results = [
        (gid, title, src, files, *evaluate_gate(files, check))
        for gid, title, src, files, check in gates(a.artifacts, a.slo)
    ]
    for gid, title, src, files, status, why in results:
        print(f"{gid} [{status}] {title} ({src})")
        print(f"     bằng chứng: {', '.join(f.as_posix() for f in files)}")
        if why:
            print(f"     lý do: {why}")
    ok = all(r[4] == DAT for r in results)
    print("TẤT CẢ GATE ĐẠT" if ok else "CHƯA ĐỦ ĐIỀU KIỆN NGHIỆM THU CORE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
