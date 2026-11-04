"""Khai báo endpoint; logic nằm ở các module khác, route không xử lý ảnh."""

from fastapi import APIRouter, Request, Response

from app.schemas import HealthResponse

router = APIRouter()


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
