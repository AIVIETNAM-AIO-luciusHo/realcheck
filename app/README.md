# app/ – FastAPI

Phụ trách: Quang

## Làm gì
API nhận 1 ảnh, kiểm tra hợp lệ, gọi `score(image)` từ `models/`, đọc EXIF và trả `verdict`, `score`, `exif`, `reason`.

| File | Chức năng |
|---|---|
| `main.py` | `create_app(scorer, settings, loader)`: tạo app, gắn middleware, lỗi, route; lifespan nạp model |
| `routes.py` | Khai báo endpoint |
| `schemas.py` | Hợp đồng JSON: `verdict`, response, mã lỗi |
| `verdict.py` | Ngưỡng và câu chữ `reason`; không lặp logic này ở nơi khác |
| `errors.py` | Bảng mã lỗi, envelope lỗi dùng chung |
| `inference.py` | `InferenceService`: chạy suy luận trên thread riêng, giới hạn slot và timeout |
| `uploads.py` | Đọc file có giới hạn, giải mã một lần, đọc EXIF, kiểm tra điểm từ model |
| `settings.py` | Cấu hình đọc từ biến môi trường |
| `logging.py` | `X-Request-ID` và log có cấu trúc |

Endpoint: `POST /v1/analyze`, `GET /health`, `GET /docs`, `GET /openapi.json`. Giai đoạn nâng cao: `GET /metrics`.

## Cách chạy
Từ thư mục gốc repo:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Chưa có model thì `/health` trả 503; đây là hành vi đúng, không có chế độ model giả khi chạy server. Test tiêm scorer giả qua `create_app(scorer=...)`, hoặc hàm nạp qua `create_app(loader=...)`; `loader` chỉ chạy khi app đi qua lifespan. Nạp lỗi thì ghi log và `/health` trả 503.

Giới hạn suy luận: hết slot trả 503 `SERVICE_BUSY`, quá giờ trả 504 `MODEL_TIMEOUT`. Thread không hủy được CLIP nên sau timeout slot vẫn bị giữ tới khi việc thật sự kết thúc; trong lúc đó request mới nhận 503.

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
- Input: `multipart/form-data`, đúng một file ở trường `file`. Chỉ nhận JPEG hoặc PNG một khung hình, xác định theo nội dung file, không theo đuôi. Tối đa 5.242.880 byte, 24 MP, cạnh dài 10.000 px; cạnh ngắn tối thiểu 256 px.
- Output: JSON `{verdict, score, exif, reason}`; `verdict` là `likely_real`, `uncertain` hoặc `likely_ai`, ngưỡng 0.3 / 0.7.
- `exif` chỉ gồm hãng và model máy; thiếu thì trả `Không có thông tin máy chụp`.
- Lỗi trả envelope `{"error": {code, message, request_id}}`, bảng mã xem D05 trong [`docs/decisions/realcheck-baseline.md`](../docs/decisions/realcheck-baseline.md).

```bash
curl -F "file=@anh.jpg" http://localhost:8000/v1/analyze
```

## Lưu ý và giả định
- Độ bao phủ test của `app/` từ 70% trở lên.
- Đổi schema response phải sửa tài liệu trong cùng PR.
