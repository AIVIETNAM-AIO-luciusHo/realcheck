# Jira liên quan đến nhánh ML

Nhánh: [kiet/ml-normalization-release](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/tree/kiet/ml-normalization-release).

| Jira | Phạm vi trong nhánh | Spec |
|---|---|---|
| [KAN-37 — Module chuẩn hóa ảnh dùng chung](https://quangtadang4206.atlassian.net/browse/KAN-37) | Chuẩn hóa dùng chung, kiểm JPEG/EXIF/kích thước; version 1 giữ nguyên | 001: T005, T019 |
| [KAN-39 — Đồng bộ score, CLIP và trích đặc trưng](https://quangtadang4206.atlassian.net/browse/KAN-39) | Hợp đồng đầu vào/cache, classes_, score hữu hạn; parity train/serve | 001: T009–T011 |
| [KAN-44 — Trích đặc trưng và train lại](https://quangtadang4206.atlassian.net/browse/KAN-44) | Candidate giữ split cũ: extract 9.708 ảnh, train GenImage C=10, val 97,24%/871 | 001: T024 |
| [KAN-51 — Khóa model và đánh giá GenImage test](https://quangtadang4206.atlassian.net/browse/KAN-51) | Protocol khóa, holdout lọc lịch sử, test một lần 94,53%/384 theo user authorization | MVP-04; liên quan 000: T013, AC-25 |

Chi tiết code/phạm vi: [hồ sơ ML](ml-normalization-release.md). Model, lệnh, commit nguồn, metrics theo source và giới hạn: [lần train/test thực tế](ml-final-experiment.md).

Đây là ánh xạ ticket với nhánh và bằng chứng triển khai, không xác nhận Jira đã đổi trạng thái hoặc QA độc lập đã duyệt. KAN-41 làm giúp Lực ở nhánh riêng `kiet/kan-41-normalization-qa`, không thuộc bảng này.

Commit liên kết tham chiếu đủ KAN-37, KAN-39, KAN-44 và KAN-51 để GitHub for Jira có thể nhận khi integration đã được cấu hình. Không dùng Smart Commit để chuyển trạng thái, ghi worklog hay đăng comment.
