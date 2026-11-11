"""Kiểm thử khói API RealCheck qua HTTP thật (KAN-29). Không import app/ hay models/.

    python -m scripts.make_fixtures --out .cache/smoke-fixtures
    python -m scripts.smoke_api --base-url http://localhost:8000 \
        --fixtures .cache/smoke-fixtures [--real ảnh] [--ai ảnh] [--out bang_chung.json]

Mã thoát: 0 mọi ca đạt, 1 có ca lỗi, 2 không kết nối được hoặc thiếu fixture.
Hợp đồng theo app/schemas.py và bảng D05 (docs/decisions/realcheck-baseline.md).
--real/--ai chỉ ghi nhận verdict/score; sai nhãn không phải lỗi, ngoài schema chỉ cảnh báo.
POST không bao giờ được thử lại.
"""

import argparse
import json
import math
import mimetypes
import re
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

VERDICTS = {"likely_real", "uncertain", "likely_ai"}
ANALYZE_KEYS = {"verdict", "score", "exif", "reason"}
VIET = re.compile(
    r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)

# Ca biên D06 ("tối đa" nghĩa là bằng thì qua) dùng JPEG đệm byte 0 sau EOI, nên CẦN XÁC NHẬN với API thật.
SIZE_CASE = "Đúng 5.242.880 byte (cần xác nhận)"
SIZE_HINT = "kiểm cách API tính dung lượng và overhead multipart (gateway), chưa kết luận API sai"
# (ca, file) -> 200
OK_CASES = [
    ("JPEG 4000x3000 có EXIF", "ok_4000x3000_exif.jpg"),
    ("JPEG 4000x3000 không EXIF", "ok_4000x3000_noexif.jpg"),
    ("JPEG Orientation=6", "ok_orientation6.jpg"),
    ("PNG hợp lệ", "ok_valid.png"),
    ("Biên 256x256", "ok_256x256.png"),
    (SIZE_CASE, "limit_5242880.jpg"),
]
# (ca, file, HTTP, code), theo D05
ERR_CASES = [
    ("File 0 byte", "empty.jpg", 400, "EMPTY_FILE"),
    ("Text giả .jpg", "fake_text.jpg", 400, "INVALID_IMAGE"),
    ("JPEG bị cắt cụt", "truncated.jpg", 400, "INVALID_IMAGE"),
    ("APNG nhiều khung", "multiframe.png", 415, "UNSUPPORTED_FORMAT"),
    ("GIF nhiều khung", "multiframe.gif", 415, "UNSUPPORTED_FORMAT"),
    ("Ảnh 200x200", "small_200x200.jpg", 422, "IMAGE_TOO_SMALL"),
    ("Ảnh 255x400", "small_255x400.jpg", 422, "IMAGE_TOO_SMALL"),
    ("5.242.881 byte", "over_5242881.jpg", 413, "FILE_TOO_LARGE"),
    ("6000x6000 (36 MP)", "many_pixels_6000x6000.png", 413, "TOO_MANY_PIXELS"),
    ("Cạnh 10001 px", "many_side_10001x300.png", 413, "TOO_MANY_PIXELS"),
]
FIXTURE_FILES = [f for _, f in OK_CASES] + [c[1] for c in ERR_CASES]


class Unreachable(Exception):
    pass


class Runner:
    def __init__(
        self, client: httpx.Client, fixtures: Path, timeout: float, delay: float = 0.0
    ):
        self.client, self.fixtures, self.timeout = client, fixtures, timeout
        self.delay = delay
        self.results: list[dict] = []
        self.requests: list[dict] = []

    def send(self, method, path, files=None, label=None):
        if self.delay and self.requests:
            time.sleep(self.delay)  # giãn cách để không vượt rate limit của gateway
        started = time.perf_counter()
        try:
            resp = self.client.request(method, path, files=files)
        except httpx.TimeoutException as exc:
            self.requests.append(
                {"method": method, "path": path, "file": label, "error": repr(exc)}
            )
            raise Unreachable(
                f"quá {self.timeout:g}s không có trả lời ở {method} {path}"
                + (f" (file {label})" if label else "")
            ) from exc
        except httpx.ConnectError as exc:
            raise Unreachable(f"{method} {path}: {exc}") from exc
        except httpx.HTTPError as exc:
            self.requests.append({"method": method, "path": path, "error": repr(exc)})
            return None
        self.requests.append(
            {
                "method": method,
                "path": path,
                "file": label,
                "status": resp.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": resp.headers.get("x-request-id"),
            }
        )
        return resp

    def upload(self, name, parts=None):
        if parts is None:
            data = (self.fixtures / name).read_bytes()
            mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
            parts = [("file", (name, data, mime))]
        return self.send("POST", "/v1/analyze", files=parts, label=name)

    def skip(self, case, why):
        self.results.append(
            {"case": case, "expected": "-", "actual": why, "status": "bỏ qua"}
        )

    def record(self, case, expected, problems, actual, kind="check"):
        status = "đạt" if not problems else ("lỗi" if kind == "check" else "cảnh báo")
        if kind == "info" and not problems:
            status = "ghi nhận"
        self.results.append(
            {
                "case": case,
                "expected": expected,
                "actual": "; ".join(problems) if problems else actual,
                "status": status,
            }
        )


def _json(resp):
    try:
        return resp.json()
    except ValueError:
        return None


def rid_problems(resp) -> list[str]:
    """X-Request-ID phải có và là UUID (app/logging.py: resolve_request_id)."""
    rid = resp.headers.get("x-request-id")
    if not rid:
        return ["thiếu header X-Request-ID"]
    try:
        uuid.UUID(rid)
    except ValueError:
        return [f"X-Request-ID {rid!r} không phải UUID"]
    return []


def schema_problems(resp) -> list[str]:
    """Vấn đề của một response 200 của /v1/analyze (rỗng nếu đúng hợp đồng)."""
    if resp is None:
        return ["không có response"]
    p = []
    if resp.status_code != 200:
        return [f"HTTP {resp.status_code}, kỳ vọng 200"]
    body = _json(resp)
    if not isinstance(body, dict):
        return ["body không phải JSON object"]
    if set(body) != ANALYZE_KEYS:
        p.append(f"trường {sorted(body)} khác {sorted(ANALYZE_KEYS)}")
    if body.get("verdict") not in VERDICTS:
        p.append(f"verdict {body.get('verdict')!r} ngoài enum")
    s = body.get("score")
    if isinstance(s, bool) or not isinstance(s, int | float) or not math.isfinite(s):
        p.append(f"score {s!r} không phải số hữu hạn")
    elif not 0 <= s <= 1:
        p.append(f"score {s} ngoài [0,1]")
    if not isinstance(body.get("exif"), str) or not body["exif"].strip():
        p.append("exif rỗng hoặc sai kiểu")
    r = body.get("reason")
    if not isinstance(r, str) or not r.strip():
        p.append("reason rỗng hoặc sai kiểu")
    elif not VIET.search(r):
        p.append("reason không có dấu tiếng Việt")
    return p + rid_problems(resp)


def error_problems(resp, status, code) -> list[str]:
    if resp is None:
        return ["không có response"]
    body = _json(resp)
    p = []
    if resp.status_code != status:
        p.append(f"HTTP {resp.status_code}, kỳ vọng {status}")
    err = body.get("error") if isinstance(body, dict) else None
    if (
        not isinstance(body, dict)
        or set(body) != {"error"}
        or not isinstance(err, dict)
    ):
        return p + ["không đúng envelope {error:{...}}"]
    if set(err) != {"code", "message", "request_id"}:
        p.append(f"trường error {sorted(err)}")
    if err.get("code") != code:
        p.append(f"code {err.get('code')!r}, kỳ vọng {code}")
    if not err.get("message"):
        p.append("message rỗng")
    p += rid_problems(resp)
    if (
        resp.headers.get("x-request-id")
        and err.get("request_id") != resp.headers["x-request-id"]
    ):
        p.append("request_id trong body khác header")
    return p


def run_checks(
    r: Runner,
    real: Path | None,
    ai: Path | None,
    docs: bool = True,
    size_boundary: bool = True,
) -> None:
    resp = r.send("GET", "/health")
    if resp is not None and resp.status_code == 503:
        r.record(
            "GET /health", "200 model_ready", ["503 not_ready: model chưa sẵn sàng"], ""
        )
    else:
        body = _json(resp) if resp is not None else None
        ok = (
            resp is not None
            and resp.status_code == 200
            and body
            == {
                "status": "ok",
                "model_ready": True,
            }
        )
        r.record(
            "GET /health",
            "200 model_ready",
            [] if ok else [f"HTTP {getattr(resp, 'status_code', None)} body {body}"],
            "200 ok",
        )
    for path in ("/docs", "/openapi.json"):
        if not docs:
            r.skip(f"GET {path}", "bỏ qua theo cờ --no-docs")
            continue
        resp = r.send("GET", path)
        code = getattr(resp, "status_code", None)
        r.record(f"GET {path}", "200", [] if code == 200 else [f"HTTP {code}"], "200")
    for case, name in OK_CASES:
        if case == SIZE_CASE and not size_boundary:
            r.skip(case, "bỏ qua theo cờ --skip-size-boundary")
            continue
        resp = r.upload(name)
        problems = schema_problems(resp)
        if (
            case == SIZE_CASE
            and problems
            and resp is not None
            and 400 <= resp.status_code < 500
            and resp.status_code != 404
        ):
            problems.append(f"gợi ý: {SIZE_HINT}")
        r.record(case, "200 + 4 trường hợp lệ", problems, "200 hợp lệ")
    for case, name, status, code in ERR_CASES:
        resp = r.upload(name)
        r.record(
            case,
            f"{status} {code}",
            error_problems(resp, status, code),
            f"{status} {code}",
        )
    resp = r.upload(None, parts=[("other", ("x.png", b"x", "image/png"))])
    r.record(
        "Thiếu trường file",
        "422 MISSING_FILE",
        error_problems(resp, 422, "MISSING_FILE"),
        "422 MISSING_FILE",
    )
    data = (r.fixtures / "ok_valid.png").read_bytes()
    two = [
        ("file", ("a.png", data, "image/png")),
        ("file", ("b.png", data, "image/png")),
    ]
    resp = r.upload("2 file", parts=two)
    r.record(
        "Hai file",
        "422 MULTIPLE_FILES",
        error_problems(resp, 422, "MULTIPLE_FILES"),
        "422 MULTIPLE_FILES",
    )
    resp = r.send(
        "GET", "/v1/khong-co-duong-nay"
    )  # dưới /v1/ để cùng đúng qua gateway, nơi / thuộc UI
    r.record(
        "GET đường dẫn lạ",
        "404 NOT_FOUND",
        error_problems(resp, 404, "NOT_FOUND"),
        "404 NOT_FOUND",
    )
    resp = r.send("GET", "/v1/analyze")
    r.record(
        "GET /v1/analyze",
        "405 METHOD_NOT_ALLOWED",
        error_problems(resp, 405, "METHOD_NOT_ALLOWED"),
        "405 METHOD_NOT_ALLOWED",
    )
    ids = [q["request_id"] for q in r.requests if q.get("request_id")]
    r.record(
        "X-Request-ID khác nhau giữa các request",
        "mỗi request một ID",
        [] if len(ids) == len(set(ids)) else ["có request_id trùng nhau"],
        f"{len(ids)} ID khác nhau",
    )
    for label, path in (("--real", real), ("--ai", ai)):
        if path is None:
            continue
        resp = r.upload(
            path.name,
            parts=[
                (
                    "file",
                    (
                        path.name,
                        path.read_bytes(),
                        mimetypes.guess_type(path.name)[0] or "image/jpeg",
                    ),
                )
            ],
        )
        problems = schema_problems(resp)
        body = _json(resp) if resp is not None and resp.status_code == 200 else {}
        r.record(
            f"Ảnh {label}",
            "200 trong schema (nhãn không kiểm)",
            problems,
            f"verdict={body.get('verdict')} score={body.get('score')}",
            kind="info",
        )


def _redact(url: str) -> str:
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    return urlunsplit(parts._replace(netloc=parts.netloc.rsplit("@", 1)[1]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--fixtures", type=Path, required=True)
    ap.add_argument("--real", type=Path)
    ap.add_argument("--ai", type=Path)
    ap.add_argument("--out", type=Path)
    # 60 s dài hơn timeout model D11 (10 s); Nginx/UI cũng phải dài hơn 10 s.
    ap.add_argument("--timeout", type=float, default=60.0, help="giây mỗi request")
    ap.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="giây nghỉ giữa hai request; dùng 0.15 khi chạy qua Nginx (10 r/s)",
    )
    ap.add_argument(
        "--no-docs", action="store_true", help="bỏ qua /docs, /openapi.json"
    )
    ap.add_argument(
        "--skip-size-boundary", action="store_true", help="bỏ ca đúng 5.242.880 byte"
    )
    args = ap.parse_args(argv)

    needed = [args.fixtures / f for f in FIXTURE_FILES + ["ok_valid.png"]]
    needed += [p for p in (args.real, args.ai) if p]
    missing = [str(p) for p in needed if not p.is_file()]
    if missing:
        print(
            "Thiếu fixture (chạy python -m scripts.make_fixtures):",
            *missing,
            sep="\n  ",
            file=sys.stderr,
        )
        return 2

    started = datetime.now(UTC).isoformat()
    fatal = None
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        runner = Runner(client, args.fixtures, args.timeout, args.delay)
        try:
            run_checks(
                runner,
                args.real,
                args.ai,
                docs=not args.no_docs,
                size_boundary=not args.skip_size_boundary,
            )
        except Unreachable as exc:
            fatal = f"Không kết nối được hoặc không có trả lời từ {_redact(args.base_url)}: {exc}"
            print(fatal, file=sys.stderr)

    print(f"{'Ca':<28} {'Kỳ vọng':<34} {'Thực tế':<40} Kết quả")
    for x in runner.results:
        print(f"{x['case']:<28} {x['expected']:<34} {x['actual']:<40} {x['status']}")
    failed = [x for x in runner.results if x["status"] == "lỗi"]
    warned = [x for x in runner.results if x["status"] == "cảnh báo"]
    print(f"\nTổng {len(runner.results)} ca, lỗi {len(failed)}, cảnh báo {len(warned)}")
    posts = [q.get("status") for q in runner.requests if q["method"] == "POST"]
    if posts and all(st == 404 for st in posts):
        print("POST /v1/analyze chưa tồn tại (404 cho mọi ca): chưa thể kiểm hợp đồng")
    code = 2 if fatal else 1 if failed else 0
    if args.out:
        args.out.write_text(
            json.dumps(
                {
                    "base_url": _redact(args.base_url),
                    "started_at": started,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "exit_code": code,
                    "fatal": fatal,
                    "results": runner.results,
                    "requests": runner.requests,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
