"""Cấu hình API, đọc từ biến môi trường tiền tố REALCHECK_.

Giá trị mặc định theo docs/decisions/realcheck-baseline.md (D06, D07, D11, D12);
ví dụ REALCHECK_MODEL_TIMEOUT_S=20 đổi timeout mà không sửa mã.
"""

from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="REALCHECK_", frozen=True)

    max_file_bytes: int = Field(default=5_242_880, gt=0)
    max_pixels: int = Field(default=24_000_000, gt=0)
    max_side: int = Field(default=10_000, gt=0)
    model_timeout_s: float = Field(default=10.0, gt=0)
    inference_slots: int = Field(default=1, gt=0)
    threshold_low: float = Field(default=0.3, ge=0, le=1)
    threshold_high: float = Field(default=0.7, ge=0, le=1)
    # None: dùng models/clip_probe.joblib theo models.score.DEFAULT_MODEL_PATH.
    model_path: Path | None = None

    @model_validator(mode="after")
    def check_thresholds(self) -> Self:
        if self.threshold_low >= self.threshold_high:
            raise ValueError("threshold_low phải nhỏ hơn threshold_high")
        return self
