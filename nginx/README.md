# nginx/ – Cổng vào và bảo vệ quá tải

Phụ trách: Quang

## Làm gì
Giới hạn 10 request/giây mỗi IP, ảnh tối đa 5MB; vượt giới hạn trả lỗi 429.

## Cách chạy
Chạy cùng `docker compose up -d --build` (khi có `docker-compose.yml`).

## Input / Output
- Input: request từ người dùng và Locust.
- Output: chuyển tiếp sang FastAPI hoặc trả 429.

## Lưu ý và giả định
- Chỉ mở cổng 80 ra ngoài; Grafana truy cập qua SSH tunnel.
