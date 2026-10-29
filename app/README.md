# app/ – FastAPI

Phụ trách: Quang

## Làm gì
API nhận 1 ảnh, kiểm tra hợp lệ, gọi `score(image)` từ `models/`, đọc EXIF và trả `verdict`, `score`, `exif`, `reason`.

| File | Chức năng |
|---|---|
| `main.py` | Khởi tạo FastAPI, khai báo endpoint |

Endpoint: `POST /v1/analyze`, `GET /health`, `GET /metrics`, `GET /docs`.

## Cách chạy
Từ thư mục gốc repo: `uvicorn app.main:app --reload`

## Input / Output
- Input: 1 ảnh (tối đa 5MB, do Nginx giới hạn).
- Output: JSON `{verdict, score, exif, reason}`; ngưỡng 0.3 / 0.7.

## Lưu ý và giả định
- Độ bao phủ test của `app/` từ 70% trở lên.
- Đổi schema response phải sửa tài liệu trong cùng PR.
