# Quyết định kỹ thuật RealCheck

Ghi các mục D01–D14 của `specs/000-realcheck-system-baseline/spec.md`. Phần API do Quang phụ trách; lựa chọn D08 của Kiệt được liên kết bên dưới. Các mục khác do người phụ trách bổ sung.

Trạng thái: `proposed` (đề xuất, chờ review), `approved` (nhóm đã duyệt) hoặc `approved tạm` (đã duyệt để dùng, xem lại sau benchmark). Mục `proposed` có thể đổi khi review PR.

| Mục | Trạng thái | Người đề xuất | Reviewer | Ngày |
|---|---|---|---|---|
| D05 Enum và lỗi | approved | Quang | Lực | 2026-11-04 |
| D06 Dung lượng file | approved | Quang | Lực | 2026-11-04 |
| D07 Số pixel | approved | Quang | Lực | 2026-11-04 |
| D11 Timeout | approved tạm, xem lại sau benchmark | Quang | Lực | 2026-11-04 |
| D12 Cơ chế suy luận | approved tạm, xem lại sau benchmark | Quang | Lực | 2026-11-04 |
| D08 Ngưỡng score/hiển thị | proposed; Kiệt chọn 0.3/0.5/0.7 để triển khai, chờ review release | Kiệt | Lực/Loan | 2026-11-05 |
| Hợp đồng `score` | proposed | Quang | Chờ Kiệt, Lực | 2026-11-04 |

## D05. Enum `verdict` và lỗi

**Lựa chọn:** `likely_real` / `uncertain` / `likely_ai` (phương án A).

**Lý do:** ba giá trị cùng kiểu; `likely_real` không khẳng định chắc chắn ảnh là thật, đúng yêu cầu không tuyên bố chính xác 100%.

Lỗi trả envelope riêng, kể cả lỗi validation của framework:

```json
{
  "error": {
    "code": "IMAGE_TOO_SMALL",
    "message": "Ảnh quá nhỏ. Cạnh ngắn tối thiểu 256 px.",
    "request_id": "6e8c9d7d-e5dc-43a0-a59c-575e586684d8"
  }
}
```

| HTTP | `code` | Khi nào |
|---|---|---|
| 400 | `EMPTY_FILE` | File 0 byte |
| 400 | `INVALID_IMAGE` | Pillow không nhận ra ảnh (text giả `.jpg`) hoặc ảnh bị cắt cụt |
| 404 | `NOT_FOUND` | Đường dẫn không tồn tại |
| 405 | `METHOD_NOT_ALLOWED` | Sai phương thức |
| 413 | `FILE_TOO_LARGE` | Vượt dung lượng |
| 413 | `TOO_MANY_PIXELS` | Vượt số pixel hoặc cạnh tối đa |
| 415 | `UNSUPPORTED_FORMAT` | Đọc được nhưng không phải JPEG/PNG, hoặc nhiều khung hình |
| 422 | `MISSING_FILE` | Thiếu trường `file` |
| 422 | `MULTIPLE_FILES` | Nhiều hơn một file |
| 422 | `IMAGE_TOO_SMALL` | Cạnh ngắn < 256 px |
| 422 | `INVALID_REQUEST` | Yêu cầu sai khác |
| 500 | `MODEL_ERROR` | `score` lỗi, hoặc trả NaN, Infinity, giá trị ngoài `[0, 1]` |
| 500 | `INTERNAL_ERROR` | Lỗi khác; không lộ stacktrace |
| 503 | `MODEL_NOT_READY` | Model chưa sẵn sàng |
| 503 | `SERVICE_BUSY` | Hết slot suy luận |
| 504 | `MODEL_TIMEOUT` | Quá thời gian xử lý |

**Ảnh hưởng:** Streamlit dựa vào `verdict` và `error.code`; Nginx phải trả lỗi 413 và 429 cùng envelope.

**Ghi chú đã duyệt:** ranh giới 400 và 415 (file không phải ảnh là 400, ảnh sai định dạng là 415); ba mã `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INVALID_REQUEST` được thêm ngoài gợi ý của D05 để lỗi framework cùng định dạng.

## D06. Dung lượng file

**Lựa chọn:** tối đa 5.242.880 byte (`REALCHECK_MAX_FILE_BYTES`).

**Lý do:** trùng cách Nginx hiểu `5m`, tránh lệch giữa gateway và API.

**Chưa chốt:** phần body dư cho multipart (64 hoặc 128 KiB) thuộc cấu hình Nginx.

## D07. Số pixel

**Lựa chọn:** tối đa 24 MP và cạnh tối đa 10.000 px (`REALCHECK_MAX_PIXELS`, `REALCHECK_MAX_SIDE`).

**Lý do:** cho qua JPEG 4000×3000 (12 MP) và phần lớn ảnh điện thoại.

**Lưu ý:** spec yêu cầu chọn theo RAM đo; hiện chưa đo. Xem lại sau benchmark.

## D11. Timeout

**Lựa chọn:** timeout model 10 giây (`REALCHECK_MODEL_TIMEOUT_S`).

**Lưu ý:** chưa đo trên model thật. Timeout của Nginx và UI phải dài hơn timeout này. Thời gian khởi động và warmup tính riêng.

## D12. Cơ chế suy luận

**Lựa chọn:** thread, 1 worker, 1 slot (`REALCHECK_INFERENCE_SLOTS`), không xếp hàng; hết slot trả 503.

**Lý do:** đơn giản nhất đáp ứng được giới hạn tài nguyên.

**Hệ quả:** thread không hủy được CLIP đang chạy. Quá giờ trả 504 nhưng slot chỉ nhả khi việc thật sự kết thúc, nên trong lúc đó request mới nhận 503.

**Lưu ý:** spec yêu cầu chọn sau benchmark CPU/RAM; xem lại khi có model thật.

## Hợp đồng `score`

Ngưỡng D08 và lựa chọn manifest/holdout mới được ghi tại [ml-selection.md](ml-selection.md). Bảng API/UI hiện có khớp các mốc Kiệt chọn; việc đó không thay thế xác nhận QA hoặc kết quả model-test.

**Lựa chọn:** theo spec 001: `models/score.py`, `score(image) -> float`, `image` là PIL Image gốc đã giải mã, chưa chuẩn hóa. API giải mã một lần, đọc EXIF, gọi `score` và bắt `ImageTooSmall`.

**Lý do:** spec 000 ghi `models/scoring.py` và nhận bytes, nhưng spec 001 mới hơn và có Clarification riêng cho điểm này. Nhận PIL Image cho phép API giải mã đúng một lần.
