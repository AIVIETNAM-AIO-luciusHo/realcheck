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
}
SLO_KEYS = tuple(SLO_DOMAIN)
BASELINE_ONLY = "chỉ là baseline, không kết luận đạt SLA"


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def load_slo(path: Path) -> dict:
    try:
        slo = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"chưa có SLO hợp lệ ({path}): {exc}") from exc
    if not isinstance(slo, dict):
        raise ValueError("SLO phải là object JSON")  # noqa: TRY004
    bad = [
        k for k, ok in SLO_DOMAIN.items() if not _is_num(slo.get(k)) or not ok(slo[k])
    ]
    if bad:
        raise ValueError(f"SLO thiếu, không hữu hạn hoặc sai miền: {', '.join(bad)}")
    return slo


def evaluate(summary: dict, slo: dict) -> list[str]:
    """Danh sách lý do không đạt; số đo thiếu cũng là không đạt."""
    fails = []
    p95 = summary["latency_200_ms"]["p95"]
    if p95 == MISSING or p95 > slo["p95_ms_max"]:
        fails.append(f"p95 của 200 = {p95} (ngưỡng {slo['p95_ms_max']} ms)")
    if summary["rps200"] == MISSING or summary["rps200"] < slo["rps200_min"]:
        fails.append(f"RPS 200 = {summary['rps200']} (tối thiểu {slo['rps200_min']})")
    err = summary["error_ratio_excl_429"]
    if err == MISSING or err > slo["error_ratio_max"]:
        fails.append(
            f"tỉ lệ lỗi (không tính 429) = {err} (ngân sách {slo['error_ratio_max']})"
        )
    return fails


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Kiểm hiệu năng theo SLO đã ký")
    ap.add_argument("--sidecar", type=Path, required=True)
    ap.add_argument("--slo", type=Path, default=Path("docs/performance/slo.json"))
    ap.add_argument("--warmup-seconds", type=float, default=None)
    ap.add_argument("--warmup-requests", type=int, default=None)
    a = ap.parse_args(argv)
    try:
        slo = load_slo(a.slo)
    except ValueError as exc:
        print(f"LỖI: {exc}\nKết quả {BASELINE_ONLY}.", file=sys.stderr)
        return 2
    try:
        meta, records = load_sidecar(a.sidecar)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    try:
        summary = summarize(meta, records, a.warmup_seconds, a.warmup_requests)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    fails = evaluate(summary, slo)
    for f in fails:
        print(f"FAIL: {f}")
    print("KHÔNG ĐẠT SLO" if fails else "ĐẠT SLO")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
