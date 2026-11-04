"""Hợp đồng JSON của API; đổi file này phải cập nhật tài liệu và test cùng PR."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Verdict(StrEnum):
    LIKELY_REAL = "likely_real"
    UNCERTAIN = "uncertain"
    LIKELY_AI = "likely_ai"


class ErrorCode(StrEnum):
    MISSING_FILE = "MISSING_FILE"
    MULTIPLE_FILES = "MULTIPLE_FILES"
    IMAGE_TOO_SMALL = "IMAGE_TOO_SMALL"
    INVALID_REQUEST = "INVALID_REQUEST"
    EMPTY_FILE = "EMPTY_FILE"
    INVALID_IMAGE = "INVALID_IMAGE"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    TOO_MANY_PIXELS = "TOO_MANY_PIXELS"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    MODEL_ERROR = "MODEL_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    MODEL_NOT_READY = "MODEL_NOT_READY"
    SERVICE_BUSY = "SERVICE_BUSY"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    exif: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(min_length=1)
    request_id: str


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "not_ready"]
    model_ready: bool
