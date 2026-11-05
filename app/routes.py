"""Khai báo endpoint; logic nằm ở các module khác, route không xử lý ảnh."""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, File, Request, Response, UploadFile

from app.errors import error_docs
from app.schemas import AnalyzeResponse, ErrorCode, HealthResponse
from app.uploads import analyze_image, read_upload
from app.verdict import MISSING_EXIF, build_reason, decide_verdict

router = APIRouter()

_ROUTING_ERRORS = {ErrorCode.NOT_FOUND, ErrorCode.METHOD_NOT_ALLOWED}


@router.post(
    "/v1/analyze",
    response_model=AnalyzeResponse,
    responses=error_docs(*(code for code in ErrorCode if code not in _ROUTING_ERRORS)),
)
async def analyze(
    request: Request, file: Annotated[UploadFile, File()]
) -> AnalyzeResponse:
    """Phân tích một ảnh JPEG hoặc PNG; slot chỉ chiếm sau khi đã đọc xong file."""
    settings = request.app.state.settings
    data = await read_upload(request, file, settings)
    score, exif = await request.app.state.inference.run(
        request.app.state.scorer, partial(analyze_image, data, settings)
    )
    verdict = decide_verdict(score, settings)
    return AnalyzeResponse(
        verdict=verdict,
        score=score,
        exif=exif,
        reason=build_reason(verdict, has_exif=exif != MISSING_EXIF),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Model chưa sẵn sàng"}},
)
async def health(request: Request, response: Response) -> HealthResponse:
    """Chỉ đọc trạng thái, không chạy model."""
    ready = request.app.state.scorer is not None
    if not ready:
        response.status_code = 503
    return HealthResponse(status="ok" if ready else "not_ready", model_ready=ready)
