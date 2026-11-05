"""Khởi tạo FastAPI.

Cách chạy (từ thư mục gốc repo):
    uvicorn app.main:app --reload
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.errors import register_error_handlers
from app.inference import InferenceService, Scorer
from app.logging import RequestContextMiddleware, configure_logging
from app.routes import router
from app.settings import Settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Nạp model trước khi nhận request; nạp lỗi thì /health trả 503."""
    inference = app.state.inference
    if app.state.scorer is None and app.state.loader is not None:
        app.state.scorer = await inference.load(app.state.loader)
    yield
    inference.close()


def create_app(
    scorer: Scorer | None = None,
    settings: Settings | None = None,
    loader: Callable[[], Scorer] | None = None,
) -> FastAPI:
    """Tạo app; scorer chỉ được tiêm từ code/test, không có cờ bật model giả."""
    configure_logging()
    app = FastAPI(title="RealCheck API", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings()
    app.state.scorer = scorer
    app.state.loader = loader
    app.state.inference = InferenceService(app.state.settings)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)
    app.include_router(router)
    return app


app = create_app()
