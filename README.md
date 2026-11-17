# RealCheck

API FastAPI phát hiện ảnh do AI tạo: trả **Ảnh thật / Ảnh AI / Chưa chắc**, kèm điểm 0–1 và lý do. Model: CLIP ViT-B/32 + Logistic Regression. Triển khai bằng Docker Compose + Nginx, đo tải bằng Locust.

## Thành viên

| Họ và tên | GitHub | Vai trò |
|---|---|---|
| Lực | [@AIVIETNAM-AIO-luciusHo](https://github.com/AIVIETNAM-AIO-luciusHo) | QA & Performance |
| Quang | [@AIVIETNAM-AIO-DangQuang](https://github.com/AIVIETNAM-AIO-DangQuang) | Backend & DevOps (leader) |
| Loan | [@AIVIETNAM-AIO-ThanhLoan](https://github.com/AIVIETNAM-AIO-ThanhLoan) | Data & Evaluation |
| Kiệt | [@AIVIETNAM-AIO-tuankietdzvl1](https://github.com/AIVIETNAM-AIO-tuankietdzvl1) | ML Engineer |

## Trạng thái (15/11/2026, `main` `d018679`)

Đây là trạng thái tiến độ, **chưa phải biên bản nghiệm thu**: lượt nghiệm thu core ([#133](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/133)) hạn hết ngày 17/11/2026. Báo cáo đầy đủ: [`docs/technical-report/progress_report_v3.tex`](docs/technical-report/progress_report_v3.tex) (bản PDF nháp `RealCheck_Technical_Report_V3_DRAFT.pdf`).

- **Chạy được:** `POST /v1/analyze` và `GET /health` qua `uvicorn` hoặc Docker Compose + Nginx; model phục vụ là **e571** (CLIP ViT-B/32 đóng băng + Logistic Regression). Nhãn real = 0, ai = 1; kết luận ba mức với ngưỡng 0,3 và 0,7 (D08, duyệt cho MVP).
- **Hệ thống:** Streamlit → Nginx → FastAPI (1 chỗ suy luận, quá tải trả 503 `SERVICE_BUSY` theo D12) → model. Mã lỗi gateway 413, 429, 502, 504; truy cập từ ngoài mạng lab qua SSH tunnel (D13).
- **Độ chính xác:** 94,53% (363/384 ảnh test GenImage đã lọc, Wilson 91,78% đến 96,40%), **chưa được kiểm độc lập**; đừng trích là "đạt 90%". Trên ảnh thật ngoài GenImage, model gọi **64/76 ảnh điện thoại và Zalo là "Ảnh AI"** ([ADV-06](docs/cohorts-adv06.md), mẫu nhỏ, chủ yếu iPhone 11).
- **Quy trình:** mọi thay đổi vào `main` qua Pull Request, `ci-ok` và một approval (vai Admin có quyền bypass Ruleset).
- **Ảnh MPO (iPhone chân dung):** nhận và chỉ chấm khung đầu (PR #106); hai ảnh MPO thật đã qua API, chưa qua Nginx.

### Chín cổng nghiệm thu (`scripts/check_mvp_gates.py`)

| Cổng | Kết quả tại 15/11 | Ghi chú |
|---|---|---|
| G01 Unit test, coverage `app/` | Đạt | 1.167 test, 0 skip, coverage 99,43% (Tester, nhánh PR #155); CI báo 5 skip do thiếu gói Locust |
| G02 Audit shortcut | **Chưa đạt** | Probe pixel: A_eff 0,72 đến 0,97 > 0,55; không đổi tiêu chí ([#147](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/147)) |
| G03 Accuracy GenImage | Đạt cơ học, **chưa độc lập** | 94,53%; kiểm độc lập chưa làm |
| G04 Gateway, G05 UI | Đạt | `check_gateway` 8/8; kiểm UI trình duyệt 6/6 trên VPS ngày 15/11 |
| G06 SLO | Đạt | Ký 14/11, p95 ≤ 400 ms, RPS ≥ 0,6, lỗi ≤ 8%, 2 user |
| G07 Load, G08 Soak | Đạt **trên máy của Lực** | p95 223,6 và 241,7 ms; client cùng phần cứng với server |
| G09 Recovery | Lượt 1 không đạt, lượt sau đạt | Giữ cả hai kết quả |

`check_mvp_gates` sẽ thoát mã 1 vì G02, nên kết luận hiện tại là **"core chưa đạt G02"**, không phải 9/9. Hướng dẫn thu bằng chứng từng cổng: [`docs/qa/gate-evidence.md`](docs/qa/gate-evidence.md).

### Giới hạn đã biết

- Ảnh thật chụp bằng điện thoại thường bị gọi "Ảnh AI"; 94,53% chỉ áp dụng cho ảnh kiểu GenImage.
- Tín hiệu tầng pixel còn sót sau chuẩn hóa (G02), chưa rõ do nén hay bản chất ảnh.
- Số đo tải lấy trên máy của Lực, chưa trên máy đạt cấu hình ([#132](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/132)); VPS mượn (2 nhân, 1,9 GiB, dùng chung) chỉ kiểm chức năng và rollback, không đo tải.
- Giám sát (`/metrics`, Prometheus, Grafana) chưa triển khai; dùng báo cáo HTML của Locust.

### Việc tiếp theo

| Việc | Issue |
|---|---|
| Nghiệm thu core 17/11 | [#133](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/133), [#134](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/134), [#147](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/147) |
| Cải thiện nhận diện ảnh thật ngoài GenImage (ADV-12, E0 đến E5) | [#144](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/144), #157 đến #161 |
| Giám sát và `/metrics` (ADV-01 đến ADV-04) | #162 đến #165 |
| Robustness, bộ ảnh điện thoại mới | [#52](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/52), #166 |
| Tối ưu hiệu năng, TLS, kiểm chức năng trên VPS | #167, #168, #169 |

## Chạy nhanh

Model không nằm trong Git. Lấy gói e571 và đặt `REALCHECK_MODEL_PATH` theo [`app/README.md`](app/README.md) (mặc định trỏ tới model cũ, không dùng).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r models/requirements-ml.txt -r streamlit/requirements.txt
export REALCHECK_MODEL_PATH="$PWD/models/clip_probe_e571.joblib"
uvicorn app.main:app --port 8000        # /health trả 200 khi đã nạp xong model
```

- Từng bước, kiểm checksum, xử lý lỗi thường gặp, smoke test và kịch bản demo: [`docs/qa/m1-runbook-and-demo.md`](docs/qa/m1-runbook-and-demo.md).
- Triển khai Compose lên máy lab, cập nhật và rollback: [`docs/deploy.md`](docs/deploy.md); biến môi trường mẫu: [`.env.example`](.env.example).
- Kiểm thử: `ruff check .`, `ruff format --check .`, `pytest --cov=app --cov-fail-under=70`.
- Kiểm lint trước mỗi commit: `pip install pre-commit && pre-commit install` (cấu hình `.pre-commit-config.yaml`, ruff 0.17.3).

## Cấu trúc

| Đường dẫn | Nội dung | Phụ trách |
|---|---|---|
| [`app/`](app/) | Mã FastAPI: route, schema, mã lỗi, suy luận, kiểm tra upload | Quang |
| [`nginx/`](nginx/) | Gateway: giới hạn tải, timeout, ánh xạ lỗi | Quang |
| `Dockerfile`, `docker-compose.yml`, `.env.example` | Image API và Compose (API, UI, Nginx) | Quang |
| [`models/`](models/) | Trích đặc trưng CLIP, huấn luyện, `score`; file model không nằm trong Git | Kiệt |
| [`data/`](data/) | `labels.csv`, báo cáo audit metadata, thư mục dữ liệu (không commit ảnh) | Loan |
| [`streamlit/`](streamlit/) | Giao diện demo và trang kết quả đánh giá | Loan |
| [`tests/`](tests/) | pytest đơn vị, hợp đồng API và `integration/` (UI qua gateway) | Lực |
| [`locust/`](locust/) | Kịch bản và cấu hình đo tải (baseline, stress, soak, recovery) | Lực |
| [`scripts/`](scripts/) | Dữ liệu, đánh giá, robustness, audit, kiểm cổng nghiệm thu, smoke test | Lực |
| [`docs/`](docs/) | Báo cáo, sổ quyết định (`decisions/`), biên bản QA (`qa/`), số đo (`reports/`, `performance/`) | Lực |
| [`specs/`](specs/) | Đặc tả theo Spec Kit (`NNN-tên`: spec, plan, tasks); `000` là đặc tả toàn hệ thống | Lực |
| [`.specify/`](.specify/) | Công cụ Spec Kit và constitution (`memory/constitution.md`) | Lực |
| [`.github/`](.github/) | CODEOWNERS, CI (`ci.yml`), mẫu PR | Lực + Loan |

Mỗi thư mục chính có `README.md` riêng (làm gì, cách chạy, input/output, lưu ý). Quyết định đã duyệt nằm trong [`docs/decisions/realcheck-baseline.md`](docs/decisions/realcheck-baseline.md).

```text
realcheck/
├── .github/            # CODEOWNERS, workflows/ci.yml, pull_request_template.md
├── .specify/           # công cụ Spec Kit + constitution
├── app/                # FastAPI (main, routes, schemas, errors, inference, uploads, verdict, settings, logging)
├── data/               # labels.csv, metadata_audit.json; raw/ processed/ features/ metadata/
├── docs/               # decisions/ qa/ reports/ performance/ + báo cáo ml-*, deploy.md, test-plan.md
├── locust/             # locustfile.py + baseline/rate_only/recovery/soak/stress.conf
├── models/             # clip_input, train, evaluate, score, normalize, ...
├── nginx/              # nginx.conf
├── scripts/            # check_*.py, evaluate.py, robustness_manifest.py, smoke_api.py, ...
├── specs/              # 000-realcheck-system-baseline, 001-unified-image-normalization
├── streamlit/          # app.py, api_client.py, pages/
├── tests/              # test_*.py, integration/
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── requirements.txt
└── README.md
```

## Quy ước làm việc
- Không commit thẳng `main`. Nhánh `ten/mo-ta-ngan`.
- Đổi cách dùng một thư mục thì cập nhật README thư mục đó trong cùng PR.
- Commit tiếng Anh, tiền tố `feat:` `fix:` `docs:` `chore:` `test:`.
- Việc cần làm và báo lỗi quản lý bằng Jira (`KAN-xx`) và GitHub Issues.
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
