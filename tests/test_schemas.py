import pytest
from pydantic import ValidationError

from app.schemas import AnalyzeResponse, ErrorDetail, HealthResponse, Verdict

OK = {"verdict": "uncertain", "score": 0.5, "exif": "x", "reason": "y"}


def test_analyze_response_hop_le():
    r = AnalyzeResponse(**OK)
    assert r.verdict is Verdict.UNCERTAIN


@pytest.mark.parametrize("score", [0, 1, 0.0, 1.0])
def test_score_bien_hop_le(score):
    assert AnalyzeResponse(**{**OK, "score": score}).score == score


@pytest.mark.parametrize("score", [-0.01, 1.01, float("nan"), float("inf")])
def test_score_ngoai_0_1_hoac_nan_bi_tu_choi(score):
    with pytest.raises(ValidationError):
        AnalyzeResponse(**{**OK, "score": score})


@pytest.mark.parametrize("field", ["exif", "reason"])
def test_exif_reason_khong_duoc_rong(field):
    with pytest.raises(ValidationError):
        AnalyzeResponse(**{**OK, field: ""})


def test_verdict_la_bi_tu_choi():
    with pytest.raises(ValidationError):
        AnalyzeResponse(**{**OK, "verdict": "maybe"})


def test_cam_truong_thua():
    with pytest.raises(ValidationError):
        AnalyzeResponse(**OK, extra=1)


def test_health_status_chi_nhan_ok_hoac_not_ready():
    with pytest.raises(ValidationError):
        HealthResponse(status="down", model_ready=False)


def test_error_detail_message_khong_rong_va_code_hop_le():
    with pytest.raises(ValidationError):
        ErrorDetail(code="NOPE", message="m", request_id="r")
    with pytest.raises(ValidationError):
        ErrorDetail(code="NOT_FOUND", message="", request_id="r")
