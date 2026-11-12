"""Gọi POST /v1/analyze qua Nginx. Mỗi lần gọi đúng một POST, không tự thử lại."""

import math
import os
from dataclasses import dataclass

import httpx

# Tạm: giá trị verdict (D05) và thời gian chờ (D11) chưa chốt
API_URL = os.environ.get("REALCHECK_API_URL", "http://localhost:8000")
TIMEOUT_SECONDS = float(os.environ.get("REALCHECK_API_TIMEOUT", "60"))
HEALTH_TIMEOUT_SECONDS = 1.0
VERDICTS = {"likely_real", "real", "uncertain", "likely_ai"}

ERROR_MESSAGES = {
    400: "Ảnh không đọc được. Vui lòng thử ảnh khác.",
    413: "Ảnh vượt quá giới hạn dung lượng. Vui lòng giảm dung lượng rồi thử lại.",
    415: "Định dạng không được hỗ trợ. Vui lòng dùng ảnh JPEG hoặc PNG.",
    422: "Ảnh không hợp lệ. Vui lòng thử ảnh khác.",
    429: "Đang có quá nhiều yêu cầu. Vui lòng đợi một lát rồi bấm kiểm tra lại.",
    502: "Hệ thống phân tích chưa sẵn sàng. Vui lòng thử lại sau.",
    503: "Hệ thống chưa sẵn sàng hoặc đang bận. Vui lòng thử lại sau.",
    504: "Hệ thống xử lý quá lâu. Vui lòng thử lại sau.",
}
# Các lỗi về ảnh: API nêu lý do cụ thể (vd. ảnh quá nhỏ, quá nhiều pixel) thì hiện lý do đó
API_MESSAGE_STATUSES = {400, 413, 415, 422}


@dataclass(frozen=True)
class Analysis:
    verdict: str
    score: float
    exif: str
    reason: str
    elapsed_seconds: float
    request_id: str | None = None


@dataclass(frozen=True)
class ApiError:
    message: str
    request_id: str | None = None


def _parse_analysis(response: httpx.Response) -> Analysis | None:
    """Trả về None nếu phản hồi 200 sai hợp đồng, để không hiện kết quả giả."""
    try:
        body = response.json()
        verdict, score = body["verdict"], body["score"]
        exif, reason = body["exif"], body["reason"]
    except (ValueError, KeyError, TypeError):
        return None
    valid_score = (
        isinstance(score, int | float)
        and not isinstance(score, bool)
        and math.isfinite(score)
        and 0 <= score <= 1
    )
    valid_text = isinstance(exif, str) and isinstance(reason, str) and reason.strip()
    if verdict not in VERDICTS or not valid_score or not valid_text:
        return None
    return Analysis(
        verdict,
        float(score),
        exif,
        reason,
        response.elapsed.total_seconds(),
        response.headers.get("X-Request-ID"),
    )


def _api_message(response: httpx.Response) -> str | None:
    """Lấy lý do từ lỗi của API; định dạng lỗi (D05) chưa chốt nên đọc các dạng phổ biến."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    candidates = [
        body.get("detail"),
        body.get("message"),
        error.get("message") if isinstance(error, dict) else error,
    ]
    return next((c for c in candidates if isinstance(c, str) and c.strip()), None)


def _error_message(response: httpx.Response) -> str:
    status = response.status_code
    if status in API_MESSAGE_STATUSES and (message := _api_message(response)):
        return message
    default = f"Hệ thống trả lỗi không mong đợi (mã {status}). Vui lòng thử lại sau."
    return ERROR_MESSAGES.get(status, default)


def analyze(
    filename: str, data: bytes, content_type: str | None
) -> Analysis | ApiError:
    try:
        response = httpx.post(
            f"{API_URL}/v1/analyze",
            files={"file": (filename, data, content_type)},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException:
        return ApiError("Hệ thống phản hồi quá lâu. Vui lòng thử lại sau.")
    except httpx.HTTPError:
        return ApiError("Không kết nối được tới hệ thống. Vui lòng thử lại sau.")

    request_id = response.headers.get("X-Request-ID")
    if response.status_code != 200:
        return ApiError(_error_message(response), request_id)
    analysis = _parse_analysis(response)
    if analysis is None:
        return ApiError(
            "Hệ thống trả kết quả không hợp lệ. Vui lòng thử lại sau.", request_id
        )
    return analysis


def api_status() -> str:
    """GET /health: "ready", "not_ready" (API chạy, model chưa sẵn sàng) hoặc "unreachable"."""
    try:
        response = httpx.get(f"{API_URL}/health", timeout=HEALTH_TIMEOUT_SECONDS)
    except httpx.HTTPError:
        return "unreachable"
    if response.is_success:
        return "ready"
    # Chỉ 503 mới có nghĩa API chạy mà model chưa sẵn sàng; mã khác là không phải API này
    return "not_ready" if response.status_code == 503 else "unreachable"
