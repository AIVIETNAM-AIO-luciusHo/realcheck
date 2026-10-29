# RealCheck

API FastAPI phát hiện ảnh do AI tạo: trả **Ảnh thật / Ảnh AI / Chưa chắc**, kèm điểm 0–1 và lý do. Model: CLIP ViT-B/32 + Logistic Regression. Triển khai bằng Docker Compose + Nginx, đo tải bằng Locust.

## Thành viên
| Họ và tên | GitHub | Vai trò |
|---|---|---|
| Lực | [@AIVIETNAM-AIO-luciusHo](https://github.com/Lucius-Ho) | QA & Performance |
| Quang | [@AIVIETNAM-AIO-DangQuang](https://github.com/AIVIETNAM-AIO-DangQuang) | Backend & DevOps (leader) |
| Loan | [@AIVIETNAM-AIO-ThanhLoan](https://github.com/AIVIETNAM-AIO-ThanhLoan) | Data & Evaluation |
| Kiệt | [@AIVIETNAM-AIO-tuankietdzvl1](https://github.com/AIVIETNAM-AIO-tuankietdzvl1) | ML Engineer |

## Cấu trúc
| Thư mục | Nội dung | Phụ trách |
|---|---|---|
| [`app/`](app/) | Mã FastAPI | Quang |
| [`nginx/`](nginx/) | Giới hạn tải | Quang |
| [`models/`](models/) | CLIP + Logistic Regression | Kiệt |
| [`data/`](data/) | Dữ liệu, `labels.csv` | Loan |
| [`streamlit/`](streamlit/) | Giao diện demo | Loan |
| [`tests/`](tests/) | pytest | Lực |
| [`locust/`](locust/) | Đo tải | Lực |
| [`scripts/`](scripts/) | Script đánh giá, xử lý dữ liệu | Lực |
| [`docs/`](docs/) | Báo cáo, kịch bản demo | Lực |
| [`.github/`](.github/) | CODEOWNERS, CI, PR template | Lực + Quang |

Mỗi thư mục có `README.md` riêng (làm gì, cách chạy, input/output, lưu ý).

## Quy ước làm việc
- Không commit thẳng `main`. Nhánh `ten/mo-ta-ngan`, ví dụ `quang/analyze-endpoint`.
- Mở Pull Request vào `main`; GitHub tự gán người review theo [CODEOWNERS](.github/CODEOWNERS); cần CI xanh (`ci-ok`) và ít nhất 1 approval.
- Đổi cách dùng một thư mục thì cập nhật README thư mục đó trong cùng PR.
- Commit tiếng Anh, tiền tố `feat:` `fix:` `docs:` `chore:` `test:`.
- Việc cần làm quản lý bằng GitHub Issues + Projects.
- Không commit dữ liệu, model nặng, secret (`.env`).

## Dữ liệu
CIFAKE (Kaggle), GenImage (NeurIPS 2023); chỉ dùng cho học tập.
