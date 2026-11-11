"""KAN-54: scripts/check_gateway.py với gateway giả (stdlib, thread, cổng 0). Không mạng ngoài."""

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import scripts.check_gateway as g
from scripts.check_gateway import main

SMALL = 100_000  # giới hạn thu nhỏ để test nhanh; test dùng giá trị thật có fixture real_limit
ARGS = ["--rate", "20", "--burst", "1", "--cooldown", "0.3", "--poll-interval", "0.05"]
LINE = re.compile(r"^\[(đạt|lỗi|bỏ qua)\] (.*?): (.*)$", re.MULTILINE)


@pytest.fixture(autouse=True)
def small_limit(request, monkeypatch):
    if "real_limit" not in request.fixturenames:
        monkeypatch.setattr(g, "MAX_FILE_BYTES", SMALL)


@pytest.fixture
def real_limit():
    return None


class Fake:
    """Gateway giả (HTTP/1.1 keep-alive). flood.jpg bị 429 sau 20 request, khóa 0.2 s."""

    def __init__(self, **opts):
        self.opts = {
            "rate_limit": True,
            "bad_env": set(),  # status có envelope hỏng
            "no_rid": set(),  # status thiếu X-Request-ID
            "upstream": "up",  # up | down | hang
            "leak": False,
            "retry_after": True,
            "never_recover": False,
            "code413": "FILE_TOO_LARGE",
            "status413": 413,
            "flood_500": False,
            "flood_busy": "",  # mã lỗi 503 trả ở request flood thứ 3
            "flood_drop": False,
            "under_status": 200,
            "strict_limit": False,
            "server_hdr": {},  # status -> giá trị header Server
            "powered": {},  # status -> giá trị X-Powered-By
            "down_status": 502,
            "file_msg": False,  # message JSON chứa File "x.py", line 3
            "message": "Lỗi",
            "close_after": False,  # Connection: close sau mỗi response
            "no_limit": False,  # không chặn file vượt giới hạn
            "xff_reject": False,  # trả 400 nếu request có X-Forwarded-For
        }
        self.opts.update(opts)
        self.flood = 0
        self.blocked_until = 0.0
        self.lock = threading.Lock()
        fake = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"
            server_version = "gw"  # mặc định "BaseHTTP/x Python/y" bị script coi là lộ
            sys_version = ""

            def log_message(self, *a):
                pass

            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                if fake.opts["xff_reject"] and "X-Forwarded-For" in self.headers:
                    res = fake.err(400, "XFF")
                else:
                    res = fake.decide(body, self.headers["Content-Type"])
                if res is None:  # ngắt kết nối không trả lời
                    self.close_connection = True
                    return
                status, payload, extra = res
                self.send_response(status)
                self.send_header("Content-Length", str(len(payload)))
                if status not in fake.opts["no_rid"]:
                    self.send_header("X-Request-ID", "rid-1")
                if status in fake.opts["server_hdr"]:
                    self.send_header("Server", fake.opts["server_hdr"][status])
                if status in fake.opts["powered"]:
                    self.send_header("X-Powered-By", fake.opts["powered"][status])
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                if fake.opts["close_after"]:
                    self.send_header("Connection", "close")
                    self.close_connection = True
                self.end_headers()
                self.wfile.write(payload)

        class S(ThreadingHTTPServer):
            request_queue_size = 128
            daemon_threads = True

        self.server = S(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        ).start()

    def err(self, status, code):
        if status in self.opts["bad_env"]:
            return status, b"<html>boom</html>", None
        msg = self.opts["message"]
        if self.opts["file_msg"]:
            msg = 'File "/app/x.py", line 3, in handler'
        p = {"error": {"code": code, "message": msg, "request_id": "rid-1"}}
        return status, json.dumps(p).encode(), None

    @staticmethod
    def file_len(body, ctype):
        """Số byte nội dung file trong multipart (một phần duy nhất)."""
        boundary = ctype.split("boundary=")[1].encode()
        start = body.index(b"\r\n\r\n") + 4
        return len(body) - start - len(b"\r\n--" + boundary + b"--\r\n")

    def decide(self, body, ctype):
        o = self.opts
        if o["upstream"] == "hang":
            time.sleep(1.0)
            return self.err(504, "TIMEOUT")
        if o["upstream"] == "down":
            if o["leak"]:
                msg = '{"error":{"code":"X","message":"Traceback upstream","request_id":"r"}}'
                return 502, msg.encode(), None
            return self.err(o["down_status"], "BAD_GATEWAY")
        flood = b'filename="flood.jpg"' in body[:300]
        flen = self.file_len(body, ctype)
        if not o["no_limit"] and flen > g.MAX_FILE_BYTES - o["strict_limit"]:
            st, payload, extra = self.err(o["status413"], o["code413"])
            return st, payload, extra
        with self.lock:
            now = time.monotonic()
            if o["rate_limit"]:
                if flood:
                    self.flood += 1
                    if self.flood > 20 and now >= self.blocked_until:
                        self.blocked_until = now + (1e9 if o["never_recover"] else 0.2)
                if now < self.blocked_until:
                    extra = {"Retry-After": "1"} if o["retry_after"] else None
                    st, payload, _ = self.err(429, "RATE_LIMITED")
                    return st, payload, extra
            n = self.flood
        if flood and o["flood_500"] and n == 3:
            return self.err(500, "INTERNAL_ERROR")
        if flood and o["flood_busy"] and n == 3:
            return self.err(503, o["flood_busy"])
        if flood and o["flood_drop"] and n == 3:
            return None
        if not flood and len(body) < 1000:
            return o["under_status"], b'{"verdict":"uncertain"}', None
        return 200, b'{"verdict":"uncertain"}', None

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fixture(tmp_path):
    p = tmp_path / "ok.jpg"
    p.write_bytes(b"\xff\xd8fake")
    return str(p)


@pytest.fixture
def gw():
    made = []

    def make(**opts):
        f = Fake(**opts)
        made.append(f)
        return f

    yield make
    for f in made:
        f.close()


def run(fake, fixture, *extra, ask=None):
    argv = ["--base-url", fake.url, "--fixture", fixture, *ARGS, *extra]
    return main(argv, ask=ask or (lambda _: ""))


def cases(capsys):
    """{tên ca: (trạng thái, chi tiết)} từ stdout."""
    return {m[1]: (m[0], m[2]) for m in LINE.findall(capsys.readouterr().out)}


def only_failed(res, prefix):
    """Đúng một ca lỗi và tên bắt đầu bằng prefix; trả chi tiết."""
    bad = {k: v for k, v in res.items() if v[0] == "lỗi"}
    assert len(bad) == 1, bad
    ((name, (_, detail)),) = bad.items()
    assert name.startswith(prefix), name
    return detail


def test_all_pass_real_limit(gw, fixture, capsys, real_limit):
    assert run(gw(), fixture, "--upstream", "skip", "--require-retry-after") == 0
    res = cases(capsys)
    assert len(res) == 7 and {v[0] for v in res.values()} == {"đạt", "bỏ qua"}
    assert any(k.startswith("Biên đúng 5.242.880") for k in res)


def test_upstream_down_then_recovery(gw, fixture, capsys):
    f = gw()

    def ask(prompt):
        f.opts["upstream"] = "down" if f.opts["upstream"] == "up" else "up"

    assert run(f, fixture, "--upstream", "prompt", "--only", "boundary", ask=ask) == 0
    res = cases(capsys)
    assert res["Upstream tắt/chậm trả lỗi gateway sạch"] == ("đạt", "HTTP 502")
    assert res["Phục hồi sau khi upstream trở lại"][0] == "đạt"


def test_upstream_never_recovers_fails(gw, fixture, capsys):
    f = gw()
    state = {"n": 0}

    def ask(prompt):
        state["n"] += 1
        f.opts["upstream"] = "down"

    argv = ["--upstream", "prompt", "--only", "boundary", "--recovery-timeout", "0.2"]
    assert run(f, fixture, *argv, ask=ask) == 1
    assert "sau 0.2s vẫn" in only_failed(cases(capsys), "Phục hồi sau khi upstream")


def test_upstream_leak_fails(gw, fixture, capsys):
    f = gw(leak=True)
    seq = iter(["down", "up"])

    def ask(prompt):
        f.opts["upstream"] = next(seq)

    assert run(f, fixture, "--upstream", "prompt", "--only", "boundary", ask=ask) == 1
    assert "traceback" in only_failed(cases(capsys), "Upstream tắt")


def test_upstream_hang_is_failed_case_not_exit2(gw, fixture, capsys, tmp_path):
    f = gw()
    seq = iter(["hang", "up"])
    out = tmp_path / "e.json"

    def ask(prompt):
        f.opts["upstream"] = next(seq)

    argv = [
        "--upstream",
        "prompt",
        "--only",
        "boundary",
        "--timeout",
        "0.4",
        "--out",
        str(out),
    ]
    assert run(f, fixture, *argv, ask=ask) == 1
    res = cases(capsys)
    assert "ReadTimeout" in only_failed(res, "Upstream tắt")
    assert res["Phục hồi sau khi upstream trở lại"][0] == "đạt"
    assert len(res) == 4  # các ca trước đó vẫn được in
    saved = json.loads(out.read_text(encoding="utf-8"))["results"]
    assert [r["status"] for r in saved].count("lỗi") == 1


def test_no_rate_limit_fails(gw, fixture, capsys):
    assert (
        run(gw(rate_limit=False), fixture, "--upstream", "skip", "--only", "rate") == 1
    )
    assert "không có 429" in only_failed(cases(capsys), "Vượt giới hạn")


@pytest.mark.parametrize(
    ("opts", "prefix", "needle"),
    [
        ({"bad_env": {429}}, "Vượt giới hạn", "envelope"),
        ({"no_rid": {429}}, "Vượt giới hạn", "X-Request-ID"),
        ({"no_rid": {200}}, "Dưới giới hạn", "X-Request-ID"),
        ({"flood_500": True}, "Vượt giới hạn", "5xx"),
        ({"flood_busy": "BAD_GATEWAY"}, "Vượt giới hạn", "5xx"),
        ({"flood_busy": "SERVICE_BUSY", "bad_env": {503}}, "Vượt giới hạn", "5xx"),
        ({"flood_drop": True}, "Vượt giới hạn", "không nhận được phản hồi"),
        ({"server_hdr": {429: "nginx/1.25.3"}}, "Vượt giới hạn", "header server"),
        ({"bad_env": {413}}, "Body", "envelope"),
        ({"no_rid": {413}}, "Body", "X-Request-ID"),
        ({"code413": "TOO_BIG"}, "Body", "FILE_TOO_LARGE"),
        ({"status413": 400}, "Body", "kỳ vọng 413"),
        ({"server_hdr": {413: "nginx/1.25.3"}}, "Body", "header server"),
        ({"strict_limit": True}, "Biên đúng", "không được chặn"),
        ({"no_limit": True}, "Biên 5.242.881", "kỳ vọng 413"),
        ({"message": ""}, "Body", "error.message"),
        ({"message": 5}, "Body", "error.message"),
        ({"server_hdr": {413: "gw/2.1"}}, "Body", "số phiên bản"),
    ],
)
def test_wrong_gateway_fails_exactly_that_case(
    gw, fixture, capsys, opts, prefix, needle
):
    only = {"Dưới": "under", "Vượt": "rate", "Body": "body", "Biên": "boundary"}[
        prefix.split()[0]
    ]
    assert run(gw(**opts), fixture, "--upstream", "skip", "--only", only) == 1
    assert needle in only_failed(cases(capsys), prefix)


def test_under_limit_status_checked(gw, fixture, capsys):
    assert (
        run(gw(under_status=503), fixture, "--upstream", "skip", "--only", "under") == 1
    )
    res = cases(capsys)
    assert res["Dưới giới hạn vẫn 200 + X-Request-ID"] == (
        "lỗi",
        "lần 1: HTTP 503; lần 2: HTTP 503; lần 3: HTTP 503",
    )


def test_api_service_busy_during_flood_is_not_a_gateway_failure(gw, fixture, capsys):
    """D12: slot đầy trả 503 SERVICE_BUSY có envelope; không phải lỗi gateway."""
    code = run(
        gw(flood_busy="SERVICE_BUSY"), fixture, "--upstream", "skip", "--only", "rate"
    )
    assert code == 0
    assert cases(capsys)["Vượt giới hạn trả 429 (không 5xx)"][0] == "đạt"


def test_no_recovery_after_rate_limit_fails(gw, fixture, capsys):
    assert (
        run(gw(never_recover=True), fixture, "--upstream", "skip", "--only", "rate")
        == 1
    )
    res = cases(capsys)
    assert res["Phục hồi sau rate limit"] == ("lỗi", "sau 0.3s chờ: HTTP 429")
    assert res["Vượt giới hạn trả 429 (không 5xx)"][0] == "đạt"


def test_flood_dropped_connection_not_reported_as_5xx(gw, fixture, capsys):
    run(gw(flood_drop=True), fixture, "--upstream", "skip", "--only", "rate")
    assert "phản hồi 5xx" not in only_failed(cases(capsys), "Vượt giới hạn")


def test_retry_after_only_checked_when_required(gw, fixture, capsys):
    f = gw(retry_after=False)
    assert run(f, fixture, "--upstream", "skip", "--only", "rate") == 0
    capsys.readouterr()
    assert (
        run(f, fixture, "--upstream", "skip", "--only", "rate", "--require-retry-after")
        == 1
    )
    assert "Retry-After" in only_failed(cases(capsys), "Vượt giới hạn")


def test_upstream_server_header_leak_fails(gw, fixture, capsys):
    f = gw(server_hdr={502: "nginx/1.25.3"})
    seq = iter(["down", "up"])

    def ask(prompt):
        f.opts["upstream"] = next(seq)

    assert run(f, fixture, "--upstream", "prompt", "--only", "boundary", ask=ask) == 1
    assert "header server" in only_failed(cases(capsys), "Upstream tắt")


def test_stdin_closed_exit_2_keeps_results(gw, fixture, capsys):
    def ask(prompt):
        raise EOFError

    assert (
        run(gw(), fixture, "--upstream", "prompt", "--only", "boundary", ask=ask) == 2
    )
    cap = capsys.readouterr()
    assert "stdin" in cap.err and "Traceback" not in cap.err
    assert "[đạt] Biên đúng" in cap.out


def test_unreachable_exit_2(gw, fixture):
    f = gw()
    f.close()
    assert run(f, fixture, "--upstream", "skip") == 2


@pytest.mark.parametrize(("flag", "val"), [("--rate", "0"), ("--burst", "-1")])
def test_invalid_thresholds_exit_2(fixture, flag, val, capsys):
    argv = ["--base-url", "http://127.0.0.1:1", "--fixture", fixture, "--rate", "10"]
    argv += ["--burst", "1", "--upstream", "skip"]
    argv[argv.index(flag) + 1] = val
    assert main(argv) == 2
    assert "ngưỡng" in capsys.readouterr().err


def test_missing_threshold_exit_2(fixture):
    with pytest.raises(SystemExit) as e:
        main(
            [
                "--base-url",
                "http://127.0.0.1:1",
                "--fixture",
                fixture,
                "--upstream",
                "skip",
            ]
        )
    assert e.value.code == 2


def test_missing_fixture_exit_2(tmp_path):
    argv = ["--base-url", "http://127.0.0.1:1", "--fixture", str(tmp_path / "nope.jpg")]
    assert main([*argv, *ARGS, "--upstream", "skip"]) == 2


def test_out_json_hides_credentials(gw, fixture, tmp_path):
    f = gw()
    out = tmp_path / "e.json"
    url = f.url.replace("http://", "http://u:p@")
    argv = [
        "--base-url",
        url,
        "--fixture",
        fixture,
        *ARGS,
        "--upstream",
        "skip",
        "--out",
        str(out),
    ]
    assert main(argv) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "u:p@" not in data["base_url"] and len(data["results"]) == 6


def down_run(gw, fixture, **opts):
    """Chạy --upstream prompt: tắt upstream ở lần hỏi đầu, bật lại ở lần hai."""
    f = gw(**opts)
    seq = iter(["down", "up"])

    def ask(prompt):
        f.opts["upstream"] = next(seq)

    return run(f, fixture, "--upstream", "prompt", "--only", "boundary", ask=ask)


def test_server_header_without_version_is_not_a_leak(gw, fixture, capsys):
    hdr = {429: "nginx", 413: "nginx", 502: "nginx", 200: "nginx"}
    assert down_run(gw, fixture, server_hdr=hdr) == 0
    assert "[lỗi]" not in capsys.readouterr().out


@pytest.mark.parametrize("value", ["nginx/1.25.3", "uvicorn/0.54", "gw/2.1"])
def test_server_header_with_version_is_a_leak(gw, fixture, capsys, value):
    assert down_run(gw, fixture, server_hdr={502: value}) == 1
    assert "số phiên bản" in only_failed(cases(capsys), "Upstream tắt")


@pytest.mark.parametrize("value", ["Express", "PHP/8.2"])
def test_x_powered_by_is_always_a_leak(gw, fixture, capsys, value):
    assert down_run(gw, fixture, powered={502: value}) == 1
    assert "x-powered-by" in only_failed(cases(capsys), "Upstream tắt")


def test_json_escaped_file_marker_is_detected(gw, fixture, capsys):
    assert down_run(gw, fixture, file_msg=True) == 1
    assert 'file "' in only_failed(cases(capsys), "Upstream tắt")


@pytest.mark.parametrize("status", [503, 504])
def test_other_gateway_failures_accepted(gw, fixture, capsys, status):
    assert down_run(gw, fixture, down_status=status) == 0
    assert cases(capsys)["Upstream tắt/chậm trả lỗi gateway sạch"] == (
        "đạt",
        f"HTTP {status}",
    )


def test_upstream_500_is_not_a_gateway_failure(gw, fixture, capsys):
    assert down_run(gw, fixture, down_status=500) == 1
    assert "kỳ vọng 502/503/504" in only_failed(cases(capsys), "Upstream tắt")


def test_no_forwarded_for_header_sent(gw, fixture):
    assert run(gw(xff_reject=True), fixture, "--upstream", "skip") == 0


def test_connect_error_midway_is_failed_case_not_exit2(gw, fixture, capsys):
    f = gw(close_after=True)

    def ask(prompt):
        f.close()  # gateway biến mất sau khi đã có phản hồi

    argv = ["--upstream", "prompt", "--only", "boundary", "--recovery-timeout", "0.1"]
    assert run(f, fixture, *argv, ask=ask) == 1
    res = cases(capsys)
    assert res["Biên đúng 5.242.880 B"][0] == "đạt"
    failed = {k for k, v in res.items() if v[0] == "lỗi"}
    assert failed == {
        "Upstream tắt/chậm trả lỗi gateway sạch",
        "Phục hồi sau khi upstream trở lại",
    }
    assert "ConnectError" in res["Upstream tắt/chậm trả lỗi gateway sạch"][1]
