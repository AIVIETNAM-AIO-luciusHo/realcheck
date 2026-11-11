# Diễn tập deploy, rollback và phục hồi: 2026-11-11

Người chạy: Quang. **Diễn tập trên máy local, không phải máy lab**: chứng minh quy trình trong [`deploy.md`](../deploy.md) chạy được, không thay bằng chứng trên server (MVP-08 tiêu chí 2, 3 còn chờ máy lab). Log đầy đủ, đã thay đường dẫn máy cá nhân bằng `<repo>`, `<deploy-dir>`: [`deploy-rollback-rehearsal-20261111-log.txt`](deploy-rollback-rehearsal-20261111-log.txt).

## Cách làm

- Thư mục deploy là một git worktree riêng, đóng vai thư mục `/srv/realcheck` trên máy lab; model e571 (SHA256 `e5718345…`) và cache CLIP được chép vào phần gitignored của nó.
- Bản cũ: `main` tại `ed51cee` (Compose chưa có `REALCHECK_TAG`, image tag `latest`). Bản mới: `d1bbc57` (thêm `REALCHECK_TAG`, `.env`).
- Mỗi bước đo `/health` mỗi 0,5 giây cho tới 200, ghi image của container đang chạy, rồi gửi một ảnh PNG qua `POST /v1/analyze`.

## Kết quả

| Bước | Lệnh chính | Commit thư mục deploy | Image API đang chạy | Không trả 200 | `POST` |
|---|---|---|---|---|---|
| 1. Deploy bản cũ | `docker compose up -d --build` | `ed51cee` | `realcheck-api` `f4ac426b…` | 11,4 s | 200 |
| 2. Cập nhật (mục 7) | `git checkout d1bbc57`, `.env`, `docker compose build`, `up -d` | `d1bbc57` | `realcheck-api:d1bbc57` `e308b894…` | 11,3 s | 200 |
| 3. Rollback mã và image (mục 9) | `git checkout ed51cee`, `up -d --no-build` | `ed51cee` | `realcheck-api` `f4ac426b…` | 11,4 s | 200 |
| 4. Phục hồi (mục 9) | `git checkout d1bbc57`, `up -d --no-build` | `d1bbc57` | `realcheck-api:d1bbc57` `e308b894…` | 11,4 s | 200 |
| 5. Model hỏng (mục 8) | `REALCHECK_MODEL_FILE=clip_probe_bad.joblib` (sai checksum), `up -d api` | `d1bbc57` | — | `/health` 503, log `model_load_failed` `Model checksum mismatch` | — |
| 6. Rollback model (mục 9) | `REALCHECK_MODEL_FILE=clip_probe_e571.joblib`, `up -d api` | `d1bbc57` | `realcheck-api:d1bbc57` | 11,9 s, log `model_loaded` 10.316 ms | 200 |

Rollback ở bước 3 và phục hồi ở bước 4 chạy lại đúng image ID cũ, không build lại. Trong lúc API nạp lại, gateway trả 502 `API_UNAVAILABLE`, không trả trang HTML. Container Nginx không bị tạo lại khi đổi commit.

## Thông tin theo mẫu biên bản

| Mục | Giá trị |
|---|---|
| Máy | Intel Xeon W-2123 3,60 GHz; Windows 11 Pro; Docker Desktop 29.8.2 (WSL2), Docker thấy 8 CPU, 8.163.885.056 byte RAM |
| Commit cuối, `git status` | `d1bbc57ecfdf5d7fa56d11ebb3e6c261c742169e`, không sửa tay |
| `.env` | `REALCHECK_TAG=d1bbc57`, `REALCHECK_MODEL_FILE=clip_probe_e571.joblib`, `REALCHECK_HTTP_PORT=80` |
| `realcheck-api:d1bbc57` / `latest` | `sha256:e308b89422b6…` / `sha256:f4ac426b289f…` |
| `realcheck-ui:d1bbc57` / `latest` | `sha256:4363ce6594c0…` / `sha256:ef647a4406a2…` |
| `nginx:1.28.0-alpine` | `sha256:30f1c0d78e0a…` |
| SHA256 model e571 | `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494` |
| SHA256 `nginx/nginx.conf` | `5e11a2b865fde6c9b088438f3057b2bc39ad91d28b50766e5c4a711449fb3e2c` |
| Worker, slot, thread CLIP | 1, 1, 4 |
| Giới hạn CPU/RAM container | Chưa đặt |

## Phát hiện

- **Nginx không tự nạp lại cấu hình khi đổi commit.** `nginx/nginx.conf` được mount như một file riêng; `git checkout` thay file, container có thể vẫn đọc bản cũ. Lần này hai commit có cùng `nginx.conf` nên không ảnh hưởng. Đã bổ sung vào `deploy.md` mục 7 và 9: `docker compose up -d --force-recreate nginx` khi cấu hình đổi.
- Lần chạy đầu của script diễn tập hỏng giữa chừng do PowerShell 5.1 đọc script UTF-8 không BOM sai bảng mã; lỗi của script, không phải của quy trình. Kết quả trên là lần chạy lại đầy đủ.

## Chưa kiểm

- Máy lab Linux, URL lab, kiểm từ máy khác (MVP-08 tiêu chí 2, 3).
- UI bằng trình duyệt qua gateway (ảnh điện thoại, PNG, WebSocket) trên server.
- Rollback khi `nginx.conf` thật sự khác giữa hai commit.
