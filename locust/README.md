# locust/ – Đo tải

Phụ trách: Lực

## Làm gì
Kịch bản smoke, load, stress, soak; đo p95 và request/giây.

## Cách chạy
`locust -f locust/locustfile.py --host http://<server>`

## Input / Output
- Input: URL server, số người dùng giả lập.
- Output: p95, request/giây, tỉ lệ lỗi.

## Lưu ý và giả định
- Chạy từ máy khác, không chạy trên chính server.
- Con số p95 và request/giây chốt sau lần đo đầu tiên.
