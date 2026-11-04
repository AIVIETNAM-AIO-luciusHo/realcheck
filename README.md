# RealCheck

API FastAPI phát hiện ảnh do AI tạo: trả **Ảnh thật / Ảnh AI / Chưa chắc**, kèm điểm 0–1 và lý do. Model: CLIP ViT-B/32 + Logistic Regression. Triển khai bằng Docker Compose + Nginx, đo tải bằng Locust.

## Thành viên

| Họ và tên | GitHub | Vai trò |
|---|---|---|
| Lực | [@AIVIETNAM-AIO-luciusHo](https://github.com/AIVIETNAM-AIO-luciusHo) | QA & Performance |
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
| [`specs/`](specs/) | Đặc tả từng tính năng theo Spec Kit (`NNN-tên`: spec, plan, tasks) | Lực |
| [`.specify/`](.specify/) | Công cụ Spec Kit và constitution của dự án (`memory/constitution.md`) | Lực |
| [`.github/`](.github/) | CODEOWNERS, CI, PR template | Lực + Loan |

Mỗi thư mục có `README.md` riêng (làm gì, cách chạy, input/output, lưu ý). Riêng `.specify/` chỉ chứa công cụ và constitution; mọi đặc tả nằm trong `specs/` (`000-realcheck-system-baseline` là đặc tả toàn hệ thống, các số tiếp theo là từng tính năng).

```text
realcheck/
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   ├── CODEOWNERS
│   └── pull_request_template.md
├── .specify/                          # công cụ Spec Kit + constitution
│   ├── integrations/
│   ├── memory/
│   │   └── constitution.md
│   ├── scripts/
│   ├── templates/
│   └── workflows/
├── app/
│   └── README.md
├── data/
│   ├── raw/
│   ├── processed/
│   ├── features/
│   └── README.md
├── docs/
│   └── README.md
├── locust/
│   └── README.md
├── models/
│   └── README.md
├── nginx/
│   └── README.md
├── scripts/
│   └── README.md
├── specs/                             # đặc tả từng tính năng
│   ├── 000-realcheck-system-baseline/
│   └── 001-unified-image-normalization/
├── streamlit/
│   └── README.md
├── tests/
│   └── README.md
├── .gitignore
├── LICENSE
└── README.md
```


## Quy ước làm việc
- Không commit thẳng `main`. Nhánh `ten/mo-ta-ngan`.
- Đổi cách dùng một thư mục thì cập nhật README thư mục đó trong cùng PR.
- Commit tiếng Anh, tiền tố `feat:` `fix:` `docs:` `chore:` `test:`.
- Việc cần làm và báo lỗi quản lý bằng Jira (Sprint 1 – Tuần 1).
- Không commit dữ liệu, model nặng, secret (`.env`).

## Quy trình Pull Request

**Trước khi mở PR**
- Mỗi PR gắn một mã Jira (`KAN-xx`) và mã task spec (`Txxx`) nếu có. Đặt tên nhánh `ten/mo-ta-ngan`.
- Một PR một mục đích. PR lớn hơn khoảng 400 dòng code thay đổi (không tính dữ liệu và tài liệu sinh tự động) nên tách nhỏ.
- Chưa xong thì mở **Draft PR**. Chỉ bấm Ready for review khi tự kiểm xong.
- Chạy cục bộ: `ruff check .`, `ruff format --check .`, `pytest --cov=app --cov-fail-under=70`.

**Viết thân PR** theo [mẫu](.github/pull_request_template.md)
- Mục **Kết quả kiểm chứng** là bắt buộc: dán lệnh và số thật (số test chạy, coverage). CI xanh không thay thế mục này.
- Mục **Giới hạn, rủi ro và việc chưa làm** nói thẳng điều chưa kiểm được. Không ghi "đạt" cho số liệu chưa được QA kiểm độc lập.
- Tick checklist khi đã làm thật. Không áp dụng thì ghi N/A và lý do.

**Review và merge**
- Mở PR vào `main`. GitHub gán người review theo [CODEOWNERS](.github/CODEOWNERS). Cần `ci-ok` xanh và ít nhất 1 approval của Code Owner. Tác giả không tự duyệt PR của mình.
- Người review đọc theo thứ tự: mô tả và phạm vi, so với spec và hợp đồng, **tự chạy lại** (không chỉ nhìn CI), rồi đọc diff theo rủi ro (xử lý lỗi, validate đầu vào, secret, dữ liệu).
- Nhận xét ghi rõ mức: **BLOCKING** (phải sửa trước khi merge), **NON-BLOCKING** (nên sửa, có thể thành ticket) hoặc **NIT** (nhỏ).
- Việc còn thiếu khi merge phải thành ticket Jira, không coi là đã xong.
- PR sửa thay phần của người khác (ví dụ ML sửa `scripts/` của Data) phải gắn chủ phần đó review. QA độc lập vẫn kiểm riêng.
- Thay đổi dữ liệu hoặc model cần bằng chứng tái lập (lệnh, commit sạch, seed) trước khi QA kiểm.

## Dữ liệu
CIFAKE (Kaggle), GenImage (NeurIPS 2023); chỉ dùng cho học tập.
