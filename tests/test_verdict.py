import pytest

from app.schemas import Verdict
from app.settings import Settings
from app.verdict import MISSING_EXIF, build_reason, decide_verdict

S = Settings()


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, Verdict.LIKELY_REAL),
        (0.299999, Verdict.LIKELY_REAL),
        (0.3, Verdict.UNCERTAIN),  # biên thuộc Chưa chắc, theo D05 (proposed)
        (0.5, Verdict.UNCERTAIN),
        (0.7, Verdict.UNCERTAIN),  # biên thuộc Chưa chắc, theo D05 (proposed)
        (0.700001, Verdict.LIKELY_AI),
        (1.0, Verdict.LIKELY_AI),
    ],
)
def test_decide_verdict_bien_theo_D05_proposed(score, expected):
    assert decide_verdict(score, S) == expected


def test_enum_verdict_theo_D05_proposed():
    assert {v.value for v in Verdict} == {"likely_real", "uncertain", "likely_ai"}


def test_decide_verdict_theo_nguong_tuy_chinh():
    s = Settings(threshold_low=0.1, threshold_high=0.2)
    assert decide_verdict(0.15, s) == Verdict.UNCERTAIN
    assert decide_verdict(0.25, s) == Verdict.LIKELY_AI


@pytest.mark.parametrize("verdict", list(Verdict))
def test_reason_exif_khong_doi_verdict_va_khac_nhau(verdict):
    with_exif = build_reason(verdict, True)
    without = build_reason(verdict, False)
    assert with_exif != without
    assert "có thông tin máy chụp" in with_exif
    assert "không có thông tin máy chụp" in without


def test_reason_moi_verdict_khac_nhau():
    assert len({build_reason(v, True) for v in Verdict}) == 3


def test_hang_missing_exif():
    assert MISSING_EXIF
