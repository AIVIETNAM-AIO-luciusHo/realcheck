"""Chạy suy luận trên thread riêng, giới hạn slot và thời gian (D11, D12)."""

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import TypeVar

from PIL.Image import Image

from app.errors import ApiError
from app.logging import logger
from app.schemas import ErrorCode
from app.settings import Settings

Scorer = Callable[[Image], float]
T = TypeVar("T")


def _log_failure(event: str, exc: Exception) -> None:
    logger.error(
        json.dumps(
            {"event": event, "error": type(exc).__name__, "detail": str(exc)},
            ensure_ascii=False,
        )
    )


class InferenceService:
    """Mỗi việc giữ một slot tới khi thread thật sự kết thúc, kể cả sau timeout."""

    def __init__(self, settings: Settings) -> None:
        self._timeout_s = settings.model_timeout_s
        self._slots = BoundedSemaphore(settings.inference_slots)
        self._executor = ThreadPoolExecutor(
            max_workers=settings.inference_slots, thread_name_prefix="inference"
        )

    async def run(self, scorer: Scorer | None, job: Callable[[Scorer], T]) -> T:
        """Chạy job(scorer) trên worker thread; hết slot thì từ chối, không xếp hàng."""
        if scorer is None:
            raise ApiError(ErrorCode.MODEL_NOT_READY)
        if not self._slots.acquire(blocking=False):
            raise ApiError(ErrorCode.SERVICE_BUSY)
        try:
            future = self._executor.submit(job, scorer)
        except RuntimeError:
            self._slots.release()
            raise ApiError(ErrorCode.MODEL_NOT_READY) from None
        # Thread không hủy được CLIP nên slot nhả theo future, không nhả ở finally.
        future.add_done_callback(lambda _: self._slots.release())

        result = asyncio.wrap_future(future)
        done, _ = await asyncio.wait({result}, timeout=self._timeout_s)
        if not done:
            result.cancel()
            raise ApiError(ErrorCode.MODEL_TIMEOUT)
        try:
            return result.result()
        except ApiError:
            raise
        except Exception as exc:
            _log_failure("inference_failed", exc)
            raise ApiError(ErrorCode.MODEL_ERROR) from exc

    async def load(self, loader: Callable[[], Scorer]) -> Scorer | None:
        """Nạp trên worker thread; không có timeout vì D11 tính startup riêng."""
        try:
            return await asyncio.wrap_future(self._executor.submit(loader))
        except Exception as exc:  # noqa: BLE001 - mọi lỗi nạp đều là chưa ready (AC-20)
            _log_failure("model_load_failed", exc)
            return None

    def close(self) -> None:
        """Không chờ việc đang chạy; việc chưa chạy bị hủy và trả lại slot."""
        self._executor.shutdown(wait=False, cancel_futures=True)
