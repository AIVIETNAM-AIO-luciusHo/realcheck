"""Mọi lỗi của API trả cùng envelope {"error": {code, message, request_id}}."""

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas import ErrorCode, ErrorDetail, ErrorResponse
from models.normalize import MIN_SIDE

REQUEST_ID_HEADER = "X-Request-ID"

ERROR_TABLE: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.MISSING_FILE: (422, "Thiếu file ảnh trong trường file."),
    ErrorCode.MULTIPLE_FILES: (422, "Chỉ gửi một file ảnh cho mỗi yêu cầu."),
    ErrorCode.IMAGE_TOO_SMALL: (
        422,
        f"Ảnh quá nhỏ. Cạnh ngắn tối thiểu {MIN_SIDE} px.",
    ),
    ErrorCode.INVALID_REQUEST: (422, "Yêu cầu không hợp lệ."),
    ErrorCode.EMPTY_FILE: (400, "File ảnh rỗng."),
    ErrorCode.INVALID_IMAGE: (400, "Không đọc được ảnh hoặc ảnh bị hỏng."),
    ErrorCode.NOT_FOUND: (404, "Không tìm thấy đường dẫn."),
    ErrorCode.METHOD_NOT_ALLOWED: (405, "Phương thức không được hỗ trợ."),
    ErrorCode.FILE_TOO_LARGE: (413, "File ảnh vượt quá dung lượng cho phép."),
    ErrorCode.TOO_MANY_PIXELS: (413, "Ảnh vượt quá số pixel cho phép."),
    ErrorCode.UNSUPPORTED_FORMAT: (415, "Chỉ hỗ trợ ảnh JPEG hoặc PNG một khung hình."),
    ErrorCode.MODEL_ERROR: (500, "Mô hình gặp lỗi khi phân tích ảnh."),
    ErrorCode.INTERNAL_ERROR: (500, "Máy chủ gặp lỗi. Vui lòng thử lại sau."),
    ErrorCode.MODEL_NOT_READY: (503, "Mô hình chưa sẵn sàng. Vui lòng thử lại sau."),
    ErrorCode.SERVICE_BUSY: (503, "Hệ thống đang bận. Vui lòng thử lại sau."),
    ErrorCode.MODEL_TIMEOUT: (
        504,
        "Phân tích quá thời gian cho phép. Vui lòng thử lại sau.",
    ),
}

_CODE_BY_HTTP_STATUS = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
}


class ApiError(Exception):
    """Lỗi dự kiến; handler đổi thành response theo ERROR_TABLE."""

    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def error_docs(*codes: ErrorCode) -> dict[int | str, dict[str, Any]]:
    """Khai báo lỗi cho OpenAPI từ ERROR_TABLE, gom theo HTTP status."""
    grouped: dict[int, list[str]] = {}
    for code in codes:
        grouped.setdefault(ERROR_TABLE[code][0], []).append(code.value)
    return {
        status: {"model": ErrorResponse, "description": ", ".join(names)}
        for status, names in grouped.items()
    }


def error_response(
    request: Request,
    code: ErrorCode,
    message: str | None = None,
    status: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Dựng response lỗi; tự gắn request ID vì lỗi 500 đi vòng qua middleware."""
    default_status, default_message = ERROR_TABLE[code]
    request_id = getattr(request.state, "request_id", None) or str(uuid4())
    body = ErrorResponse(
        error=ErrorDetail(
            code=code, message=message or default_message, request_id=request_id
        )
    )
    return JSONResponse(
        status_code=status or default_status,
        content=body.model_dump(mode="json"),
        headers={**(headers or {}), REQUEST_ID_HEADER: request_id},
    )


async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
    return error_response(request, exc.code, exc.message)


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Không trả chi tiết của Pydantic để giữ một định dạng lỗi duy nhất."""
    missing_file = any("file" in error["loc"] for error in exc.errors())
    code = ErrorCode.MISSING_FILE if missing_file else ErrorCode.INVALID_REQUEST
    return error_response(request, code)


async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        return error_response(request, ErrorCode.INTERNAL_ERROR, status=exc.status_code)
    code = _CODE_BY_HTTP_STATUS.get(exc.status_code)
    if code is None:
        # D05 (issue #43): INVALID_REQUEST luôn 422, kể cả 400 của framework khi multipart hỏng.
        return error_response(request, ErrorCode.INVALID_REQUEST)
    return error_response(
        request,
        code,
        status=exc.status_code,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Không lộ stacktrace ra response; Starlette vẫn ghi lỗi vào log server."""
    return error_response(request, ErrorCode.INTERNAL_ERROR)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
