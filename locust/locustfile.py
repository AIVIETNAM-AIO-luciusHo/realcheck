"""Locust cho POST /v1/analyze: ảnh raw (không pre-resize), sidecar JSONL từng request.

Cấu hình qua biến môi trường và --rc-scenario (xem locust/README.md). Mốc `t` trong sidecar là
time.time() (đồng hồ treo tường, có thể nhảy nếu NTP chỉnh); latency đo cùng đồng hồ, không gồm đọc file payload. Không dùng model stub, không giả X-Forwarded-For.
"""

import json
import math
import os
import random
import time
from pathlib import Path

from locust import HttpUser, events, task

PAYLOAD_DIR = Path(os.environ.get("RC_PAYLOAD_DIR", "payloads"))
# Mix theo tên thư mục con của PAYLOAD_DIR, ví dụ jpeg=40,png=30,phone=30
MIX = os.environ.get("RC_MIX", "")
WAIT_MIN = float(os.environ.get("RC_WAIT_MIN", "1"))
WAIT_MAX = float(os.environ.get("RC_WAIT_MAX", "3"))
SIDECAR = Path(os.environ.get("RC_SIDECAR", "sidecar.jsonl"))
WARMUP_S = float(os.environ.get("RC_WARMUP_SECONDS", "0"))
WARMUP_N = int(os.environ.get("RC_WARMUP_REQUESTS", "0"))
META_ENV = ("commit", "image", "model", "profile", "config_hash", "client", "server")
TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}

SCENARIOS = ("baseline", "rate_only", "stress", "recovery", "soak")
_fh = None


@events.init_command_line_parser.add_listener
def _args(parser):
    # Tham số locust (đặt được trong file conf) thay cho biến môi trường: conf ghim kịch bản,
    # quên biến môi trường không thể chạy nhầm rate-only thành baseline.
    parser.add_argument("--rc-scenario", choices=SCENARIOS, default="baseline")


@events.init.add_listener
def _check_scenario(environment, **_):
    """Soak không có thời lượng mặc định (D14 chưa chốt): bắt buộc --run-time."""
    opts = environment.parsed_options
    if opts.rc_scenario == "soak" and not getattr(opts, "run_time", None):
        raise SystemExit("rc-scenario soak cần --run-time (D14 chưa chốt: 30/60/120m)")


_pool: list[tuple[Path, str]] = []
_weights: list[float] = []


def _parse_mix(text: str, groups) -> dict[str, float]:
    """'jpeg=40,png=30' -> trọng số; rỗng = đều. Từ chối nhóm lạ, trọng số sai/âm hoặc tổng 0."""
    try:
        mix = {k: float(v) for k, v in (kv.split("=") for kv in text.split(",") if kv)}
    except ValueError:
        raise SystemExit(f"RC_MIX sai định dạng (cần nhom=so,...): {text!r}") from None
    mix = mix or {g: 1.0 for g in groups}
    if set(mix) - set(groups):
        raise SystemExit(
            f"RC_MIX có nhóm không tồn tại: {sorted(set(mix) - set(groups))}"
        )
    if (
        any(not math.isfinite(w) or w < 0 for w in mix.values())
        or sum(mix.values()) <= 0
    ):
        raise SystemExit(f"RC_MIX cần trọng số hữu hạn, không âm, tổng > 0: {text!r}")
    return mix


def _load_payloads():
    """Gom file theo thư mục con; trọng số theo RC_MIX, mặc định đều."""
    groups = {}
    for d in sorted(p for p in PAYLOAD_DIR.iterdir() if p.is_dir()):
        files = [f for f in sorted(d.iterdir()) if f.suffix.lower() in TYPES]
        if files:
            groups[d.name] = files
    if not groups:
        raise SystemExit(f"RC_PAYLOAD_DIR={PAYLOAD_DIR} cần thư mục con chứa .jpg/.png")
    mix = _parse_mix(MIX, groups)
    for name, w in mix.items():
        for f in groups[name]:
            _pool.append((f, TYPES[f.suffix.lower()]))
            _weights.append(float(w) / len(groups[name]))
    return mix


def _write(row: dict):
    _fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    _fh.flush()


@events.test_start.add_listener
def _start(environment, **_):
    global _fh
    mix = _load_payloads()
    _fh = SIDECAR.open("w", encoding="utf-8")
    opts = environment.parsed_options
    meta = {k: os.environ.get(f"RC_{k.upper()}") for k in META_ENV}
    _write(
        {
            "type": "meta",
            "scenario": opts.rc_scenario,
            "mix": mix,
            "wait": list(_wait_bounds(opts.rc_scenario)),
            "warmup_seconds": WARMUP_S,
            "warmup_requests": WARMUP_N,
            "users": getattr(opts, "num_users", None),
            "spawn_rate": getattr(opts, "spawn_rate", None),
            "run_time": getattr(opts, "run_time", None),
            "host": environment.host,
            "started": time.time(),
            **{k: v for k, v in meta.items() if v},  # không điền khi chưa khai
        }
    )


@events.test_stop.add_listener
def _stop(**_):
    if _fh:
        _fh.close()


def _wait_bounds(scenario: str) -> tuple[float, float]:
    return (0.0, 0.0) if scenario == "rate_only" else (WAIT_MIN, WAIT_MAX)


def _wait(self) -> float:
    return random.uniform(*_wait_bounds(self.environment.parsed_options.rc_scenario))


def _valid(body) -> bool:
    try:
        s = body["score"]
        return (
            set(body) == {"verdict", "score", "exif", "reason"}
            and body["verdict"] in ("likely_real", "uncertain", "likely_ai")
            and isinstance(s, (int, float))
            and not isinstance(s, bool)
            and math.isfinite(s)
            and 0 <= s <= 1
            and all(isinstance(body[k], str) and body[k] for k in ("exif", "reason"))
        )
    except (TypeError, KeyError):
        return False


def _outcome(status: int, valid: bool) -> str:
    if status == 200:
        return "200" if valid else "invalid200"
    if status in (429, 503, 504):
        return str(status)
    return "5xx" if 500 <= status <= 599 else "other"


class AnalyzeUser(HttpUser):
    wait_time = _wait

    @task
    def analyze(self):
        path, mime = random.choices(_pool, _weights)[0]
        data = path.read_bytes()
        t0 = time.time()
        with self.client.post(
            "/v1/analyze",
            files={"file": (path.name, data, mime)},
            catch_response=True,
            name="/v1/analyze",
        ) as resp:
            status = resp.status_code
            code, valid = None, False
            try:
                body = resp.json()
            except ValueError:
                body = None
            if status == 200:
                valid = _valid(body)
            elif isinstance(body, dict) and isinstance(body.get("error"), dict):
                code = body["error"].get("code")
            outcome = _outcome(status, valid)
            _write(
                {
                    "type": "req",
                    "t": t0,
                    "outcome": outcome,
                    "status": status,
                    "error_code": code,
                    "latency_ms": (time.time() - t0) * 1000,
                    "payload": path.name,
                }
            )
            if outcome == "200":
                resp.success()
            else:
                resp.failure(f"{outcome} status={status} code={code}")
