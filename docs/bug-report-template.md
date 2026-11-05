# Mẫu báo lỗi (Jira)

Sao chép phần dưới vào ticket Jira loại Bug. Bản này đi cùng [kế hoạch test](test-plan.md); mã TC trong kế hoạch dùng để ghi ca nào bị lỗi.

## Mẫu

- **Tóm tắt:** (một câu: cái gì sai, ở đâu)
- **Mã task liên quan:** (mã Jira dạng `KAN-xx`; nếu thuộc spec thì thêm mã task spec dạng `Txxx`, ví dụ `T016`; ghi thêm mã ca của kế hoạch test như `TC-04` nếu có)
- **Người phụ trách xử lý:** (tên)
- **Commit/PR:** (SHA ngắn của commit đã chạy, và PR hoặc nhánh nếu có)
- **Mã yêu cầu (`X-Request-ID`):** (giá trị header `X-Request-ID` của phản hồi lỗi, cũng là `error.request_id` trong thân phản hồi; ghi `Không có` nếu không phải lỗi gọi API)
- **Bước tái hiện:**
  1. ...
  2. ...
- **Kết quả mong đợi:** ...
- **Kết quả thực tế:** ...
- **Bằng chứng:** (xem gợi ý bên dưới)
- **Mức độ:** (Nghiêm trọng / Cao / Trung bình / Thấp)
- **Môi trường:** (hệ điều hành, phiên bản Python, chạy local hay CI, địa chỉ API đã gọi)

## Gợi ý về bằng chứng

- Dán trực tiếp vào ticket: thân phản hồi lỗi (JSON), dòng lệnh đã chạy, đoạn log hoặc traceback liên quan, dòng pytest thất bại. Không chỉ trỏ tới file nằm ngoài repo hay trên máy cá nhân.
- Kèm liên kết tới lần chạy CI hoặc PR nếu có. Đính kèm ảnh chụp hoặc file nhỏ trực tiếp vào ticket.
- Không dán đường dẫn tuyệt đối của máy cá nhân, khóa bí mật hay ảnh có mặt người lạ. Nêu SHA256 hoặc mô tả file đầu vào để người khác tạo lại được.

## Thang mức độ (đề xuất)

Thang dưới đây là đề xuất của kế hoạch test, chưa đối chiếu với trường Priority thực tế của dự án Jira. Nếu Jira dùng thang khác, ghi giá trị Jira vào trường Priority và giữ thang này làm gợi ý.

| Mức độ | Dùng khi |
|---|---|
| Nghiêm trọng | API sập hoặc trả kết quả sai hợp đồng trên đầu vào hợp lệ; dữ liệu bị rò hoặc hỏng; lộ stacktrace |
| Cao | Sai mã lỗi hoặc mã HTTP so với bảng D05; test hợp đồng đỏ; split dữ liệu bị rò |
| Trung bình | Sai thông điệp, thiếu trường phụ, sai tài liệu; có cách tránh |
| Thấp | Lỗi trình bày, lỗi chính tả, cải tiến nhỏ |

## Ví dụ điền mẫu

Ca giả định để minh họa cách điền, không phải lỗi đã xảy ra. Mã `KAN-00` là mã giữ chỗ.

- **Tóm tắt:** `/v1/analyze` trả 500 thay vì 400 `INVALID_IMAGE` khi gửi file text đuôi `.jpg`
- **Mã task liên quan:** KAN-00, TC-04
- **Người phụ trách xử lý:** Quang
- **Commit/PR:** `abc1234`, nhánh `ten/mo-ta-ngan`
- **Mã yêu cầu (`X-Request-ID`):** `6e8c9d7d-e5dc-43a0-a59c-575e586684d8`
- **Bước tái hiện:**
  1. Tạo file `fake.jpg` chứa chữ "hello".
  2. Gửi file này bằng `POST /v1/analyze`, trường `file`.
- **Kết quả mong đợi:** HTTP 400, `error.code` là `INVALID_IMAGE`, model không bị gọi (bảng D05).
- **Kết quả thực tế:** HTTP 500, `error.code` là `INTERNAL_ERROR`.
- **Bằng chứng:** thân phản hồi JSON dán trực tiếp, lệnh `curl` đã dùng, đoạn log máy chủ có cùng `request_id`.
- **Mức độ:** Cao
- **Môi trường:** Linux, Python 3.11, chạy local.

## Checklist chất lượng

- [ ] Đã tái hiện được lỗi ít nhất một lần nữa theo đúng các bước.
- [ ] Có bằng chứng dán trực tiếp (log, thân phản hồi, ảnh chụp) hoặc liên kết CI/PR.
- [ ] Gắn đúng mã Jira `KAN-xx`, mã task spec `Txxx` nếu có, và người phụ trách.
- [ ] Ghi commit đã chạy; với lỗi API có thêm `X-Request-ID`.
