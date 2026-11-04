"""Nơi duy nhất quyết định verdict và câu chữ reason, không để lặp ở API hay UI."""

from app.schemas import Verdict
from app.settings import Settings

MISSING_EXIF = "Không có thông tin máy chụp"

_REASON_BY_VERDICT = {
    Verdict.LIKELY_REAL: "Điểm mô hình nằm trong vùng Ảnh thật.",
    Verdict.UNCERTAIN: "Điểm mô hình nằm trong vùng Chưa chắc, chưa đủ căn cứ kết luận.",
    Verdict.LIKELY_AI: "Điểm mô hình nằm trong vùng Ảnh AI.",
}
_REASON_HAS_EXIF = "Ảnh có thông tin máy chụp; đây chỉ là bằng chứng phụ."
_REASON_NO_EXIF = "Ảnh không có thông tin máy chụp; đây chỉ là bằng chứng phụ."


def decide_verdict(score: float, settings: Settings) -> Verdict:
    """Đổi điểm thô thành verdict; không làm tròn, hai biên thuộc vùng Chưa chắc."""
    if score < settings.threshold_low:
        return Verdict.LIKELY_REAL
    if score > settings.threshold_high:
        return Verdict.LIKELY_AI
    return Verdict.UNCERTAIN


def build_reason(verdict: Verdict, has_exif: bool) -> str:
    """Tạo lý do tiếng Việt; EXIF chỉ thêm thông tin, không đổi verdict."""
    exif_sentence = _REASON_HAS_EXIF if has_exif else _REASON_NO_EXIF
    return f"{_REASON_BY_VERDICT[verdict]} {exif_sentence}"
