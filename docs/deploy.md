# Triển khai core lên máy lab

Phụ trách: Quang. Áp dụng cho Compose core (API, UI Streamlit, gateway Nginx) trong `docker-compose.yml`.

**Trạng thái (2026-11-11):** chưa có máy lab. Hướng dẫn này đã được diễn tập trên máy local, gồm cả rollback và phục hồi ([biên bản diễn tập](reports/deploy-rollback-rehearsal-20261111.md)); chưa có bằng chứng trên server. Khi có máy, điền [mẫu biên bản](deploy-record-template.md).

## 1. Máy lab

| Mục | Yêu cầu |
|---|---|
| Hệ điều hành | Linux x86_64 có Docker Engine và Docker Compose v2, `git`, `curl`, `sha256sum` |
| Ổ đĩa | Khoảng 5 GB: image API 2,3 GB, image UI, cache CLIP 0,6 GB, các image cũ giữ để rollback |
| RAM | Container API dùng khoảng 500 MiB sau khi nạp model (đo local) |
| CPU | CLIP dùng 4 thread (`torch.set_num_threads(4)`); 1 worker, 1 slot suy luận (D12) |
| Mạng | Chỉ mở cổng gateway (mặc định 80) cho mạng lab hoặc qua SSH tunnel (D13) |

Chưa đặt giới hạn CPU/RAM cho container; chờ benchmark MVP-09 rồi mới chốt (D12).

## 2. Bố cục thư mục

Thư mục deploy là một git checkout ghim tại **một commit**, ví dụ `/srv/realcheck`:

| Đường dẫn | Nội dung | Trong Git? |
|---|---|---|
| (gốc) | Mã nguồn tại commit đang deploy | Có |
| `models/` | File model và `.sha256` | Không (gitignored) |
| `.cache/huggingface/` | Trọng số CLIP revision `327ab672…` | Không |
| `artifacts/` | Báo cáo đánh giá cho trang UI (có thể trống) | Không |
| `.env` | `REALCHECK_TAG`, `REALCHECK_MODEL_FILE`, `REALCHECK_HTTP_PORT` | Không |

File không nằm trong Git sẽ giữ nguyên khi `git checkout` sang commit khác, nên đổi commit không làm mất model hay cache.

## 3. Cài lần đầu

```bash
git clone https://github.com/AIVIETNAM-AIO-luciusHo/realcheck.git /srv/realcheck
cd /srv/realcheck
git checkout <commit>                        # commit đã review, không dùng nhánh đang đổi
```

**Model** (nguồn tin cậy: GitHub release của nhóm; joblib chạy được mã khi nạp, không dùng file từ nguồn khác):
```bash
curl -LO https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/releases/download/api-model-reference-e571-20261110/realcheck-api-model-e571-20261110-v2.zip
sha256sum realcheck-api-model-e571-20261110-v2.zip   # phải là baf7bd57…be6beea07 như ghi trong release
unzip realcheck-api-model-e571-20261110-v2.zip -d /tmp/e571 && (cd /tmp/e571 && sha256sum -c SHA256SUMS)
mkdir -p models
cp /tmp/e571/model/clip_probe.joblib models/clip_probe_e571.joblib
cp /tmp/e571/model/clip_probe.joblib.sha256 models/clip_probe_e571.joblib.sha256
```

**Trọng số CLIP:** container chạy offline (`HF_HUB_OFFLINE=1`), nên cache phải có sẵn. Chép nguyên thư mục `.cache/huggingface` từ một máy đã tải (giữ cấu trúc `hub/…/blobs`, `snapshots`), ví dụ `rsync -a may-co-cache:/duong-dan/realcheck/.cache/huggingface/ .cache/huggingface/`. Máy có Python và `models/requirements-ml.txt` thì tải được bằng `HF_HOME=.cache/huggingface python -c "from models.clip_input import load_encoder; load_encoder()"`. Container chạy bằng uid 10001, nên file trong `models/` và cache phải cho phép đọc.

**Cấu hình và khởi động:**
```bash
cp .env.example .env
sed -i "s/^REALCHECK_TAG=.*/REALCHECK_TAG=$(git rev-parse --short HEAD)/" .env
mkdir -p artifacts
docker compose build
docker compose up -d
```

## 4. Kiểm tra sau khi khởi động

API nạp model mất khoảng 15–20 giây; trong lúc đó gateway trả 502 `API_UNAVAILABLE`.

```bash
docker compose ps                            # api (healthy), ui (healthy), nginx (Up)
curl -s http://localhost/health              # {"status":"ok","model_ready":true}
docker compose logs api | grep model_        # model_loaded kèm duration_ms
```

Từ **một máy khác** trong mạng lab (thay `<lab>` bằng địa chỉ máy lab):
```bash
curl -s http://<lab>/health
curl -s -o /dev/null -w "%{http_code}\n" http://<lab>/docs
python -m scripts.make_fixtures --out .cache/smoke-fixtures
python -m scripts.smoke_api --base-url http://<lab> --fixtures .cache/smoke-fixtures --delay 0.15 \
    --real <ảnh-thật.jpg> --ai <ảnh-ai.png> --out smoke-lab.json
python -m scripts.check_gateway --base-url http://<lab> --fixture <ảnh.jpg> --rate 10 --burst 10 --upstream prompt --require-retry-after
```
Mở `http://<lab>/` bằng trình duyệt, tải một ảnh JPEG điện thoại và một ảnh PNG, kiểm kết quả và một ảnh lỗi (file text đổi đuôi `.jpg`).

## 5. Mạng và bảo mật

- Chỉ cổng gateway mở ra ngoài; API `8000` và UI `8501` chỉ có trong mạng Compose. Tường lửa máy lab chỉ cho mạng lab vào cổng 80, ví dụ `ufw allow from <subnet-lab> to any port 80`.
- Không TLS (D13: mạng lab hoặc SSH tunnel). Ngoài mạng lab thì dùng tunnel: `ssh -L 8080:localhost:80 <user>@<lab>` rồi mở `http://localhost:8080/`. Mở ra Internet thì phải có TLS, cần quyết định riêng.
- Không có secret trong repo hay `.env`; không commit `.env`.

## 6. Khởi động lại và sự cố

- Mọi service có `restart: unless-stopped`: Docker tự chạy lại container khi nó dừng hoặc khi máy khởi động lại.
- API và UI có healthcheck; API báo `unhealthy` khi `/health` không trả 200 (thiếu model, model sai checksum).
- Mọi `POST /v1/analyze` trả 503 `SERVICE_BUSY` kéo dài, còn `/health` vẫn 200: thread suy luận bị treo (D12). Xử lý: `docker compose restart api`.
- Xem log: `docker compose logs -f api nginx`. Log Nginx và log API cùng `request_id`.

## 7. Cập nhật mã

```bash
git fetch origin
git checkout <commit-mới>
sed -i "s/^REALCHECK_TAG=.*/REALCHECK_TAG=$(git rev-parse --short HEAD)/" .env
docker compose build
docker compose up -d
```
Image của commit cũ vẫn còn với tag cũ, dùng để rollback. Kiểm lại như mục 4 và ghi biên bản.

## 8. Cập nhật model

1. Chép model mới vào `models/` với **tên mới**, kèm `.sha256` cùng tên; không ghi đè file đang dùng.
2. Đổi `REALCHECK_MODEL_FILE` trong `.env`.
3. `docker compose up -d api` (tạo lại container API), rồi kiểm `/health` và log `model_loaded`.

Sai checksum hoặc sai metadata thì API ghi `model_load_failed` và `/health` trả 503; quay lại model cũ như mục 9.

## 9. Rollback

| Quay lại | Cách làm | Thời gian gián đoạn |
|---|---|---|
| Mã và image | `git checkout <commit-cũ>`, đặt `REALCHECK_TAG=<commit-cũ>` trong `.env`, `docker compose up -d --no-build` | Thời gian API nạp lại model, khoảng 20 giây |
| Model | Đặt lại `REALCHECK_MODEL_FILE=<file-cũ>`, `docker compose up -d api` | Như trên |
| Commit cũ hơn bản thêm `REALCHECK_TAG` | Compose cũ dùng tag `latest`: `git checkout <commit-cũ>`, `docker compose up -d --build` (build lại, lớp pip đã cache) | Thêm thời gian build |

Sau rollback kiểm như mục 4 và ghi vào biên bản: commit, tag, model, lý do và thời điểm.

## 10. Thông tin cho biên bản

```bash
git rev-parse HEAD; git status --short                       # commit, có sửa tay không
cat .env
docker image inspect --format '{{.RepoTags}} {{.Id}}' realcheck-api:$(git rev-parse --short HEAD) realcheck-ui:$(git rev-parse --short HEAD) nginx:1.28.0-alpine
sha256sum models/*.joblib && cat models/*.sha256
sha256sum docker-compose.yml nginx/nginx.conf .env
docker compose config | sha256sum                            # cấu hình Compose đã nội suy
nproc; free -h; uname -a; docker version --format '{{.Server.Version}}'
```
