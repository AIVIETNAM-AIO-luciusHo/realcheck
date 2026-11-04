"""Khởi tạo FastAPI.

Cách chạy (từ thư mục gốc repo):
    uvicorn app.main:app --reload
"""

from collections.abc import Callable

from fastapi import FastAPI
from PIL.Image import Image

from app.errors import register_error_handlers
from app.logging import RequestContextMiddleware, configure_logging
from app.routes import router
from app.settings import Settings

Scorer = Callable[[Image], float]


def create_app(
    scorer: Scorer | None = None, settings: Settings | None = None
) -> FastAPI:
    """Tạo app; scorer chỉ được tiêm từ code/test, không có cờ bật model giả."""
    configure_logging()
    app = FastAPI(title="RealCheck API", version="0.1.0")
    app.state.settings = settings or Settings()
    app.state.scorer = scorer
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
