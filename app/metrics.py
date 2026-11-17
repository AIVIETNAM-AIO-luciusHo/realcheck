"""Metric Prometheus cho GET /metrics (#162). Registry riêng cho mỗi app, nhãn là tập đóng.

Không có nhãn nào lấy từ dữ liệu người dùng: route là khuôn đường dẫn đã khai báo (hoặc "other"),
status_class là 2xx..5xx, code là ErrorCode.
"""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from app.schemas import ErrorCode

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"
OTHER = "other"


class Metrics:
    def __init__(self, app) -> None:
        self.registry = CollectorRegistry()
        self.requests = Counter(
            "realcheck_requests_total",
            "Số request theo route và nhóm status",
            ["route", "status_class"],
            registry=self.registry,
        )
        self.duration = Histogram(
            "realcheck_request_duration_seconds",
            "Thời gian xử lý request theo route",
            ["route"],
            registry=self.registry,
        )
        self.errors = Counter(
            "realcheck_api_errors_total",
            "Số lỗi API theo mã ErrorCode",
            ["code"],
            registry=self.registry,
        )
        for code in ErrorCode:  # tạo sẵn để series không đổi theo lưu lượng
            self.errors.labels(code=code.value)
        slots = Gauge(
            "realcheck_inference_slots_in_use",
            "Số slot suy luận đang bận",
            registry=self.registry,
        )
        slots.set_function(lambda: app.state.inference.busy)
        ready = Gauge(
            "realcheck_model_ready",
            "1 nếu model đã nạp xong",
            registry=self.registry,
        )
        ready.set_function(lambda: 1 if app.state.scorer is not None else 0)

    def observe_request(self, route: str, status: int, seconds: float) -> None:
        self.requests.labels(route=route, status_class=f"{status // 100}xx").inc()
        self.duration.labels(route=route).observe(seconds)

    def render(self) -> bytes:
        return generate_latest(self.registry)
