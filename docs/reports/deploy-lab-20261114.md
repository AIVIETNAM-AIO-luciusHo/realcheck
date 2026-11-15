# Biên bản deploy máy lab: 2026-11-14

Người deploy: Quang. Người kiểm độc lập: **chưa có** (cần một người khác chạy lại mục "Kiểm từ máy khác"). Lệnh lấy thông tin: [`deploy.md` mục 10](../deploy.md#10-thông-tin-cho-biên-bản). Giờ ghi theo máy lab (UTC+7).

**Kết luận:** Compose core (API, UI, Nginx) chạy được trên một server Linux thật, với model e571. Smoke (26/26 ca), gateway (8/8 ca), rollback mã và rollback model đều đạt. **Máy này thấp hơn yêu cầu của `deploy.md`** (2 nhân, 1,9 GiB RAM) và chạy chung với dịch vụ của người khác, nên phải hạ giới hạn tài nguyên (bảng "Lệch so với cấu hình đã ghi"). Biên bản này **không** dùng làm số đo hiệu năng và chưa có Locust hay soak (D09, D10, D14, G06–G09 vẫn chưa làm).

## Máy và truy cập

| Mục | Giá trị |
|---|---|
| Máy | VPS mượn, IP công khai, không phải mạng lab. Địa chỉ không ghi trong repo |
| URL gateway | `http://127.0.0.1:8090` trên máy lab. Không mở ra Internet |
| Cách truy cập | **SSH tunnel** (D13: ngoài mạng lab bắt buộc tunnel), ví dụ `ssh -L 8080:127.0.0.1:8090 <user>@<lab>` rồi mở `http://localhost:8080/` |
| CPU (model, số nhân `nproc`) | Intel Xeon E5-2696 v4 @ 2.20GHz, **2 nhân** (VM KVM) |
| RAM (`free -h`) | **1,9 GiB**, không có swap; còn trống khoảng 1,0–1,1 GiB trước khi deploy, 630–640 MiB sau khi deploy |
| OS, kernel (`uname -a`) | Ubuntu 24.04.3 LTS, Linux 6.8.0-88-generic x86_64 |
| Docker Engine, Compose | 29.9.2, Compose 5.6.1 |
| Cổng mở ra ngoài | Không có cổng nào của RealCheck: Nginx chỉ nghe `127.0.0.1:8090` (`ss -ltn`), 8000 và 8501 chỉ có trong mạng Compose. Cổng 80/443 của máy là của dịch vụ khác, không thuộc RealCheck |
| Dịch vụ khác trên máy | 3 container của người khác (Nginx cổng 80/443, 2 backend), chạy liên tục trước, trong và sau khi deploy; không đụng tới |
| Internet | Có. `download.pytorch.org`, GitHub, Hugging Face nhanh; PyPI chậm. Thiếu `unzip`, `rsync`: giải nén model bằng `python3 -m zipfile`, cache CLIP tải bằng `load_encoder()` (mục 3), không cài thêm gói |

## Phiên bản

| Mục | Giá trị |
|---|---|
| Commit | `9c8162f6e9150ff0edbd6ff1c56033c9dacaa799` (`main`) |
| `git status --short` | Trống |
| `REALCHECK_TAG` | `9c8162f` |
| Image ID `realcheck-api` | `sha256:b8ef2be12e29…` |
| Image ID `realcheck-ui` | `sha256:40aa968c34c0…` |
| Image ID `nginx:1.28.0-alpine` | `sha256:30f1c0d78e0a…` |
| `REALCHECK_MODEL_FILE`, SHA256 model | `clip_probe_e571.joblib`, `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494` (khớp `.sha256`; zip release `baf7bd57…be6beea07`, `SHA256SUMS` OK) |
| Cache CLIP | Revision `327ab6726d33…`, tải trên máy lab bằng `load_encoder()`; 10 file trùng SHA256 với cache đã dùng khi kiểm trên máy Quang |
| SHA256 `docker-compose.yml` | `7c71792bdc29…` |
| SHA256 `nginx/nginx.conf` | `2122c11fa1f0…` |
| SHA256 `.env` | `54aefb7dbf71…` (khác máy khác vì có `REALCHECK_HTTP_PORT` và `COMPOSE_FILE` riêng) |
| SHA256 file override `compose.lab.yml` | `d1004f55d15a…` |
| SHA256 `docker compose config` | `b997cbd830b9…` |

Build trên máy lab: API 230 giây, UI 69 giây (bản đầu); bản thứ hai dùng lại cache, 1–2 giây.

## Lệch so với cấu hình đã ghi

| Mục | `docker-compose.yml` / `deploy.md` | Máy này | Lý do |
|---|---|---|---|
| Giới hạn CPU/RAM | api 4 / 2 GiB, ui 1 / 512 MiB, nginx 0,5 / 128 MiB | api **1,5 / 900 MiB**, ui **0,5 / 256 MiB**, nginx **0,25 / 64 MiB** | Máy 2 nhân: Docker không cho `cpus: 4`. Giữ tổng RAM của RealCheck dưới RAM còn trống để không ảnh hưởng dịch vụ khác |
| Cổng gateway | `REALCHECK_HTTP_PORT=80`, mở cho mạng lab | `127.0.0.1:8090` | Cổng 80 đã có dịch vụ khác; máy có IP công khai và Docker bỏ qua `ufw`, nên chỉ nghe loopback để không mở ra Internet (D13) |
| Tường lửa | `ufw allow from <subnet-lab> to any port 80` | Không đổi `ufw` | Không mở cổng nào; `ufw` của máy thuộc dịch vụ khác |

File override nằm ngoài repo (`/srv/realcheck-lab/compose.lab.yml`), nạp bằng `COMPOSE_FILE=docker-compose.yml:/srv/realcheck-lab/compose.lab.yml` trong `.env`; repo trên máy lab không sửa tay.

## Cấu hình chạy

| Mục | Giá trị |
|---|---|
| Worker, slot suy luận | 1 worker, `REALCHECK_INFERENCE_SLOTS=1` (không làm #97) |
| Thread CLIP | 4 (trên quota 1,5 CPU) |
| Timeout model / gateway / UI | 10 s / 15 s / 60 s |
| Rate limit | 10 r/s, burst 10 nodelay |
| Giới hạn CPU/RAM container | Xem bảng "Lệch so với cấu hình đã ghi" |
| RAM API (`docker stats`) | 404–430 MiB khi rảnh sau khi nạp model; **đỉnh 641 MiB** khi chạy smoke (có ảnh 4000×3000 và ảnh 5 MiB), lấy mẫu mỗi giây |
| `memory.peak` cgroup API | 849 MiB (gồm page cache khi đọc trọng số CLIP, không phải RSS) |
| OOM, restart | Không (`OOMKilled=false`, `RestartCount=0`) |
| Nạp model | `model_loaded` 12,0–12,4 s; `/health` 200 sau 20,8 s kể từ `docker compose up -d` |

## Kiểm từ máy khác

Máy kiểm: máy Quang (Windows 11), qua SSH tunnel tới `127.0.0.1:8090` của máy lab, mã `main` `9c8162f`. Từ Internet, `http://<lab>:8090/health` không kết nối được (đúng).

| Kiểm | Kết quả |
|---|---|
| `GET /health` | 200 `{"status":"ok","model_ready":true}` |
| `GET /docs` | 200 |
| `scripts.smoke_api` với model thật (`--delay 0.15`) | **26/26 ca đạt**, 0 lỗi, 0 cảnh báo ([JSON](deploy-lab-20261114-smoke.json)); ảnh thật GenImage `likely_real` 0,026, ảnh Midjourney `likely_ai` 0,985. Chạy lần hai khi đo RAM: 26/26 |
| `scripts.check_gateway --upstream prompt --require-retry-after` | **8/8 ca đạt** ([JSON](deploy-lab-20261114-gateway.json)): 27/50 request vượt giới hạn trả 429; body 6 MiB 413; biên 5.242.880 B 200, 5.242.881 B 413; dừng API trả 504; bật lại 200 sau 14,1 s |
| UI: ảnh JPEG điện thoại, ảnh PNG, file lỗi, WebSocket | **Chưa kiểm bằng trình duyệt.** Qua tunnel `GET /` trả 200 |

Ghi chú về `check_gateway`: người chạy không bấm Enter bằng tay mà dùng một script nhỏ truyền `ask` vào `check_gateway.main`; mỗi lần script nhắc, nó chạy `docker compose stop api` (2,8 s) hoặc `docker compose start api` (0,8 s) trên máy lab rồi mới trả lời, đúng thứ tự như `deploy.md` mục 4. Khi dừng API, gateway trả 504 thay vì 502: Nginx còn giữ IP cũ của `api` trong cache DNS 10 giây (đã ghi ở D05).

## Rollback

Dò `/health` trên máy lab mỗi 0,5 giây. "Gián đoạn" là từ request lỗi đầu tiên tới 200 đầu tiên sau đó.

| Bước | Thời điểm | Commit / tag / model | Kết quả |
|---|---|---|---|
| Deploy | 21:43:08 | `9c8162f`, e571 | `/health` 200 sau 20,8 s |
| Rollback mã (mục 9) | 21:54:12 | `d78197b` (merge `main` liền trước), `up -d --no-build` | Container chạy `realcheck-api:d78197b`, `realcheck-ui:d78197b`; gián đoạn **15,6 s**, chỉ có 502 |
| Phục hồi | 21:54:37 | `9c8162f`, `up -d --no-build` | `realcheck-api:9c8162f`, `realcheck-ui:9c8162f`; gián đoạn **15,1 s**, chỉ có 502 |
| Model hỏng (mục 8) | 22:08:49 | `clip_probe_bad.joblib` (file `.sha256` sai) | `/health` 503 `not_ready`, log `model_load_failed` `ValueError` `Model checksum mismatch` |
| Rollback model (mục 9) | 22:08:55 | `clip_probe_e571.joblib` | `/health` 200 sau 13,6 s, `model_loaded` 12.023 ms. Đã xóa file model hỏng |

`nginx/nginx.conf` và `docker-compose.yml` giống nhau giữa `d78197b` và `9c8162f`. Khác với ghi chú ở `deploy.md` mục 7: khi `up -d --no-build` tạo lại api và ui, Nginx **không** bị tạo lại (vẫn `Up` từ lúc deploy).

## Chưa làm

- Kiểm UI bằng trình duyệt qua Nginx (tải ảnh, xem kết quả, giới hạn 5 MiB).
- Người kiểm độc lập chạy lại mục "Kiểm từ máy khác".
- Locust baseline, soak 30 phút (RSS sau warmup và cuối), recovery: chờ Lực/QA. Lưu ý: qua SSH tunnel mọi client dùng chung 10 r/s (D13); máy 2 nhân và giới hạn đã hạ nên số đo không đại diện cho cấu hình 4 CPU / 2 GiB.
- Thời hạn mượn máy: chưa xác nhận.
