# Biên bản kiểm gateway (KAN-54)

Sao chép thành `docs/qa/gateway-report-<ngày>.md` và điền. Người kiểm KHÁC người viết cấu hình Nginx. Script chỉ gọi HTTP; người chạy tự tắt/bật upstream. Bản kiểm với server giả không thay thế lần chạy với Nginx thật.

## 1. Môi trường

| Mục | Giá trị |
|---|---|
| Ngày, người kiểm | |
| Commit repo và commit cấu hình `nginx/`, trạng thái dirty | |
| `--base-url` | |
| Chính sách đã chốt (D13): rate (r/s), burst, nodelay hay không, Retry-After | |
| Giới hạn body (D06) và phần dư multipart đã chọn | |
| Timeout Nginx (D11) | |
| Cách tắt/làm chậm upstream | |

## 2. Lệnh và mã thoát

```bash
python -m scripts.check_gateway --base-url http://localhost --fixture <ảnh hợp lệ> \
  --rate <r/s> --burst <n> --upstream prompt --out .cache/gateway-evidence.json
```

Mã thoát: ___ (0 đạt, 1 có ca lỗi, 2 thiếu tham số/fixture hoặc không kết nối). Nếu dùng `--upstream skip`, mục 3 hàng 5-6 là Chưa.

## 3. Kết quả

| # | Ca | Kỳ vọng | Thực tế | Đạt / Lỗi / Chưa |
|---|---|---|---|---|
| 1 | Dưới giới hạn vẫn 200 + X-Request-ID | 200 | | |
| 2 | Vượt giới hạn | có 429, envelope, không 5xx | | |
| 3 | Phục hồi sau rate limit | 200 sau cooldown | | |
| 4 | Body vượt giới hạn | 413 FILE_TOO_LARGE, envelope | | |
| 5 | Upstream tắt/chậm | 502/503/504, envelope, không lộ nội bộ | | |
| 6 | Phục hồi khi upstream bật lại | 200 trong thời hạn | | |

Đính kèm JSON bằng chứng. Ghi chú: XFF không được đặt; rate limit theo IP thấy tại gateway.

## 4. Lỗi và câu hỏi còn mở

| Mã Jira | Tóm tắt | Mức độ | Chặn demo? | Người xử lý |
|---|---|---|---|---|
| | | | | |

## 5. Chữ ký

| Vai trò | Họ tên | Ngày |
|---|---|---|
| Người viết cấu hình gateway | | |
| Người kiểm | | |
