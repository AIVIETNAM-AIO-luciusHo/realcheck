from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.errors import ERROR_TABLE, ApiError
from app.main import create_app
from app.schemas import ErrorCode, ErrorResponse


def _assert_envelope(r, status, code):
    assert r.status_code == status
    body = ErrorResponse.model_validate(r.json())
    assert body.error.code == code
    assert body.error.request_id == r.headers["X-Request-ID"]
    return body


@pytest.fixture
def boom_client():
    """Thêm route lỗi vào instance app của test, không sửa code app."""
    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret /home/x/leak.py")

    @app.get("/api-error")
    async def api_error():
        raise ApiError(ErrorCode.MODEL_TIMEOUT)

    @app.get("/need-int")
    async def need_int(n: int):
        return n

    # raise_server_exceptions=False để nhận response 500 thay vì ném lại
    return TestClient(app, raise_server_exceptions=False)


def test_404_envelope(client):
    _assert_envelope(client.get("/khong-co"), 404, ErrorCode.NOT_FOUND)


def test_405_envelope_va_header_allow(client):
    r = client.post("/health")
    _assert_envelope(r, 405, ErrorCode.METHOD_NOT_ALLOWED)
    assert "GET" in r.headers["allow"]


def test_422_invalid_request_khong_lo_chi_tiet_pydantic(boom_client):
    r = boom_client.get("/need-int", params={"n": "abc"})
    _assert_envelope(r, 422, ErrorCode.INVALID_REQUEST)
    assert "detail" not in r.json()


def test_api_error_dung_bang_ERROR_TABLE(boom_client):
    status, message = ERROR_TABLE[ErrorCode.MODEL_TIMEOUT]
    r = boom_client.get("/api-error")
    body = _assert_envelope(r, status, ErrorCode.MODEL_TIMEOUT)
    assert body.error.message == message


def test_500_khong_lo_stacktrace_hay_duong_dan(boom_client):
    r = boom_client.get("/boom")
    body = _assert_envelope(r, 500, ErrorCode.INTERNAL_ERROR)
    assert body.error.message == ERROR_TABLE[ErrorCode.INTERNAL_ERROR][1]
    for leak in ("Traceback", "RuntimeError", "secret", "/home/", ".py"):
        assert leak not in r.text


def test_error_table_phu_het_error_code():
    assert set(ERROR_TABLE) == set(ErrorCode)


def test_request_id_sinh_khi_thieu(client):
    rid = client.get("/health").headers["X-Request-ID"]
    assert str(UUID(rid)) == rid


def test_request_id_giu_nguyen_khi_client_gui_uuid(client):
    rid = "123e4567-e89b-42d3-a456-426614174000"
    r = client.get("/health", headers={"X-Request-ID": rid})
    assert r.headers["X-Request-ID"] == rid


def test_request_id_la_bi_thay_bang_uuid_moi(client):
    r = client.get("/health", headers={"X-Request-ID": "evil\tvalue"})
    assert r.headers["X-Request-ID"] != "evil\tvalue"
    UUID(r.headers["X-Request-ID"])


def test_request_id_giu_nguyen_trong_loi(client):
    rid = "123e4567-e89b-42d3-a456-426614174000"
    r = client.get("/khong-co", headers={"X-Request-ID": rid})
    assert r.json()["error"]["request_id"] == rid
