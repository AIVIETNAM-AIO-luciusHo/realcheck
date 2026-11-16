# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong repo RealCheck (kiểm tra ảnh thật hay ảnh AI: FastAPI `/v1/analyze`, CLIP ViT-B/32 + Logistic Regression, UI Streamlit, gateway Nginx). Văn bản và giao diện bằng tiếng Việt; commit và tiêu đề PR bằng tiếng Anh. Cấu trúc thư mục và chủ sở hữu: `README.md`.

## Lệnh (chạy từ gốc repo, Python 3.12 khi nghiệm thu: 3.12.14, Pillow 13.0.0)
```bash
pip install -r requirements.txt -r models/requirements-ml.txt -r streamlit/requirements.txt -r locust/requirements.txt
ruff check . && ruff format --check .          # ruff==0.17.3, cùng bản với CI
pytest --cov=app --cov-fail-under=70 -ra       # test đầy đủ; thiếu torch hoặc locust thì có skip
uvicorn app.main:app --port 8000               # cần REALCHECK_MODEL_PATH trỏ tới model e571
docker compose up -d --build                   # api, ui, nginx; xem docs/deploy.md
```
CI (`.github/workflows/ci.yml`, Python 3.11, không torch và locust) có `lint`, `test` và `ci-ok` (check bắt buộc). Cổng nghiệm thu G01 đến G09: `docs/qa/gate-evidence.md`; G01 không cho phép skip.

## Quy tắc cứng
- **Không** thêm dòng `Co-Authored-By` hay "Generated with Claude Code" vào commit hoặc PR. Không viết lại lịch sử `main`.
- Không commit, push, mở PR, merge hay comment GitHub/Jira khi người phụ trách chưa ra lệnh; mỗi lệnh dùng một lần.
- PR theo `.github/pull_request_template.md`: có mã `KAN-xx` hoặc `#issue`, mục **Kết quả kiểm chứng** (lệnh và số thật) và **Giới hạn, rủi ro và việc chưa làm** có nội dung.
- Khi đang freeze (đợt nghiệm thu), không merge vào `app/ nginx/ models/ locust/ scripts/ docker-compose.yml`; làm trên nhánh, Draft PR.
- Số tự đo ghi là tự đo; phân biệt người viết, người chạy, người tính lại. Không ghi "đạt" cho số chưa có QA độc lập. Không bịa số.
- Không đưa ảnh cá nhân, dữ liệu, model nặng, `.env`, địa chỉ hay mật khẩu máy chủ vào repo, log, báo cáo.
- Model e571 (`models/clip_probe_e571.joblib`) và cache CLIP không nằm trong Git; thiếu thì `/health` không `model_ready`.

## Kiến trúc ngắn
`app/` API (không import torch ở mức module; test mock scorer), `models/` chuẩn hóa, trích đặc trưng, train, `score`; `scripts/` đánh giá, audit, kiểm cổng; `streamlit/` UI; `nginx/` gateway (rate limit, mã lỗi); `locust/` đo tải; `docs/` quyết định (`docs/decisions/realcheck-baseline.md`), báo cáo, runbook.
