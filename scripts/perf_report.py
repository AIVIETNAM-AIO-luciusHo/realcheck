"""Đọc sidecar JSONL của Locust, tách outcome và tính số đo. Thuần stdlib, không import locust.

Dòng req hỏng (thiếu/sai kiểu/không hữu hạn t hoặc latency_ms, latency_ms < 0, outcome lạ)
làm cả sidecar bị từ chối (thoát 2), không loại âm thầm. --warmup-* âm cũng bị từ chối.

Sidecar: dòng đầu {"type":"meta",...}, các dòng sau {"type":"req","t","outcome","status",
"error_code","latency_ms"}. Percentile chỉ trên outcome "200" (200 đúng schema);
429/503/504/5xx không bao giờ vào RPS thành công.
"""

import argparse
import json
import math
import sys
from pathlib import Path

MISSING = "thiếu"
OUTCOMES = ("200", "invalid200", "429", "503", "504", "5xx", "other")
META_KEYS = ("commit", "image", "model", "profile", "config_hash", "client", "server")


def classify(status: int, schema_valid: bool = True) -> str:
    if status == 200:
        return "200" if schema_valid else "invalid200"
    if status in (429, 503, 504):
        return str(status)
    if 500 <= status <= 599:
        return "5xx"
    return "other"  # gồm status 0 (lỗi kết nối) và 4xx khác


def load_sidecar(path: Path) -> tuple[dict, list[dict]]:
    """Trả (meta, records). ValueError nếu thiếu file, rỗng hoặc có dòng hỏng."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"không đọc được sidecar {path}: {exc}") from exc
    meta: dict = {}
    records: list[dict] = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"sidecar dòng {n} không phải JSON") from exc
        if not isinstance(row, dict):
            raise ValueError(f"sidecar dòng {n} không phải object")  # noqa: TRY004
        if row.get("type") == "meta":
            meta.update(row)
        elif row.get("type") == "req":
            t, lat = row.get("t"), row.get("latency_ms")
            if (
                row.get("outcome") not in OUTCOMES
                or not all(
                    isinstance(v, (int, float))
                    and not isinstance(v, bool)
                    and math.isfinite(v)
                    for v in (t, lat)
                )
                or lat < 0
            ):
                raise ValueError(
                    f"sidecar dòng {n} thiếu hoặc sai t/latency_ms/outcome"
                )
            records.append(row)
        else:
            raise ValueError(f"sidecar dòng {n} có type lạ")
    if not records:
        raise ValueError("sidecar không có request nào")
    return meta, records


def percentile(sorted_vals: list[float], p: float) -> float | None:
    """Nearest-rank."""
    if not sorted_vals:
        return None
    return sorted_vals[max(1, math.ceil(p / 100 * len(sorted_vals))) - 1]


def summarize(
    meta: dict,
    records: list[dict],
    warmup_seconds: float | None = None,
    warmup_requests: int | None = None,
) -> dict:
    """Bỏ warmup (theo thời gian tính từ request đầu và/hoặc N request đầu) rồi tính số đo."""
    if any(
        v is not None and not (math.isfinite(v) and v >= 0)
        for v in (warmup_seconds, warmup_requests)
    ):
        raise ValueError("warmup phải hữu hạn và không âm")
    recs = sorted(records, key=lambda r: r["t"])
    ws = meta.get("warmup_seconds") if warmup_seconds is None else warmup_seconds
    wr = meta.get("warmup_requests") if warmup_requests is None else warmup_requests
    start = recs[0]["t"]
    before = len(recs)
    recs = recs[int(wr or 0) :]
    recs = [r for r in recs if r["t"] >= start + float(ws or 0)]
    skipped = before - len(recs)
    counts = {o: sum(1 for r in recs if r["outcome"] == o) for o in OUTCOMES}
    lat200 = sorted(r["latency_ms"] for r in recs if r["outcome"] == "200")
    window = None
    if recs:
        w = max(r["t"] + r["latency_ms"] / 1000 for r in recs) - recs[0]["t"]
        window = w if w > 0 else None
    total = len(recs)
    non429 = total - counts["429"]
    out = {
        "warmup_skipped_requests": skipped,
        "measured_requests": total,
        "window_s": window if window is not None else MISSING,
        "counts": counts,
        "offered_rps": total / window if window else MISSING,
        "rps200": counts["200"] / window if window else MISSING,
        "latency_200_ms": {
            f"p{p}": percentile(lat200, p) if lat200 else MISSING for p in (50, 95, 99)
        },
        # lỗi bất ngờ = mọi thứ không phải 200 đúng schema và không phải 429 chặn tốc độ
        "error_ratio_excl_429": (non429 - counts["200"]) / non429
        if non429
        else MISSING,
        "meta": {k: meta.get(k, MISSING) for k in META_KEYS},
    }
    return out


def render(s: dict) -> str:
    lines = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in s.items()]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Báo cáo từ sidecar Locust")
    ap.add_argument("sidecar", type=Path)
    ap.add_argument("--warmup-seconds", type=float, default=None)
    ap.add_argument("--warmup-requests", type=int, default=None)
    ap.add_argument("--output", type=Path, default=None, help="ghi JSON báo cáo")
    a = ap.parse_args(argv)
    try:
        meta, records = load_sidecar(a.sidecar)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    try:
        s = summarize(meta, records, a.warmup_seconds, a.warmup_requests)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    print(render(s))
    print("Chỉ là số đo baseline; không kết luận đạt SLA.")
    if a.output:
        a.output.write_text(
            json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
