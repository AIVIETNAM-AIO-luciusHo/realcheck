"""Hai thay đổi hành vi theo câu trả lời issue #43 (D05 làm rõ, 2026-11-11).

Câu 1: INVALID_REQUEST luôn 422, kể cả khi framework trả 400 vì body multipart hỏng.
Câu 5: score phải là float (Python hoặc numpy); str, int, bool, None là 500 MODEL_ERROR.
Thứ tự kiểm tra (câu 2, 4) và định dạng exif (câu 3) không đổi mã; Lực khóa bằng test ở PR riêng.
"""

import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import create_app

URL = "/v1/analyze"


def jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), (120, 80, 40)).save(buf, "JPEG")
    return buf.getvalue()


def client_for(scorer):
    return TestClient(create_app(scorer=scorer), raise_server_exceptions=False)


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_multipart_hong_la_422_invalid_request_va_khong_goi_model():
    calls = []
    client = client_for(lambda image: calls.append(1) or 0.5)
    r = client.post(
        URL,
        content=b"--x\r\nkhong phai multipart\r\n",
        headers={"content-type": "multipart/form-data; boundary=yyy"},
    )
    assert_error(r, 422, "INVALID_REQUEST")
    assert calls == []


@pytest.mark.parametrize(
    "value",
    [0.5, np.float32(0.5), np.float64(0.5), np.array(0.5)],
    ids=["float", "np_float32", "np_float64", "np_0d"],
)
def test_score_float_duoc_nhan(value):
    r = client_for(lambda image: value).post(URL, files={"file": ("a.jpg", jpeg())})
    assert r.status_code == 200, r.text
    assert r.json()["score"] == 0.5


@pytest.mark.parametrize(
    "value",
    ["0.5", 0, 1, True, False, None, np.int64(1), np.bool_(True), np.array([0.5])],
    ids=["str", "int0", "int1", "true", "false", "none", "np_int", "np_bool", "np_1d"],
)
def test_score_khong_phai_float_la_model_error(value):
    r = client_for(lambda image: value).post(URL, files={"file": ("a.jpg", jpeg())})
    assert_error(r, 500, "MODEL_ERROR")
    assert "verdict" not in r.text
