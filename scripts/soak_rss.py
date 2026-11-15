"""Lấy mẫu RSS của container api trong lúc soak, ghi file cho check_performance (T031, KAN-58).

Chạy từ gốc repo, song song với Locust soak, trên máy có Docker:
    python -m scripts.soak_rss --container realcheck-api-1 --duration-seconds 3600 \
        --warmup-seconds 300 --output artifacts/soak-rss.json
    python -m scripts.check_performance --sidecar artifacts/soak.jsonl \
        --slo docs/performance/slo.json --scope soak --rss artifacts/soak-rss.json

Đọc `docker stats --no-stream` (mức dùng bộ nhớ cgroup của container, gần RSS nhưng không
đồng nhất với VmRSS của tiến trình), mỗi `--interval-seconds` (mặc định 30). File ghi đúng hai khóa
`rss_after_warmup_mb` (mẫu đầu tiên ở hoặc sau warmup) và `rss_end_mb` (mẫu cuối), đơn vị MiB.
Thoát 0 khi ghi được, 2 khi tham số hoặc Docker lỗi.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

# Docker in thập phân (kB, MB, GB) hoặc nhị phân (KiB, MiB, GiB) tùy phiên bản.
_UNIT_BYTES = {
    "B": 1,
    "kB": 10**3,
    "KB": 10**3,
    "MB": 10**6,
    "GB": 10**9,
    "KiB": 2**10,
    "MiB": 2**20,
    "GiB": 2**30,
}


def parse_mem_usage(text: str) -> float:
    """'543.2MiB / 2GiB' -> MiB đang dùng (phần trước dấu /)."""
    m = re.match(r"\s*([\d.]+)\s*([A-Za-z]+)\s*/", text)
    if not m or m.group(2) not in _UNIT_BYTES:
        raise ValueError(f"Không đọc được MemUsage của docker stats: {text!r}")
    return float(m.group(1)) * _UNIT_BYTES[m.group(2)] / 2**20


def docker_mem_mib(container: str, run: Callable = subprocess.run) -> float:
    try:
        r = run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError as exc:
        raise ValueError(f"Không chạy được docker: {exc}") from exc
    if r.returncode != 0:
        raise ValueError(
            f"docker stats lỗi (container {container!r}): {r.stderr.strip()}"
        )
    return parse_mem_usage(r.stdout)


def collect(
    read: Callable[[], float],
    duration: float,
    warmup: float,
    interval: float,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[dict, list[tuple[float, float]]]:
    """Lấy mẫu mỗi `interval` giây tới hết `duration`; mẫu cuối ở đúng cuối thời lượng."""
    sleep, clock = (
        sleep or time.sleep,
        clock or time.monotonic,
    )  # tra lúc gọi để test thay được
    if not (duration > warmup >= 0 and interval > 0):
        raise ValueError("Cần duration > warmup >= 0 và interval > 0")
    start = clock()
    samples: list[tuple[float, float]] = []
    while True:
        t = clock() - start
        samples.append((t, read()))
        if t >= duration:
            break
        sleep(min(interval, duration - t))
    after = [s for s in samples if s[0] >= warmup]
    if len(after) < 2:
        raise ValueError(
            "Cần ít nhất 2 mẫu sau warmup để so RSS; tăng duration hoặc giảm interval"
        )
    return {"rss_after_warmup_mb": after[0][1], "rss_end_mb": after[-1][1]}, samples


def main(argv: list[str] | None = None, read: Callable[[], float] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Lấy mẫu RSS container api cho soak (T031)"
    )
    ap.add_argument("--container", required=True, help="tên hoặc ID container api")
    ap.add_argument("--duration-seconds", type=float, required=True)
    ap.add_argument("--warmup-seconds", type=float, required=True)
    ap.add_argument("--interval-seconds", type=float, default=30)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args(argv)
    read = read or (lambda: docker_mem_mib(a.container))
    try:
        result, samples = collect(
            read, a.duration_seconds, a.warmup_seconds, a.interval_seconds
        )
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError) as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    print(f"{len(samples)} mẫu; ghi {a.output}: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
