# RealCheck

API FastAPI phát hiện ảnh do AI tạo (Ảnh thật / Ảnh AI / Chưa chắc, kèm điểm 0–1 và lý do). Model: CLIP ViT-B/32 + Logistic Regression. Triển khai bằng Docker Compose + Nginx, đo tải bằng Locust.

## Cấu trúc

| Thư mục | Nội dung | Phụ trách |
|---|---|---|
| `app/` | Mã FastAPI | Quang (Backend) |
| `nginx/` | Cấu hình Nginx, giới hạn tải | Quang (Backend) |
| `models/` | `clip_probe.joblib`, hàm `score(image)` | Kiệt (ML) |
| `data/` | `raw/`, `processed/`, `features/`, `labels.csv` | Loan (Data) |
| `streamlit/` | Giao diện demo | Loan (Data) |
| `tests/` | pytest (từ 15 test) | Lực (QA) |
| `locust/` | Kịch bản đo tải | Lực (QA) |
| `scripts/` | Script đánh giá, xử lý dữ liệu | Lực (QA) |
| `docs/` | Báo cáo, kịch bản demo | Lực (QA) |
| `.github/workflows/` | CI chạy pytest mỗi Pull Request | Lực (QA) |

Mỗi thư mục có `README.md` ghi mục đích. Dữ liệu và model không commit (xem `.gitignore`).

## Quy ước
- Làm việc trên branch riêng, mở Pull Request vào `main`.
- Dữ liệu chỉ dùng cho học tập; trích dẫn GenImage, CIFAKE trong báo cáo.
