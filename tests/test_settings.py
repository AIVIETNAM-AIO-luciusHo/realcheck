import pytest
from pydantic import ValidationError

from app.settings import Settings


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in list(__import__("os").environ):
        if k.startswith("REALCHECK_"):
            monkeypatch.delenv(k)


def test_gia_tri_mac_dinh():
    s = Settings()
    assert s.max_file_bytes == 5_242_880
    assert s.max_pixels == 24_000_000
    assert s.max_side == 10_000
    assert s.model_timeout_s == 10.0
    assert s.inference_slots == 1
    assert (s.threshold_low, s.threshold_high) == (0.3, 0.7)


def test_doc_env_va_ep_kieu(monkeypatch):
    monkeypatch.setenv("REALCHECK_MODEL_TIMEOUT_S", "20")
    monkeypatch.setenv("REALCHECK_MAX_SIDE", "512")
    s = Settings()
    assert s.model_timeout_s == 20.0
    assert s.max_side == 512


def test_env_sai_kieu_bi_tu_choi(monkeypatch):
    monkeypatch.setenv("REALCHECK_MAX_SIDE", "abc")
    with pytest.raises(ValidationError):
        Settings()


@pytest.mark.parametrize("field", ["max_file_bytes", "max_pixels", "model_timeout_s"])
def test_gia_tri_khong_duong_bi_tu_choi(field):
    with pytest.raises(ValidationError):
        Settings(**{field: 0})


@pytest.mark.parametrize("low,high", [(0.7, 0.3), (0.5, 0.5), (-0.1, 0.5), (0.2, 1.1)])
def test_nguong_khong_hop_le(low, high):
    with pytest.raises(ValidationError):
        Settings(threshold_low=low, threshold_high=high)


def test_settings_bat_bien():
    with pytest.raises(ValidationError):
        Settings().max_side = 1
