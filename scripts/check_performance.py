"""So số đo từ sidecar Locust với SLO đã ký (docs/performance/slo.json). Không tự tạo SLO.

Thoát 0 đạt, 1 không đạt SLO, 2 thiếu/hỏng đầu vào hoặc SLO thiếu trường (chỉ là baseline).
"""

import argparse
import json
import math
import sys
from pathlib import Path

from scripts.perf_report import MISSING, load_sidecar, summarize

SLO_DOMAIN = {
    "p95_ms_max": lambda v: v > 0,
    "rps200_min": lambda v: v >= 0,
    "error_ratio_max": lambda v: 0 <= v <= 1,
    "rss_growth_pct_max": lambda v: v >= 0,  # % RSS tăng sau warmup (AC-28, NFR-05)
}
SLO_KEYS = tuple(SLO_DOMAIN)
# Trường chữ T030 yêu cầu: tiêu chí recovery và workload/hardware tham chiếu (không có số mẫu).
SLO_TEXT = ("recovery_criterion",)
WORKLOAD_TEXT = ("profile", "payload_mix", "warmup", "hardware")
BASELINE_ONLY = "chỉ là baseline, không kết luận đạt SLA"
# scope -> kịch bản locust phải khớp meta của sidecar (chặn lấy run rate_only làm load)
SCOPE_SCENARIO = {"load": "baseline", "soak": "soak", "recovery": "recovery"}


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def load_slo(path: Path) -> dict:
    """Chỉ nhận SLO đã duyệt, đủ trường; mẫu có ô null/rỗng hoặc approved=false bị từ chối."""
    try:
        slo = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"chưa có SLO hợp lệ ({path}): {exc}") from exc
    if not isinstance(slo, dict):
        raise ValueError("SLO phải là object JSON")  # noqa: TRY004
    bad = [
        k for k, ok in SLO_DOMAIN.items() if not _is_num(slo.get(k)) or not ok(slo[k])
    ]
    bad += [k for k in SLO_TEXT if not _is_text(slo.get(k))]
    wl = slo.get("workload")
    wl = wl if isinstance(wl, dict) else {}
    bad += [f"workload.{k}" for k in WORKLOAD_TEXT if not _is_text(wl.get(k))]
    by = slo.get("approved_by")
    if not (isinstance(by, list) and by and all(_is_text(x) for x in by)):
        bad.append("approved_by")
    if not _is_text(slo.get("approved_date")):
        bad.append("approved_date")
    if bad:
        raise ValueError(f"SLO thiếu, null/rỗng hoặc sai miền: {', '.join(bad)}")
    if slo.get("approved") is not True:
        raise ValueError("SLO chưa được duyệt (approved phải là true)")
    return slo


def evaluate(summary: dict, slo: dict, check_rps: bool = True) -> list[str]:
    """Danh sách lý do không đạt; số đo thiếu cũng là không đạt."""
    fails = []
    p95 = summary["latency_200_ms"]["p95"]
    if p95 == MISSING or p95 > slo["p95_ms_max"]:
        fails.append(f"p95 của 200 = {p95} (ngưỡng {slo['p95_ms_max']} ms)")
    if check_rps and (
        summary["rps200"] == MISSING or summary["rps200"] < slo["rps200_min"]
    ):
        fails.append(f"RPS 200 = {summary['rps200']} (tối thiểu {slo['rps200_min']})")
    err = summary["error_ratio_excl_429"]
    if err == MISSING or err > slo["error_ratio_max"]:
        fails.append(
            f"tỉ lệ lỗi (không tính 429) = {err} (ngân sách {slo['error_ratio_max']})"
        )
    return fails


def evaluate_rss(path: Path, slo: dict) -> list[str]:
    """RSS tăng sau warmup. Định dạng {"rss_after_warmup_mb","rss_end_mb"} là giả định, xem docs/performance/README.md."""
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        a, b = d["rss_after_warmup_mb"], d["rss_end_mb"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError(f"RSS không đọc được ({path}): {exc}") from exc
    if not (_is_num(a) and _is_num(b) and a > 0 and b > 0):
        raise ValueError("RSS cần số dương hữu hạn")
    growth = (b - a) / a * 100
    if growth > slo["rss_growth_pct_max"]:
        return [f"RSS tăng {growth:.1f}% (tối đa {slo['rss_growth_pct_max']}%)"]
    return []


def run(
    sidecar: Path,
    slo_path: Path,
    scope: str = "load",
    rss: Path | None = None,
    warmup_seconds: float | None = None,
    warmup_requests: int | None = None,
) -> tuple[int, list[str]]:
    """(mã thoát, dòng thông báo). 2 = thiếu/hỏng/chưa duyệt, chỉ là baseline."""
    try:
        slo = load_slo(slo_path)
    except ValueError as exc:
        return 2, [f"LỖI: {exc}", f"Kết quả {BASELINE_ONLY}."]
    try:
        meta, records = load_sidecar(sidecar)
        want = SCOPE_SCENARIO[scope]
        if meta.get("scenario") != want:
            raise ValueError(
                f"sidecar scenario={meta.get('scenario')!r}, scope {scope} cần {want!r}"
            )
        summary = summarize(meta, records, warmup_seconds, warmup_requests)
        if scope == "soak" and rss is None:
            raise ValueError("scope soak cần --rss (RSS sau warmup và cuối soak)")
        rss_fails = evaluate_rss(rss, slo) if scope == "soak" else []
    except ValueError as exc:
        return 2, [f"LỖI: {exc}"]
    fails = evaluate(summary, slo, check_rps=scope != "recovery") + rss_fails
    return (1 if fails else 0), [f"FAIL: {f}" for f in fails] + [
        "KHÔNG ĐẠT SLO" if fails else "ĐẠT SLO"
    ]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm hiệu năng theo SLO đã ký")
    ap.add_argument("--sidecar", type=Path, required=True)
    ap.add_argument("--slo", type=Path, default=Path("docs/performance/slo.json"))
    ap.add_argument("--scope", choices=tuple(SCOPE_SCENARIO), default="load")
    ap.add_argument("--rss", type=Path, default=None, help="bắt buộc với scope soak")
    ap.add_argument("--warmup-seconds", type=float, default=None)
    ap.add_argument("--warmup-requests", type=int, default=None)
    a = ap.parse_args(argv)
    code, lines = run(
        a.sidecar, a.slo, a.scope, a.rss, a.warmup_seconds, a.warmup_requests
    )
    for line in lines:
        print(line, file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
