"""Giao diện Streamlit với HTTP giả và với FastAPI thật, không cần mạng hay model."""

import io
import json
import re
from datetime import timedelta
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from streamlit.testing.v1 import AppTest

import streamlit as st
from app.main import create_app
from models.normalize import normalize_image

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "streamlit" / "app.py")
EVALUATION_PAGE = str(ROOT / "streamlit" / "pages" / "1_Ket_qua_danh_gia.py")
OK_BODY = {"verdict": "likely_ai", "score": 0.87, "exif": "Apple", "reason": "Lý do"}


def png(size=(300, 300), color=(10, 20, 30)):
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, "PNG")
    return stream.getvalue()


def response(status=200, body=None, text=None):
    if text is not None:
        result = httpx.Response(status, text=text, headers={"X-Request-ID": "rid-1"})
    else:
        result = httpx.Response(status, json=body, headers={"X-Request-ID": "rid-1"})
    result.elapsed = timedelta(seconds=0.25)
    return result


class FakeApi:
    """Thay httpx: ghi lại mọi POST, trả lần lượt các phản hồi đã đặt."""

    def __init__(self):
        self.posts = []
        self.replies = []
        self.health = response(200, {"status": "ok"})

    def post(self, url, *, files, timeout):
        self.posts.append({"url": url, "files": files, "timeout": timeout})
        reply = self.replies.pop(0) if self.replies else response(200, OK_BODY)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def get(self, url, *, timeout):
        if isinstance(self.health, Exception):
            raise self.health
        return self.health


@pytest.fixture
def api(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "streamlit"))
    fake = FakeApi()
    monkeypatch.setattr(httpx, "post", fake.post)
    monkeypatch.setattr(httpx, "get", fake.get)
    st.cache_data.clear()
    yield fake
    st.cache_data.clear()


def open_app():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    return at


def upload(at, name="a.png", data=None, mime="image/png"):
    at.file_uploader[0].set_value((name, png() if data is None else data, mime))
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


def score_text(at):
    found = re.search(r'rc-score"><strong>(.*?)</strong>', html(at))
    return found.group(1) if found else None


def captions(at):
    return " ".join(element.value for element in at.caption)


def test_upload_does_not_call_api_until_click(api):
    at = upload(open_app())
    assert api.posts == []
    assert at.button[0].disabled is False
    assert title(at) is None


def test_upload_shows_file_facts_and_warns_small_image(api):
    at = upload(open_app(), data=png((200, 150)))
    assert "200 × 150 px" in html(at)
    assert any("256 px" in warning.value for warning in at.warning)
    assert api.posts == []


def test_upload_unreadable_file_does_not_crash_and_can_be_sent(api):
    api.replies = [response(400, {"error": {"message": "Ảnh hỏng."}})]
    at = upload(open_app(), "gia.jpg", b"khong phai anh", "image/jpeg")
    assert any("Không xem trước" in info.value for info in at.info)
    submit(at)
    assert [error.value for error in at.error] == ["Ảnh hỏng."]
    assert len(api.posts) == 1


def test_upload_new_file_clears_old_result_even_with_same_content(api):
    at = submit(upload(open_app(), "a.png"))
    assert title(at) == "Ảnh AI"
    upload(at, "b.png")
    assert title(at) is None
    assert at.button[0].disabled is False
    assert len(api.posts) == 1


def test_upload_new_file_that_errors_does_not_show_old_result(api):
    at = submit(upload(open_app(), "a.png"))
    api.replies = [response(503, {})]
    submit(upload(at, "b.png", png(color=(1, 2, 3))))
    assert title(at) is None and score_text(at) is None
    assert len(at.error) == 1


def test_one_click_sends_one_post_with_the_file(api):
    data = png()
    at = submit(upload(open_app(), "anh.png", data))
    assert len(api.posts) == 1
    sent = api.posts[0]
    assert sent["url"].endswith("/v1/analyze") and sent["timeout"] > 0
    assert sent["files"]["file"] == ("anh.png", data, "image/png")
    at.run()
    assert len(api.posts) == 1, "chạy lại trang không được gửi lại"


def test_result_button_stays_locked_after_success(api):
    at = submit(upload(open_app()))
    assert at.button[0].disabled is True
    at.run()
    assert at.button[0].disabled is True and len(api.posts) == 1


@pytest.mark.parametrize(
    "verdict,score,expected,percent,low_confidence",
    [
        ("likely_real", 0.12, "Ảnh thật", "12%", False),
        ("uncertain", 0.3, "Dự đoán thật", "30%", True),
        ("uncertain", 0.49, "Dự đoán thật", "49%", True),
        ("uncertain", 0.5, "Dự đoán AI", "50%", True),
        ("uncertain", 0.7, "Dự đoán AI", "70%", True),
        ("likely_ai", 0.87, "Ảnh AI", "87%", False),
    ],
)
def test_result_levels_keep_uncertain_label(
    api, verdict, score, expected, percent, low_confidence
):
    api.replies = [response(200, {**OK_BODY, "verdict": verdict, "score": score})]
    at = submit(upload(open_app()))
    assert title(at) == expected
    assert score_text(at) == percent
    assert ("Phân loại: Chưa chắc" in html(at)) is low_confidence
    assert html(at).count('class="rc-zone') == 4
    assert f"left:{score * 100}%" in html(at)
    assert not at.error


def test_result_shows_reason_exif_limits_and_request_id(api):
    at = submit(upload(open_app()))
    assert "<p>Lý do</p>" in html(at) and "<p>Apple</p>" in html(at)
    assert "không phải xác suất" in captions(at)
    assert "rid-1" in captions(at)
    assert any("chỉ để tham khảo" in warning.value for warning in at.warning)


def test_result_text_from_api_is_escaped(api):
    body = {**OK_BODY, "reason": "<img src=x>", "exif": "<script>x</script>"}
    api.replies = [response(200, body)]
    at = submit(upload(open_app(), "<b>ten.png"))
    page = html(at)
    assert "<img" not in page and "<script" not in page
    assert "&lt;img src=x&gt;" in page and "&lt;b&gt;ten.png" in page


@pytest.mark.parametrize(
    "status,body,message",
    [
        (400, {"error": {"message": "Ảnh hỏng."}}, "Ảnh hỏng."),
        (413, {"error": {"message": "Quá nhiều pixel."}}, "Quá nhiều pixel."),
        (413, {}, "giảm dung lượng"),
        (415, {"error": {"message": "Sai định dạng."}}, "Sai định dạng."),
        (422, {"error": {"message": "Ảnh quá nhỏ."}}, "Ảnh quá nhỏ."),
        (429, {}, "đợi"),
        (500, {"error": {"message": "/duong/dan/bi-mat"}}, "mã 500"),
        (502, {}, "chưa sẵn sàng"),
        (503, {}, "chưa sẵn sàng"),
        (504, {}, "quá lâu"),
    ],
)
def test_error_status_shows_message_without_result_or_retry(api, status, body, message):
    api.replies = [response(status, body)]
    at = submit(upload(open_app()))
    assert len(at.error) == 1 and message in at.error[0].value
    assert "bi-mat" not in at.error[0].value
    assert title(at) is None and score_text(at) is None
    assert "rid-1" in captions(at)
    assert len(api.posts) == 1


def gateway_errors():
    """Body lỗi đúng như nginx/nginx.conf trả (D05 lỗi gateway), để test không lệch cấu hình."""
    conf = (ROOT / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    found = re.findall(r"return (\d{3}) '(\{.*\})';", conf)
    return {
        int(status): json.loads(body.replace("$realcheck_request_id", "rid-1"))
        for status, body in found
    }


@pytest.mark.parametrize(
    "status,code,message",
    [
        (413, "FILE_TOO_LARGE", "File ảnh vượt quá dung lượng cho phép."),
        (429, "RATE_LIMITED", "đợi một lát"),
        (502, "API_UNAVAILABLE", "chưa sẵn sàng"),
        (504, "GATEWAY_TIMEOUT", "quá lâu"),
    ],
)
def test_gateway_error_shows_vietnamese_message_without_retry(
    api, status, code, message
):
    body = gateway_errors()[status]
    assert body["error"]["code"] == code
    reply = response(status, body)
    if status == 429:
        reply.headers["Retry-After"] = "1"
    api.replies = [reply]
    at = submit(upload(open_app()))
    assert len(at.error) == 1 and message in at.error[0].value
    assert code not in at.error[0].value and "mã" not in at.error[0].value
    assert title(at) is None and score_text(at) is None
    assert "rid-1" in captions(at)
    assert len(api.posts) == 1, "không tự gửi lại, kể cả khi có Retry-After"


@pytest.mark.parametrize(
    "failure,message",
    [
        (httpx.ConnectError("x"), "Không kết nối được"),
        (httpx.ReadTimeout("x"), "quá lâu"),
    ],
)
def test_error_network_shows_message_without_retry(api, failure, message):
    api.replies = [failure]
    at = submit(upload(open_app()))
    assert message in at.error[0].value and title(at) is None
    assert len(api.posts) == 1


@pytest.mark.parametrize(
    "reply",
    [
        response(200, {**OK_BODY, "score": 1.7}),
        response(200, {**OK_BODY, "score": True}),
        response(200, {**OK_BODY, "verdict": "khac"}),
        response(200, {**OK_BODY, "reason": "  "}),
        response(200, {"verdict": "likely_ai"}),
        response(200, text="<html>"),
    ],
)
def test_error_invalid_response_is_never_shown_as_result(api, reply):
    api.replies = [reply]
    at = submit(upload(open_app()))
    assert "không hợp lệ" in at.error[0].value and title(at) is None


def test_retry_only_happens_when_user_clicks_again(api):
    api.replies = [response(429, {}), response(200, OK_BODY)]
    at = submit(upload(open_app()))
    at.run()
    assert len(api.posts) == 1
    submit(at)
    assert len(api.posts) == 2
    assert title(at) == "Ảnh AI" and not at.error


def test_session_results_are_not_shared(api):
    first = submit(upload(open_app()))
    assert title(first) == "Ảnh AI"
    second = upload(open_app())
    assert title(second) is None
    assert second.button[0].disabled is False


def sidebar_text(at):
    return " ".join(
        element.value for element in at.sidebar if hasattr(element, "value")
    )


@pytest.mark.parametrize(
    "health,badge,detail",
    [
        (response(200, {}), "Hệ thống sẵn sàng", None),
        (response(503, {}), "Hệ thống chưa sẵn sàng", "mô hình chưa sẵn sàng"),
        (response(404, {}), "Hệ thống chưa sẵn sàng", "Chưa kết nối được API"),
        (httpx.ConnectError("x"), "Hệ thống chưa sẵn sàng", "Chưa kết nối được API"),
    ],
)
def test_session_sidebar_reports_system_status(api, health, badge, detail):
    api.health = health
    text = sidebar_text(open_app())
    assert badge in text
    assert detail is None or detail in text


@pytest.fixture
def real_api(api, monkeypatch):
    """Nối api_client vào FastAPI thật; chuẩn hóa thật, chỉ điểm là giả."""

    def scorer(image):
        normalize_image(image)
        return 0.58

    client = TestClient(create_app(scorer=scorer), raise_server_exceptions=False)

    def post(url, *, files, timeout):
        reply = client.post(url.removeprefix("http://localhost:8000"), files=files)
        return response(reply.status_code, reply.json())

    monkeypatch.setattr(httpx, "post", post)


def noise_jpeg(size):
    pixels = np.random.default_rng(1).integers(0, 256, (size[1], size[0], 3))
    stream = io.BytesIO()
    Image.fromarray(pixels.astype(np.uint8)).save(stream, "JPEG")
    return stream.getvalue()


def test_result_from_real_api_contract(real_api):
    at = submit(upload(open_app(), "a.jpg", noise_jpeg((640, 480)), "image/jpeg"))
    assert title(at) == "Dự đoán AI" and score_text(at) == "58%"
    assert "<p>Không có thông tin máy chụp</p>" in html(at)
    assert not at.error


@pytest.mark.parametrize(
    "name,data,message",
    [
        ("nho.jpg", noise_jpeg((200, 300)), "Cạnh ngắn tối thiểu 256 px"),
        ("gia.jpg", b"khong phai anh", "Không đọc được ảnh"),
    ],
)
def test_error_from_real_api_contract_shows_api_message(real_api, name, data, message):
    at = submit(upload(open_app(), name, data, "image/jpeg"))
    assert message in at.error[0].value and title(at) is None


def report(**changes):
    metrics = {
        "n": 900,
        "accuracy": 0.9,
        "precision": 0.91,
        "recall": 0.89,
        "decided_accuracy": 0.95,
        "uncertain_n": 90,
        "confusion_matrix": [[410, 40], [50, 400]],
    }
    version = {"version": "v1", "hash": "abc"}
    return {
        "dataset": version,
        "model": version,
        "profile": version,
        "thresholds": {"binary": 0.5, "low": 0.3, "high": 0.7},
        "test": metrics,
        "by_source": [{"name": "GLIDE", "n": 150, "accuracy": 0.9, "uncertain_n": 15}],
        **changes,
    }


def open_report(monkeypatch, tmp_path, content):
    path = tmp_path / "evaluation.json"
    if content is not None:
        path.write_text(
            content if isinstance(content, str) else json.dumps(content),
            encoding="utf-8",
        )
    monkeypatch.setenv("REALCHECK_EVAL_REPORT", str(path))
    at = AppTest.from_file(EVALUATION_PAGE, default_timeout=30).run()
    assert not at.exception
    return at


def metric_values(at):
    return {metric.label: metric.value for metric in at.metric}


def test_evaluation_report_shows_measured_values(monkeypatch, tmp_path):
    at = open_report(monkeypatch, tmp_path, report())
    values = metric_values(at)
    assert values["Accuracy"] == "90.0%"
    assert values["Precision"] == "91.0%"
    assert values["Recall"] == "89.0%"
    assert not at.error


def test_evaluation_uncertainty_rate_uses_all_images(monkeypatch, tmp_path):
    at = open_report(monkeypatch, tmp_path, report())
    assert metric_values(at)["Tỷ lệ Chưa chắc"] == "10.0%"
    assert "810 ảnh đã có kết luận" in captions(at)


def test_evaluation_uncertainty_all_images_has_no_decided_accuracy(
    monkeypatch, tmp_path
):
    data = report()
    data["test"].update(decided_accuracy=None, uncertain_n=900)
    at = open_report(monkeypatch, tmp_path, data)
    assert metric_values(at)["Tỷ lệ Chưa chắc"] == "100.0%"
    assert "Không có ảnh nào được kết luận" in captions(at)


def test_evaluation_report_missing_shows_not_measured(monkeypatch, tmp_path):
    at = open_report(monkeypatch, tmp_path, None)
    assert any("Chưa có số đo" in info.value for info in at.info)
    assert "Accuracy" not in metric_values(at) and not at.error


def test_evaluation_report_with_null_test_shows_not_measured(monkeypatch, tmp_path):
    at = open_report(monkeypatch, tmp_path, report(test=None, by_source=[]))
    assert any("Chưa đo trên tập test" in info.value for info in at.info)
    assert "Accuracy" not in metric_values(at) and not at.error


def broken(**test_changes):
    data = report()
    data["test"].update(test_changes)
    return data


def without_test():
    data = report()
    data.pop("test")
    return data


@pytest.mark.parametrize(
    "content",
    [
        "{hong",
        "[]",
        without_test(),
        broken(accuracy=90),
        broken(accuracy=None),
        broken(n=901),
        broken(uncertain_n=901),
        broken(confusion_matrix=[[1, 2]]),
        report(by_source=[{"name": "x"}]),
        report(thresholds={"binary": 0.5}),
    ],
)
def test_evaluation_report_malformed_shows_no_numbers(monkeypatch, tmp_path, content):
    at = open_report(monkeypatch, tmp_path, content)
    assert "sai định dạng" in at.error[0].value
    assert "Accuracy" not in metric_values(at)
