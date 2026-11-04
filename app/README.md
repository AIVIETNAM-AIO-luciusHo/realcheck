# app/ – FastAPI

Phụ trách: Quang

## Làm gì
API nhận 1 ảnh, kiểm tra hợp lệ, gọi `score(image)` từ `models/`, đọc EXIF và trả `verdict`, `score`, `exif`, `reason`.

| File | Chức năng |
|---|---|
| `main.py` | `create_app(scorer, settings)`: tạo app, gắn middleware, lỗi, route |
| `routes.py` | Khai báo endpoint |
| `schemas.py` | Hợp đồng JSON: `verdict`, response, mã lỗi |
| `verdict.py` | Ngưỡng và câu chữ `reason`; không lặp logic này ở nơi khác |
| `errors.py` | Bảng mã lỗi, envelope lỗi dùng chung |
| `settings.py` | Cấu hình đọc từ biến môi trường |
| `logging.py` | `X-Request-ID` và log có cấu trúc |

Endpoint: `GET /health`, `GET /docs`, `GET /openapi.json`. Đang làm: `POST /v1/analyze`. Giai đoạn nâng cao: `GET /metrics`.

## Cách chạy
Từ thư mục gốc repo:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Chưa có model thì `/health` trả 503; đây là hành vi đúng, không có chế độ model giả khi chạy server. Test tiêm scorer giả qua `create_app(scorer=...)`.

## Cấu hình
Biến môi trường, giá trị mặc định xem `settings.py`. Lý do chọn: [`docs/decisions/realcheck-baseline.md`](../docs/decisions/realcheck-baseline.md).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `REALCHECK_MAX_FILE_BYTES` | 5242880 | Dung lượng file tối đa |
| `REALCHECK_MAX_PIXELS` | 24000000 | Số pixel tối đa |
| `REALCHECK_MAX_SIDE` | 10000 | Cạnh tối đa |
| `REALCHECK_MODEL_TIMEOUT_S` | 10 | Timeout suy luận (giây) |
| `REALCHECK_INFERENCE_SLOTS` | 1 | Số ảnh xử lý đồng thời |
| `REALCHECK_THRESHOLD_LOW` | 0.3 | Dưới ngưỡng này là `likely_real` |
| `REALCHECK_THRESHOLD_HIGH` | 0.7 | Trên ngưỡng này là `likely_ai` |

## Input / Output
- Input: 1 ảnh (tối đa 5MB, do Nginx giới hạn).
- Output: JSON `{verdict, score, exif, reason}`; ngưỡng 0.3 / 0.7.

## Lưu ý và giả định
- Độ bao phủ test của `app/` từ 70% trở lên.
- Đổi schema response phải sửa tài liệu trong cùng PR.
