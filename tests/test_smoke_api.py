"""Logic của scripts/smoke_api.py, kiểm bằng server HTTP giả (stdlib, thread)."""

import json
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts import make_fixtures, smoke_api

GOOD = {
    "verdict": "likely_real",
    "score": 0.2,
    "exif": "Không có EXIF",
    "reason": "Ảnh có vẻ thật.",
}
HEALTH = {"status": "ok", "model_ready": True}
# Bảng D05 viết tay, độc lập với smoke_api.ERR_CASES để bắt sửa nhầm kỳ vọng.
ERRORS = {
    "empty.jpg": (400, "EMPTY_FILE"),
    "fake_text.jpg": (400, "INVALID_IMAGE"),
    "truncated.jpg": (400, "INVALID_IMAGE"),
    "multiframe.png": (415, "UNSUPPORTED_FORMAT"),
    "multiframe.gif": (415, "UNSUPPORTED_FORMAT"),
    "small_200x200.jpg": (422, "IMAGE_TOO_SMALL"),
    "small_255x400.jpg": (422, "IMAGE_TOO_SMALL"),
    "over_5242881.jpg": (413, "FILE_TOO_LARGE"),
    "many_pixels_6000x6000.png": (413, "TOO_MANY_PIXELS"),
    "many_side_10001x300.png": (413, "TOO_MANY_PIXELS"),
}


def _rid():
    return str(uuid.uuid4())


def _raw(status, body, rid=_rid):
    rid = rid() if callable(rid) else rid
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return status, {"X-Request-ID": rid} if rid else {}, text


def _err(status, code, header_rid=None, **extra):
    """Envelope lỗi đúng; header_rid/extra để cố ý làm sai."""
    rid = _rid()
    err = {"code": code, "message": "Lỗi.", "request_id": rid, **extra}
    return _raw(status, {"error": err}, rid=rid if header_rid is None else header_rid)


def contract(method, path, names):
    """Đáp án đúng hợp đồng; names là các filename trong multipart."""
    if method == "GET":
        if path == "/health":
            return _raw(200, HEALTH)
        if path in ("/docs", "/openapi.json"):
            return 200, {}, "{}"
        if path == "/v1/analyze":
            return _err(405, "METHOD_NOT_ALLOWED")
        return _err(404, "NOT_FOUND")
    if not names:
        return _err(422, "MISSING_FILE")
    if len(names) > 1:
        return _err(422, "MULTIPLE_FILES")
    if names[0] in ERRORS:
        return _err(*ERRORS[names[0]])
    return _raw(200, GOOD)


@pytest.fixture
def serve():
    servers = []

    def start(override=None):
        override = override or {}

        class Handler(BaseHTTPRequestHandler):
            def _do(self, method):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                names = [
                    n.decode()
                    for n in re.findall(rb'name="file"; filename="([^"]*)"', body)
                ]
                key = (method, self.path, names[0] if len(names) == 1 else None)
                resp = override.get(key) or contract(method, self.path, names)
                if resp == "hang":
                    time.sleep(1.5)
                    return
                status, headers, text = resp
                data = text.encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in headers.items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._do("GET")

            def do_POST(self):
                self._do("POST")

            def log_message(self, *_):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return f"http://127.0.0.1:{srv.server_port}"

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    out = tmp_path_factory.mktemp("smoke-fx")
    make_fixtures.generate(out)
    return out


def run(base, fx, tmp_path, *extra):
    out = tmp_path / "evidence.json"
    code = smoke_api.main(
        ["--base-url", base, "--fixtures", str(fx), "--out", str(out), *extra]
    )
    return code, json.loads(out.read_text(encoding="utf-8")) if out.exists() else None


def failed(evidence):
    return {r["case"] for r in evidence["results"] if r["status"] == "lỗi"}


def post(name, resp):
    return {("POST", "/v1/analyze", name): resp}


def test_contract_server_exits_0(serve, fx, tmp_path, capsys):
    code, ev = run(serve(), fx, tmp_path)
    assert code == 0 and not failed(ev)
    assert "Tổng" in capsys.readouterr().out
    assert all(
        "file" not in r or isinstance(r["file"], str | type(None))
        for r in ev["requests"]
    )


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "score": 1.5},
        {**GOOD, "score": -0.1},
        {**GOOD, "score": float("nan")},
        {**GOOD, "score": "0.2"},
        {**GOOD, "score": "0.5"},
        {**GOOD, "score": None},
        {**GOOD, "score": True},
        {**GOOD, "score": False},
        {k: v for k, v in GOOD.items() if k != "exif"},
        {**GOOD, "debug": 1},
        {**GOOD, "reason": ""},
        {**GOOD, "reason": "Plain English."},
        {**GOOD, "verdict": "real"},
    ],
)
def test_bad_200_body_fails_that_case(serve, fx, tmp_path, bad):
    ov = post("ok_valid.png", _raw(200, bad))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"PNG hợp lệ"}


def test_missing_request_id_header_fails(serve, fx, tmp_path):
    code, ev = run(serve(post("ok_valid.png", _raw(200, GOOD, rid=None))), fx, tmp_path)
    assert code == 1 and failed(ev) == {"PNG hợp lệ"}


def test_wrong_http_for_error_code_fails(serve, fx, tmp_path):
    ov = post("empty.jpg", _err(422, "EMPTY_FILE"))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"File 0 byte"}


def test_wrong_error_code_fails(serve, fx, tmp_path):
    ov = post("small_200x200.jpg", _err(422, "INVALID_REQUEST"))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"Ảnh 200x200"}


def test_error_without_envelope_fails(serve, fx, tmp_path):
    ov = post("fake_text.jpg", _raw(400, {"detail": "x"}))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"Text giả .jpg"}


def test_health_not_ready_reported(serve, fx, tmp_path):
    ov = {
        ("GET", "/health", None): _raw(
            503, {"status": "not_ready", "model_ready": False}
        )
    }
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"GET /health"}
    assert (
        "not_ready"
        in next(r for r in ev["results"] if r["case"] == "GET /health")["actual"]
    )


def test_real_and_ai_never_fail_on_label_but_warn_off_schema(serve, fx, tmp_path):
    real, ai = tmp_path / "real.png", tmp_path / "ai.png"
    real.write_bytes((fx / "ok_valid.png").read_bytes())
    ai.write_bytes((fx / "ok_valid.png").read_bytes())
    ai_wrong = {**GOOD, "verdict": "likely_real", "score": 0.01}
    ov = post("ai.png", _raw(200, ai_wrong))
    code, ev = run(serve(ov), fx, tmp_path, "--real", str(real), "--ai", str(ai))
    assert code == 0
    assert [r["status"] for r in ev["results"][-2:]] == ["ghi nhận", "ghi nhận"]
    ov = post("ai.png", _raw(200, {**GOOD, "score": 2}))
    code, ev = run(serve(ov), fx, tmp_path, "--ai", str(ai))
    assert code == 0 and ev["results"][-1]["status"] == "cảnh báo"


def test_no_listener_exits_2(fx, tmp_path, capsys):
    code, ev = run("http://127.0.0.1:9", fx, tmp_path)
    assert code == 2 and ev["exit_code"] == 2 and ev["results"] == []
    assert "Không kết nối" in capsys.readouterr().err


def test_missing_fixture_exits_2(serve, tmp_path, capsys):
    code, _ = run(serve(), tmp_path, tmp_path)
    assert code == 2 and "Thiếu fixture" in capsys.readouterr().err


def test_expected_errors_match_d05_table():
    assert {f: (s, c) for _, f, s, c in smoke_api.ERR_CASES} == ERRORS


# Mỗi test dưới đây đặt tên theo một đột biến từng sống sót.
def test_mutant_error_envelope_extra_field(serve, fx, tmp_path):
    code, ev = run(
        serve(post("empty.jpg", _err(400, "EMPTY_FILE", debug="x"))), fx, tmp_path
    )
    assert code == 1 and failed(ev) == {"File 0 byte"}


def test_mutant_error_body_request_id_differs_from_header(serve, fx, tmp_path):
    ov = post("empty.jpg", _err(400, "EMPTY_FILE", header_rid=_rid()))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"File 0 byte"}


def test_mutant_error_response_missing_request_id_header(serve, fx, tmp_path):
    ov = post("empty.jpg", _err(400, "EMPTY_FILE", header_rid=""))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"File 0 byte"}


def test_mutant_no_timeout_hang_stops_after_first_request(serve, fx, tmp_path, capsys):
    base = serve({("GET", "/health", None): "hang"})
    code, ev = run(base, fx, tmp_path, "--timeout", "0.3")
    assert code == 2 and len(ev["requests"]) == 1 and ev["results"] == []
    err = capsys.readouterr().err
    assert base in err and "0.3s" in err and "/health" in err


def test_timeout_mid_run_names_case_and_stops(serve, fx, tmp_path, capsys):
    base = serve(post("ok_valid.png", "hang"))
    code, ev = run(base, fx, tmp_path, "--timeout", "0.3")
    assert code == 2
    assert (
        ev["requests"][-1]["file"] == "ok_valid.png" and "error" in ev["requests"][-1]
    )
    assert len(ev["requests"]) == 7  # health, 2 docs, 3 ca JPEG, rồi PNG treo
    assert "ok_valid.png" in capsys.readouterr().err


def test_non_uuid_request_id_fails(serve, fx, tmp_path):
    ov = post("ok_valid.png", _raw(200, GOOD, rid="rid-1"))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"PNG hợp lệ"}


def test_duplicate_request_ids_fail(serve, fx, tmp_path):
    same = _rid()
    ov = {
        **post("ok_valid.png", _raw(200, GOOD, rid=same)),
        **post("ok_256x256.png", _raw(200, GOOD, rid=same)),
    }
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"X-Request-ID khác nhau giữa các request"}


def test_no_docs_flag_is_skipped_not_passed(serve, fx, tmp_path):
    code, ev = run(serve(), fx, tmp_path, "--no-docs")
    assert code == 0
    docs = [r for r in ev["results"] if r["case"] in ("GET /docs", "GET /openapi.json")]
    assert [r["status"] for r in docs] == ["bỏ qua", "bỏ qua"]
    assert not [q for q in ev["requests"] if q["path"] in ("/docs", "/openapi.json")]


def test_docs_checked_by_default(serve, fx, tmp_path):
    ov = {("GET", "/docs", None): _raw(404, "x")}
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {"GET /docs"}


def test_size_boundary_failure_hints_not_blaming_api(serve, fx, tmp_path):
    ov = post("limit_5242880.jpg", _err(413, "FILE_TOO_LARGE"))
    code, ev = run(serve(ov), fx, tmp_path)
    assert code == 1 and failed(ev) == {smoke_api.SIZE_CASE}
    assert (
        "overhead multipart"
        in next(r for r in ev["results"] if r["case"] == smoke_api.SIZE_CASE)["actual"]
    )


def test_skip_size_boundary_flag(serve, fx, tmp_path):
    ov = post("limit_5242880.jpg", _err(413, "FILE_TOO_LARGE"))
    code, ev = run(serve(ov), fx, tmp_path, "--skip-size-boundary")
    assert code == 0
    assert (
        next(r for r in ev["results"] if r["case"] == smoke_api.SIZE_CASE)["status"]
        == "bỏ qua"
    )


def test_evidence_redacts_userinfo(serve, fx, tmp_path):
    base = serve().replace("http://", "http://user:secret@")
    code, ev = run(base, fx, tmp_path)
    assert (
        code == 0
        and "secret" not in json.dumps(ev)
        and ev["base_url"].startswith("http://127.0.0.1")
    )


@pytest.mark.parametrize(
    ("status", "code", "hint"),
    [
        (404, "NOT_FOUND", False),
        (503, "MODEL_NOT_READY", False),
        (400, "INVALID_IMAGE", True),
        (413, "FILE_TOO_LARGE", True),
        (422, "IMAGE_TOO_SMALL", True),
    ],
)
def test_size_hint_only_for_4xx_except_404(serve, fx, tmp_path, status, code, hint):
    code_, ev = run(serve(post("limit_5242880.jpg", _err(status, code))), fx, tmp_path)
    actual = next(r for r in ev["results"] if r["case"] == smoke_api.SIZE_CASE)[
        "actual"
    ]
    assert code_ == 1 and ("overhead multipart" in actual) is hint


def test_summary_line_when_every_post_is_404(serve, fx, tmp_path, capsys):
    ov = {("POST", "/v1/analyze", None): _err(404, "NOT_FOUND")}
    ov.update(
        {
            ("POST", "/v1/analyze", f): _err(404, "NOT_FOUND")
            for f in smoke_api.FIXTURE_FILES
        }
    )
    code, _ = run(serve(ov), fx, tmp_path)
    assert code == 1
    assert (
        "POST /v1/analyze chưa tồn tại (404 cho mọi ca): chưa thể kiểm hợp đồng"
        in capsys.readouterr().out
    )


def test_no_summary_line_when_only_some_posts_404(serve, fx, tmp_path, capsys):
    code, _ = run(serve(post("empty.jpg", _err(404, "NOT_FOUND"))), fx, tmp_path)
    assert code == 1
    assert "chưa tồn tại" not in capsys.readouterr().out


def test_unknown_path_probe_stays_under_v1(serve, fx, tmp_path):
    """Qua gateway, đường dẫn gốc không khớp thuộc UI (200); ca 404 phải nằm dưới /v1/."""
    code, ev = run(serve(), fx, tmp_path)
    assert code == 0
    unknown = [q["path"] for q in ev["requests"] if "khong-co" in q["path"]]
    assert unknown == ["/v1/khong-co-duong-nay"]


def test_delay_sleeps_between_requests_but_not_before_the_first(
    serve, fx, tmp_path, monkeypatch
):
    sleeps = []
    monkeypatch.setattr("scripts.smoke_api.time.sleep", sleeps.append)
    code, ev = run(serve(), fx, tmp_path, "--delay", "0.15")
    assert code == 0
    assert sleeps and set(sleeps) == {0.15}
    assert len(sleeps) == len(ev["requests"]) - 1


def test_default_has_no_delay(serve, fx, tmp_path, monkeypatch):
    sleeps = []
    monkeypatch.setattr("scripts.smoke_api.time.sleep", sleeps.append)
    assert run(serve(), fx, tmp_path)[0] == 0
    assert sleeps == []
