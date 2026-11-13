"""Mã lỗi gateway (D05, Lực duyệt 2026-11-12): nginx/nginx.conf và app/ phải khớp nhau.

Nginx tự trả 413/429/502/504 bằng chuỗi JSON viết cứng trong nginx.conf; ErrorCode và
ERROR_TABLE là nơi ghi hợp đồng mã lỗi. Test này chặn hai nơi lệch nhau khi một bên đổi.
"""

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.errors import ERROR_TABLE
from app.main import create_app
from app.schemas import ErrorCode

NGINX_CONF = Path(__file__).resolve().parents[1] / "nginx" / "nginx.conf"
GATEWAY_CODES = {"FILE_TOO_LARGE", "RATE_LIMITED", "API_UNAVAILABLE", "GATEWAY_TIMEOUT"}


def nginx_error_bodies():
    """(status, body JSON) của mọi `return <status> '...'` trong nginx.conf."""
    text = NGINX_CONF.read_text(encoding="utf-8")
    found = []
    for status, raw in re.findall(r"return\s+(\d{3})\s+'(\{.*?\})';", text):
        body = json.loads(raw.replace("$realcheck_request_id", "x"))
        found.append((int(status), body))
    return found


def test_nginx_tra_dung_bon_ma_gateway():
    codes = {body["error"]["code"] for _, body in nginx_error_bodies()}
    assert codes == GATEWAY_CODES


def test_ma_va_thong_bao_cua_nginx_trung_error_table():
    for status, body in nginx_error_bodies():
        error = body["error"]
        code = ErrorCode(error["code"])
        assert set(error) == {"code", "message", "request_id"}
        assert (status, error["message"]) == ERROR_TABLE[code], code


def test_openapi_khai_bao_loi_gateway_cho_analyze():
    spec = TestClient(create_app()).get("/openapi.json").json()
    responses = spec["paths"]["/v1/analyze"]["post"]["responses"]
    assert "RATE_LIMITED" in responses["429"]["description"]
    assert "API_UNAVAILABLE" in responses["502"]["description"]
    assert "GATEWAY_TIMEOUT" in responses["504"]["description"]
