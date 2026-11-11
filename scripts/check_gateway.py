"""Kiểm gateway RealCheck chỉ bằng HTTP (KAN-54). Không import app/ hay models/, không điều khiển Docker.

    python -m scripts.check_gateway --base-url http://localhost --fixture artifacts/fixtures/phone.jpg \
        --rate 10 --burst 10 --upstream prompt [--out bang_chung.json]

Rò rỉ (FR-N03 chỉ cấm traceback và chi tiết nội bộ, KHÔNG cấm tên phần mềm): body chứa traceback/File "..."/tên
upstream; header Server chỉ bị coi là lộ khi có SỐ PHIÊN BẢN (nginx/1.25.3), còn `Server: nginx` vẫn xanh vì Nginx thật
chỉ ẩn được số; X-Powered-By có mặt là lộ framework.
Mã thoát: 0 mọi ca đạt, 1 có ca lỗi (kể cả timeout/ngắt kết nối sau khi đã nhận phản hồi), 2 thiếu tham số/fixture,
không tới được gateway hoặc stdin đóng khi --upstream prompt (kết quả đã có vẫn in và ghi --out).
--rate (request/giây) và --burst là ngưỡng do nhóm chốt (D13), script không tự đặt giá trị.
Không đặt X-Forwarded-For. POST không bao giờ được thử lại, trừ vòng chờ phục hồi có chủ đích.
Upstream tắt/chậm do NGƯỜI CHẠY làm: --upstream prompt (hỏi, chờ Enter) hoặc --wait-seconds N (chờ N giây).
"""

import argparse
import json
import math
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import httpx

PATH = "/v1/analyze"
MAX_FILE_BYTES = 5_242_880  # D06
OVERSIZE_EXTRA = 1_048_576  # vượt xa mọi phương án dư multipart (64/128 KiB) chưa chốt
GATEWAY_FAIL = {502, 503, 504}
# Dấu hiệu lộ nội bộ trong body lỗi của gateway (FR-N03)
LEAKS = ("traceback", 'file "', "upstream", "nginx", "uvicorn", "fastapi")


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v)


class Unreachable(Exception):
    pass


class Checker:
    def __init__(self, client: httpx.Client, fixture: Path):
        self.client = client
        self.fixture = fixture.read_bytes()
        self.name = fixture.name
        self.results: list[dict] = []
        self.seen_response = (
            False  # ConnectError trước phản hồi đầu tiên = không tới được gateway
        )

    def post(self, data=None, filename=None):
        data = self.fixture if data is None else data
        files = {"file": (filename or self.name, data, "image/jpeg")}
        try:
            resp = self.client.post(PATH, files=files)
        except httpx.ConnectError as exc:
            if not self.seen_response:
                raise Unreachable(f"POST {PATH}: {exc}") from exc
            return exc
        except httpx.HTTPError as exc:  # timeout, đóng kết nối giữa chừng: thành ca lỗi
            return exc
        self.seen_response = True
        return resp

    def record(self, case, expected, problems, actual):
        self.results.append(
            {
                "case": case,
                "expected": expected,
                "actual": "; ".join(problems) if problems else actual,
                "status": "lỗi" if problems else "đạt",
            }
        )


def envelope_problems(resp, retry_after=False) -> list[str]:
    """Envelope D05 {error:{code,message,request_id}} + X-Request-ID; không kiểm giá trị code."""
    p = []
    try:
        body = resp.json()
    except ValueError:
        body = None
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict) or set(body) != {"error"}:
        p.append("không đúng envelope {error:{...}}")
    else:
        for k in ("code", "message", "request_id"):
            if not isinstance(err.get(k), str) or not err[k]:
                p.append(f"error.{k} thiếu hoặc rỗng")
    if not resp.headers.get("x-request-id"):
        p.append("thiếu header X-Request-ID")
    if retry_after:
        ra = resp.headers.get("retry-after", "")
        if not ra.isdigit():
            p.append(f"Retry-After {ra!r} thiếu hoặc không phải số giây")
    return p


def leak_problems(resp) -> list[str]:
    """Body (thô và đã giải mã JSON, vì \\" che marker File ") và header không được lộ nội bộ (FR-N03)."""
    text = resp.text
    try:
        text += "\n" + "\n".join(_strings(resp.json()))
    except ValueError:
        pass
    text = text.lower()
    p = [f"body chứa {w!r}" for w in LEAKS if w in text]
    v = resp.headers.get("server")
    if v and re.search(r"\d", v):
        p.append(f"header server: {v!r} lộ số phiên bản")
    v = resp.headers.get("x-powered-by")
    if v:
        p.append(f"header x-powered-by: {v!r} lộ framework")
    return p


def status_text(resp) -> str:
    return (
        f"{type(resp).__name__}: {resp}"
        if isinstance(resp, Exception)
        else f"HTTP {resp.status_code}"
    )


def check_request_id_ok(ck: Checker, rate, anchor_sleep):
    """Dưới giới hạn: 3 request cách nhau 2/rate giây (nửa tốc độ) phải 200, có X-Request-ID."""
    ps = []
    for i in range(3):
        if i:
            anchor_sleep(2 / rate)
        r = ck.post()
        if isinstance(r, Exception) or r.status_code != 200:
            ps.append(f"lần {i + 1}: {status_text(r)}")
        elif not r.headers.get("x-request-id"):
            ps.append(f"lần {i + 1}: thiếu X-Request-ID")
    ck.record(
        "Dưới giới hạn vẫn 200 + X-Request-ID",
        f"3 request, nửa {rate:g} r/s → 200",
        ps,
        "3/3 là 200",
    )


def is_service_busy(resp) -> bool:
    """503 do API tạo (D12): đúng mã SERVICE_BUSY và envelope hợp lệ."""
    if resp.status_code != 503:
        return False
    try:
        code = resp.json()["error"]["code"]
    except (ValueError, KeyError, TypeError):
        return False
    return code == "SERVICE_BUSY" and not envelope_problems(resp, False)


def check_rate(ck: Checker, rate, burst, cooldown, retry_after, sleep):
    n = 2 * (math.ceil(rate) + burst) + 10
    with ThreadPoolExecutor(max_workers=16) as pool:
        rs = list(pool.map(lambda _: ck.post(b"x", "flood.jpg"), range(n)))
    r429 = [r for r in rs if not isinstance(r, Exception) and r.status_code == 429]
    # D12: API hết slot trả 503 SERVICE_BUSY; đó là lỗi của API, không phải của gateway.
    bad = sorted(
        {
            r.status_code
            for r in rs
            if not isinstance(r, Exception)
            and r.status_code >= 500
            and not is_service_busy(r)
        }
    )
    broken = sorted({type(r).__name__ for r in rs if isinstance(r, Exception)})
    ps = []
    if not r429:
        ps.append(
            f"không có 429 trong {n} request gửi dồn (rate={rate:g}, burst={burst})"
        )
    if bad:
        ps.append(f"có phản hồi 5xx không phải rate limit: {bad}")
    if broken:
        ps.append(
            f"có request không nhận được phản hồi (kết nối/timeout, không phải 5xx): {broken}"
        )
    if r429:
        ps += envelope_problems(r429[0], retry_after) + leak_problems(r429[0])
    ck.record(
        "Vượt giới hạn trả 429 (không 5xx)",
        "≥1 request 429, envelope, không 500",
        ps,
        f"{len(r429)}/{n} là 429",
    )
    sleep(cooldown)
    r = ck.post()
    ps = (
        []
        if not isinstance(r, Exception) and r.status_code == 200
        else [f"sau {cooldown:g}s chờ: {status_text(r)}"]
    )
    ck.record(
        "Phục hồi sau rate limit",
        "request hợp lệ lại 200",
        ps,
        f"200 sau {cooldown:g}s chờ",
    )


def check_body(ck: Checker):
    r = ck.post(b"\0" * (MAX_FILE_BYTES + OVERSIZE_EXTRA))
    if isinstance(r, Exception):
        ps = [
            f"không nhận được 413 ({status_text(r)}): gateway đóng kết nối khi gửi body"
        ]
    else:
        ps = [] if r.status_code == 413 else [f"HTTP {r.status_code}, kỳ vọng 413"]
        ps += envelope_problems(r) + leak_problems(r)
        try:
            code = r.json()["error"]["code"]
            if r.status_code == 413 and code != "FILE_TOO_LARGE":
                ps.append(f"code {code!r}, kỳ vọng FILE_TOO_LARGE (D05)")
        except (ValueError, KeyError, TypeError):
            pass
    ck.record(
        f"Body {MAX_FILE_BYTES + OVERSIZE_EXTRA} B bị chặn",
        "413 FILE_TOO_LARGE + envelope",
        ps,
        "413",
    )


def check_boundary(ck: Checker):
    """AC-09: file đúng 5.242.880 B (đệm 0 sau fixture) không bị gateway chặn; +1 B bị 413. Kết quả sau gateway chỉ ghi nhận."""
    if len(ck.fixture) > MAX_FILE_BYTES:
        ck.record(
            "Biên đúng 5.242.880 B", "không 413", ["fixture lớn hơn giới hạn"], ""
        )
        return
    pad = lambda n: ck.fixture + b"\0" * (n - len(ck.fixture))
    r = ck.post(pad(MAX_FILE_BYTES))
    if isinstance(r, Exception):
        ps = [f"không nhận được phản hồi ({status_text(r)})"]
    elif r.status_code in (413, 429) or r.status_code >= 500:
        ps = [f"HTTP {r.status_code}, gateway không được chặn file đúng giới hạn"]
    else:
        ps = []
    ck.record("Biên đúng 5.242.880 B", "không 413/429/5xx", ps, status_text(r))
    r = ck.post(pad(MAX_FILE_BYTES + 1))
    if isinstance(r, Exception):
        ps = [f"không nhận được 413 ({status_text(r)})"]
    else:
        ps = [] if r.status_code == 413 else [f"HTTP {r.status_code}, kỳ vọng 413"]
    ck.record("Biên 5.242.881 B", "413", ps, status_text(r))


def pause(msg, wait, ask):
    print(msg, flush=True)
    if wait is None:
        ask("Nhấn Enter khi đã làm xong... ")
    else:
        time.sleep(wait)


def check_upstream(ck: Checker, wait, ask, recovery_timeout, poll):
    pause(
        "Hãy TẮT (hoặc làm treo) upstream API; script không tự điều khiển Docker.",
        wait,
        ask,
    )
    r = ck.post()
    if isinstance(r, Exception):
        ps = [f"không nhận được trả lời của gateway ({status_text(r)})"]
    else:
        ps = (
            []
            if r.status_code in GATEWAY_FAIL
            else [f"HTTP {r.status_code}, kỳ vọng 502/503/504"]
        )
        ps += envelope_problems(r) + leak_problems(r)
    ck.record(
        "Upstream tắt/chậm trả lỗi gateway sạch",
        "502/503/504 + envelope, không lộ nội bộ",
        ps,
        status_text(r),
    )
    pause("Hãy BẬT LẠI upstream API.", wait, ask)
    start = time.monotonic()
    last = None
    while True:
        last = ck.post()
        if not isinstance(last, Exception) and last.status_code == 200:
            ck.record(
                "Phục hồi sau khi upstream trở lại",
                "200 trong thời hạn",
                [],
                f"200 sau {time.monotonic() - start:.1f}s",
            )
            return
        if time.monotonic() - start >= recovery_timeout:
            ck.record(
                "Phục hồi sau khi upstream trở lại",
                "200 trong thời hạn",
                [f"sau {recovery_timeout:g}s vẫn {status_text(last)}"],
                "",
            )
            return
        time.sleep(poll)


def write_junit(path, results, upstream_skipped, aborted):
    """JUnit cho gate G04 (check_mvp_gates): mỗi ca là một testcase. Upstream bỏ qua hoặc chạy dở thì
    không bao giờ xanh: skipped / error, để thiếu bằng chứng không thành "đạt"."""
    suite = ET.Element("testsuite", name="gateway", tests=str(len(results)))
    for r in results:
        case = ET.SubElement(suite, "testcase", classname="gateway", name=r["case"])
        if r["status"] == "lỗi":
            ET.SubElement(case, "failure", message=r["actual"])
    extra = []
    if upstream_skipped:
        extra.append(("skipped", "--upstream skip: tắt/bật upstream chưa kiểm"))
    if aborted:
        extra.append(("error", "chạy dở: không tới được gateway hoặc stdin đóng"))
    for tag, message in extra:
        case = ET.SubElement(suite, "testcase", classname="gateway", name=message)
        ET.SubElement(case, tag, message=message)
    suite.set("tests", str(len(results) + len(extra)))
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def run(args, ask=input, sleep=time.sleep) -> int:
    if args.rate <= 0 or args.burst < 0:
        print(
            "Thiếu/sai ngưỡng: --rate phải > 0 và --burst >= 0 (do nhóm chốt, D13).",
            file=sys.stderr,
        )
        return 2
    fixture = Path(args.fixture)
    if not fixture.is_file():
        print(f"Thiếu fixture: {fixture}", file=sys.stderr)
        return 2
    cooldown = (
        args.cooldown if args.cooldown is not None else (args.burst + 1) / args.rate + 1
    )
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        ck = Checker(client, fixture)
        rc = None
        try:
            on = lambda name: not args.only or name in args.only
            if on("under"):
                check_request_id_ok(ck, args.rate, sleep)
            if on("rate"):
                check_rate(
                    ck, args.rate, args.burst, cooldown, args.require_retry_after, sleep
                )
            if on("body"):
                check_body(ck)
            if on("boundary"):
                check_boundary(ck)
            if args.upstream == "prompt":
                check_upstream(
                    ck,
                    args.wait_seconds,
                    ask,
                    args.recovery_timeout,
                    args.poll_interval,
                )
        except Unreachable as exc:
            print(f"Không kết nối được gateway: {exc}", file=sys.stderr)
            rc = 2
        except EOFError:
            print(
                "stdin đã đóng khi --upstream prompt: chạy trong terminal hoặc dùng --wait-seconds N.",
                file=sys.stderr,
            )
            rc = 2
    for r in ck.results:
        print(f"[{r['status']}] {r['case']}: {r['actual']}")
    if args.upstream == "skip":
        print(
            "[bỏ qua] Upstream tắt/chậm và phục hồi: --upstream skip, mục này CHƯA kiểm."
        )
    if args.junit:
        write_junit(args.junit, ck.results, args.upstream == "skip", rc is not None)
    if args.out:
        parts = urlsplit(args.base_url)
        base = urlunsplit(parts._replace(netloc=parts.netloc.rpartition("@")[2]))
        Path(args.out).write_text(
            json.dumps(
                {
                    "time": datetime.now(UTC).isoformat(),
                    "base_url": base,
                    "rate": args.rate,
                    "burst": args.burst,
                    "results": ck.results,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if rc is not None:
        return rc
    return 1 if any(r["status"] == "lỗi" for r in ck.results) else 0


def main(argv=None, ask=input, sleep=time.sleep) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", required=True)
    ap.add_argument(
        "--fixture",
        required=True,
        help="ảnh hợp lệ (JPEG/PNG) cho request dưới giới hạn",
    )
    ap.add_argument(
        "--rate", type=float, required=True, help="request/giây của chính sách đã chốt"
    )
    ap.add_argument(
        "--burst",
        type=int,
        required=True,
        help="burst của chính sách đã chốt (0 nếu không burst)",
    )
    ap.add_argument("--upstream", choices=["prompt", "skip"], required=True)
    ap.add_argument(
        "--wait-seconds",
        type=float,
        help="chờ N giây thay vì hỏi Enter khi tắt/bật upstream",
    )
    ap.add_argument(
        "--recovery-timeout",
        type=float,
        default=60,
        help="giây chờ 200 sau khi upstream bật lại",
    )
    ap.add_argument(
        "--poll-interval",
        type=float,
        default=1,
        help="giây giữa các lần thử khi chờ phục hồi",
    )
    ap.add_argument(
        "--cooldown", type=float, help="giây chờ sau flood (mặc định (burst+1)/rate+1)"
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="timeout HTTP của client (mặc định 30 s)",
    )
    ap.add_argument(
        "--require-retry-after",
        action="store_true",
        help="429 phải có Retry-After dạng số giây",
    )
    ap.add_argument(
        "--only",
        nargs="+",
        choices=["under", "rate", "body", "boundary"],
        help="chỉ chạy các ca HTTP này (mặc định tất cả)",
    )
    ap.add_argument("--out")
    ap.add_argument(
        "--junit", help="ghi JUnit XML cho gate G04 (artifacts/integration.xml)"
    )
    return run(ap.parse_args(argv), ask, sleep)


if __name__ == "__main__":
    sys.exit(main())
