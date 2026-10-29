# tests/ – pytest

Phụ trách: Lực

## Làm gì
Từ 15 test trở lên cho API, model và dữ liệu. Test chống phá: ảnh pixel cực lớn, file giả đuôi `.jpg`, gửi liên tục để kiểm tra 429. Test độ bền model: xoay, cắt viền, thu nhỏ, chỉnh sáng.

## Cách chạy
`pytest --cov=app --cov-fail-under=70`

## Input / Output
- Input: code trong `app/`, `models/`, pipeline dữ liệu.
- Output: kết quả pass/fail và độ bao phủ.

## Lưu ý và giả định
- Người kiểm tra dữ liệu phải khác người làm dữ liệu.
- Mock CLIP trong test để CI không phải tải model nặng.
