"""UI Streamlit qua gateway Nginx thật (AC-29, T026): phiên độc lập, lỗi không lộ kết quả phiên khác.

Cần stack Compose đang chạy với model thật (REALCHECK_GATEWAY_URL trỏ tới cổng Nginx). Điều khiển UI
bằng AppTest trỏ tới gateway; không dùng trình duyệt nên không kiểm theme, giới hạn tải 5 MiB, widget.
"""

import io
import os
import re
import socket
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import numpy as np
import pytest
from PIL import Image
from streamlit.testing.v1 import AppTest

GATEWAY = os.environ["REALCHECK_GATEWAY_URL"].rstrip("/")
ROOT = Path(__file__).resolve().parents[2]
APP = str(ROOT / "streamlit" / "app.py")


@pytest.fixture(autouse=True)
def streamlit_on_path(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "streamlit"))


def noise_jpeg(seed, size=(640, 480)):
    pixels = np.random.default_rng(seed).integers(0, 256, (size[1], size[0], 3))
    stream = io.BytesIO()
    Image.fromarray(pixels.astype(np.uint8)).save(stream, "JPEG")
    return stream.getvalue()


def open_app():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    return at


def upload(at, name, data, mime="image/jpeg"):
    at.file_uploader[0].set_value((name, data, mime))
    at.run()
    assert not at.exception
    return at


def submit(at):
    at.button[0].click().run()
    assert not at.exception
    return at


def html(at):
    return "\n".join(element.value for element in at.get("html"))


def title(at):
    found = re.search(r'rc-verdict[^"]*"><b>(.*?)</b>', html(at))
    return found.group(1) if found else None


def sidebar_text(at):
    return " ".join(e.value for e in at.sidebar if hasattr(e, "value"))


def test_gateway_serves_the_ui_page():
    response = httpx.get(GATEWAY + "/", timeout=30)
    assert response.status_code == 200 and "streamlit" in response.text.lower()


def test_gateway_upgrades_the_streamlit_websocket():
    parts = urlsplit(GATEWAY)
    host, port = parts.hostname, parts.port or 80
    request = (
        f"GET /_stcore/stream HTTP/1.1\r\nHost: {host}:{port}\r\n"
        "Upgrade: websocket\r\nConnection: Upgrade\r\n"
        "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
        f"Origin: http://{host}:{port}\r\n\r\n"
    )
    with socket.create_connection((host, port), timeout=15) as sock:
        sock.sendall(request.encode())
        status_line = sock.recv(256).split(b"\r\n", 1)[0]
    assert b"101" in status_line


def test_ui_reports_the_system_ready_through_the_gateway():
    assert "Hệ thống sẵn sàng" in sidebar_text(open_app())


def test_a_real_upload_through_the_gateway_shows_a_verdict():
    at = submit(upload(open_app(), "a.jpg", noise_jpeg(1)))
    assert title(at) is not None and not at.error


def test_two_sessions_do_not_share_results():
    first = submit(upload(open_app(), "a.jpg", noise_jpeg(2)))
    assert title(first) is not None
    second = open_app()
    assert title(second) is None and not second.error
    assert "Điểm" not in " ".join(e.value for e in second.markdown), (
        "không thấy điểm của phiên khác"
    )


def test_a_second_session_that_only_uploads_never_sees_the_first_sessions_result():
    """Phiên B tải ảnh nhưng chưa bấm gửi: không được thấy kết quả đã có của phiên A."""
    first = submit(upload(open_app(), "a.jpg", noise_jpeg(6)))
    assert title(first) is not None
    second = upload(open_app(), "b.jpg", noise_jpeg(7))
    assert title(second) is None and not second.error
    assert any("Bấm nút để gửi ảnh" in c.value for c in second.caption)
    assert second.button[0].disabled is False


def test_an_error_in_one_session_never_shows_the_other_sessions_result():
    first = submit(upload(open_app(), "a.jpg", noise_jpeg(3)))
    kept = title(first)
    assert kept is not None
    second = submit(upload(open_app(), "gia.jpg", b"khong phai anh"))
    assert title(second) is None and len(second.error) == 1
    assert "Không đọc được ảnh" in second.error[0].value
    first.run()
    assert title(first) == kept, "phiên đầu giữ kết quả của chính nó"


def test_a_new_upload_in_the_same_session_does_not_show_the_old_result():
    at = submit(upload(open_app(), "a.jpg", noise_jpeg(4)))
    assert title(at) is not None
    upload(at, "b.jpg", noise_jpeg(5))
    assert title(at) is None
    assert at.button[0].disabled is False
