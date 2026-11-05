"""Đọc file upload, giải mã một lần, đọc EXIF; không resize hay nén ảnh (hợp đồng C4)."""

from io import BytesIO

from fastapi import Request, UploadFile
from PIL import Image
from starlette.datastructures import UploadFile as FormFile

from app.errors import ApiError
from app.inference import Scorer
from app.schemas import ErrorCode
from app.settings import Settings
from app.verdict import MISSING_EXIF
from models.normalize import ImageTooSmall

ALLOWED_FORMATS = {"JPEG", "PNG"}
EXIF_MAKE = 0x010F
EXIF_MODEL = 0x0110
MAX_EXIF_TEXT = 64


async def read_upload(request: Request, file: UploadFile, settings: Settings) -> bytes:
    """Đọc tối đa limit + 1 byte; file vượt giới hạn không được giữ trong bộ nhớ."""
    form = await request.form()
    if sum(isinstance(value, FormFile) for _, value in form.multi_items()) > 1:
        raise ApiError(ErrorCode.MULTIPLE_FILES)
    data = await file.read(settings.max_file_bytes + 1)
    if not data:
        raise ApiError(ErrorCode.EMPTY_FILE)
    if len(data) > settings.max_file_bytes:
        raise ApiError(ErrorCode.FILE_TOO_LARGE)
    return data


def decode_image(data: bytes, settings: Settings) -> Image.Image:
    """Kiểm header trước load() để ảnh bomb không được cấp phát raster."""
    try:
        image = Image.open(BytesIO(data))
    except Image.DecompressionBombError as exc:
        raise ApiError(ErrorCode.TOO_MANY_PIXELS) from exc
    except Exception as exc:
        raise ApiError(ErrorCode.INVALID_IMAGE) from exc

    width, height = image.size
    if image.format not in ALLOWED_FORMATS:
        raise ApiError(ErrorCode.UNSUPPORTED_FORMAT)
    if width * height > settings.max_pixels or max(width, height) > settings.max_side:
        raise ApiError(ErrorCode.TOO_MANY_PIXELS)
    if getattr(image, "n_frames", 1) > 1:
        raise ApiError(ErrorCode.UNSUPPORTED_FORMAT)

    try:
        image.load()
    except Exception as exc:
        raise ApiError(ErrorCode.INVALID_IMAGE) from exc
    return image


def _clean_exif_text(value: object) -> str:
    """Bỏ ký tự điều khiển, gộp khoảng trắng, giới hạn độ dài."""
    if not isinstance(value, str):
        return ""
    printable = "".join(char if char.isprintable() else " " for char in value)
    return " ".join(printable.split())[:MAX_EXIF_TEXT].rstrip()


def read_exif(image: Image.Image) -> str:
    """Chỉ trả hãng và model máy, không trả GPS hay serial."""
    try:
        exif = image.getexif()
        make = _clean_exif_text(exif.get(EXIF_MAKE))
        model = _clean_exif_text(exif.get(EXIF_MODEL))
    except Exception:  # noqa: BLE001 - EXIF chỉ là bằng chứng phụ, không làm hỏng request
        return MISSING_EXIF
    if make and model.casefold().startswith(make.split()[0].casefold()):
        return model
    return " ".join(filter(None, (make, model))) or MISSING_EXIF


def analyze_image(data: bytes, settings: Settings, scorer: Scorer) -> tuple[float, str]:
    """Chạy trên worker thread; EXIF phải đọc trước khi chuẩn hóa xóa nó."""
    image = decode_image(data, settings)
    exif = read_exif(image)
    try:
        score = float(scorer(image))
    except ImageTooSmall as exc:
        raise ApiError(ErrorCode.IMAGE_TOO_SMALL) from exc
    # NaN làm mọi phép so đều sai, lọt tới decide_verdict sẽ thành uncertain.
    if not 0 <= score <= 1:
        raise ValueError(f"Score ngoài [0, 1]: {score}")
    return score, exif
