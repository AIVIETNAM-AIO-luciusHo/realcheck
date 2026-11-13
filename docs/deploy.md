# Triển khai core lên máy lab

Phụ trách: Quang. Áp dụng cho Compose core (API, UI Streamlit, gateway Nginx) trong `docker-compose.yml`.

**Trạng thái (2026-11-11):** chưa có máy lab. Hướng dẫn này đã được diễn tập trên máy local, gồm cả rollback và phục hồi ([biên bản diễn tập](reports/deploy-rollback-rehearsal-20261111.md)); chưa có bằng chứng trên server. Khi có máy, điền [mẫu biên bản](deploy-record-template.md).

## 1. Máy lab

| Mục | Yêu cầu |
|---|---|
| Hệ điều hành | Linux x86_64 có Docker Engine và Docker Compose v2, `git`, `curl`, `sha256sum` |
| Ổ đĩa | Khoảng 5 GB: image API 2,3 GB, image UI, cache CLIP 0,6 GB, các image cũ giữ để rollback |
| RAM | Ít nhất 3 GiB cho container (tổng giới hạn bên dưới); API dùng khoảng 400 MiB sau khi nạp model, đỉnh 609 MiB với ảnh 23,5 MP (đo local) |
| CPU | Ít nhất 4 nhân: CLIP dùng 4 thread (`torch.set_num_threads(4)`); 1 worker, 1 slot suy luận (D12) |
| Mạng | Chỉ mở cổng gateway (mặc định 80) cho mạng lab hoặc qua SSH tunnel (D13). **`docker compose build` cần ra Internet** (pip tải `torch` từ `download.pytorch.org/whl/cpu` và PyPI); lab không có Internet thì build ở máy khác rồi chuyển image bằng `docker save` / `docker load` (chưa diễn tập, build từ trắng chưa đo) |
| Công cụ khác | `unzip` (mục 3), `rsync` nếu chép cache bằng ví dụ ở mục 3 (diễn tập Linux 2026-11-12 máy đã có sẵn; lab tối giản có thể thiếu) |
| Máy chạy kiểm tra (mục 4) | Python 3 với `httpx`, `Pillow`, `numpy` (các script `scripts.*` import trực tiếp) |

Giới hạn tài nguyên trong `docker-compose.yml` (proposed, chỉnh lại sau benchmark MVP-09):

| Service | `cpus` | `mem_limit` | Đo local (đỉnh) |
|---|---|---|---|
| `api` | 4 | 2 GiB | 609 MiB |
| `ui` | 1 | 512 MiB | 50 MiB |
| `nginx` | 0,5 | 128 MiB | 9 MiB |

Container vượt `mem_limit` bị kill và Docker chạy lại theo `restart: unless-stopped`; kiểm bằng `docker inspect --format '{{.State.OOMKilled}} {{.RestartCount}}' $(docker compose ps -q api)`.

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
grep '^REALCHECK_TAG=' .env                  # sed im lặng nếu .env thiếu dòng này (vd. .env từ bản cũ): phải thấy đúng tag
# tùy chọn, nếu cổng 80 bận: sed -i "s/^REALCHECK_HTTP_PORT=.*/REALCHECK_HTTP_PORT=8080/" .env
mkdir -p artifacts
docker compose build
docker compose up -d
```

## 4. Kiểm tra sau khi khởi động

Nếu đã đổi `REALCHECK_HTTP_PORT` trong `.env` thì mọi URL bên dưới phải kèm cổng (`http://localhost:8080/health`, `http://<lab>:8080/...`, `--base-url http://<lab>:8080`). `scripts.*` chạy từ gốc repo trên máy kiểm tra có Python với `httpx`, `Pillow`, `numpy`, ví dụ `python3 -m venv .venv && . .venv/bin/activate && pip install httpx pillow numpy` (hoặc `pip install -r requirements.txt`, kéo thêm pytest, ruff, pandas, scikit-learn).

API nạp model mất khoảng 10–20 giây (đo local: 11–15 giây; diễn tập Linux 2026-11-12: 7–16 giây khi máy rảnh, tới khoảng 28–40 giây khi máy bận); trong lúc đó gateway trả 502 `API_UNAVAILABLE`, khoảng 1,6 giây mỗi request khi container API đã dừng (`resolver_timeout 1s`; trước đó 4 giây).

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
**`--upstream prompt` cần người chạy tắt và bật API bằng tay, trong terminal có tty.** Khi script nhắc, chạy `docker compose stop api` (không phải `kill`) rồi nhấn Enter; khi script nhắc lần sau, chạy `docker compose start api` rồi nhấn Enter. Không có tty (stdin đóng) thì script không chờ và ca upstream báo lỗi. Đừng dùng `--wait-seconds 8`: `docker compose stop api` mất khoảng 3 giây lúc rảnh nhưng khoảng 28 giây khi đang có tải, nên sau 8 giây API vẫn trả HTTP 200 và ca lỗi. Nếu bắt buộc dùng `--wait-seconds`, đặt từ 40 trở lên và dừng API trước khi script tới bước đó. Phục hồi sau khi bật mất khoảng 10–40 giây.
Mở `http://<lab>/` bằng trình duyệt, tải một ảnh JPEG điện thoại và một ảnh PNG, kiểm kết quả và một ảnh lỗi (file text đổi đuôi `.jpg`).

## 5. Mạng và bảo mật

- Chỉ cổng gateway mở ra ngoài; API `8000` và UI `8501` chỉ có trong mạng Compose. Tường lửa máy lab chỉ cho mạng lab vào cổng 80, ví dụ `ufw allow from <subnet-lab> to any port 80`.
- Không TLS (D13: mạng lab hoặc SSH tunnel). Ngoài mạng lab thì dùng tunnel: `ssh -L 8080:localhost:80 <user>@<lab>` rồi mở `http://localhost:8080/`. Mở ra Internet thì phải có TLS, cần quyết định riêng. Đã xác nhận trong diễn tập Linux 2026-11-12: chỉ cổng gateway lắng nghe (`ss -ltn`), cổng 8000 và 8501 không kết nối được từ địa chỉ IP của máy; gateway phục vụ HTTP thuần. Bước `ufw` chưa kiểm được (WSL2).
- Không có secret trong repo hay `.env`; không commit `.env`.

## 6. Khởi động lại và sự cố

- Mọi service có `restart: unless-stopped`: Docker tự chạy lại container khi nó **dừng** hoặc khi máy khởi động lại.
- API và UI có healthcheck; API báo `unhealthy` khi `/health` không trả 200 (thiếu model, model sai checksum). **Docker Compose không tự khởi động lại container `unhealthy`**: nạp model lỗi thì API vẫn chạy và trả 503 cho tới khi người vận hành sửa.
- Theo dõi: `docker compose ps` hiện `(unhealthy)`; hoặc chạy định kỳ (cron mỗi phút) và báo khi khác `healthy`:
  ```bash
  docker inspect --format '{{.State.Health.Status}}' $(docker compose ps -q api)
  ```
  Docker chỉ đổi sang `unhealthy` sau khoảng 3–4 phút kể từ khi API khởi động (`HEALTHCHECK` có `--start-period=120s`, `--interval=30s`, `--retries=3`; suy ra từ Dockerfile, chưa chờ đủ để quan sát). Trong thời gian đó `docker compose ps` vẫn hiện `health: starting` dù `/health` đã trả 503, nên không chờ `docker compose ps` mà kiểm ngay `curl -s http://localhost/health` (503 `not_ready`) và `docker compose logs api | grep model_`.
  Gặp `unhealthy`: xem `docker compose logs api | grep model_`, sửa model hoặc `.env` theo mục 8, rồi `docker compose up -d api`.
- Mọi `POST /v1/analyze` trả 503 `SERVICE_BUSY` kéo dài, còn `/health` vẫn 200: thread suy luận bị treo (D12). Xử lý: `docker compose restart api`.
- Xem log: `docker compose logs -f api nginx`. Log Nginx và log API cùng `request_id`.

## 7. Cập nhật mã

```bash
git fetch origin
OLD=$(git rev-parse --short HEAD)
git checkout <commit-mới>
sed -i "s/^REALCHECK_TAG=.*/REALCHECK_TAG=$(git rev-parse --short HEAD)/" .env
docker compose build
docker compose up -d
git diff --quiet "$OLD" HEAD -- nginx/nginx.conf || docker compose up -d --no-deps --force-recreate nginx
```
Image của commit cũ vẫn còn với tag cũ, dùng để rollback. Kiểm lại như mục 4 và ghi biên bản.

`docker compose up -d` không tạo lại container Nginx khi chỉ có `nginx/nginx.conf` đổi: file được mount riêng lẻ, `git checkout` thay nó bằng file mới, và container có thể vẫn đọc nội dung cũ. Dòng cuối tạo lại Nginx khi cấu hình đổi giữa hai commit. Lưu ý: khi image `api` hoặc `ui` đổi, `docker compose up -d` đã tạo lại Nginx (do `depends_on`), nên dòng cuối tạo lại lần hai (log hiện `Recreate` hai lần, quan sát khi diễn tập Linux). Vô hại nhưng thêm vài giây ngắt; chỉ cần dòng cuối khi `up -d` không tạo lại Nginx.

## 8. Cập nhật model

1. Chép model mới vào `models/` với **tên mới**, kèm `.sha256` cùng tên; không ghi đè file đang dùng.
2. Đổi `REALCHECK_MODEL_FILE` trong `.env`.
3. `docker compose up -d api` (tạo lại container API), rồi kiểm `/health` và log `model_loaded`.

Sai checksum hoặc sai metadata thì API ghi `model_load_failed` và `/health` trả 503; quay lại model cũ như mục 9.

## 9. Rollback

| Quay lại | Cách làm | Thời gian gián đoạn |
|---|---|---|
| Mã và image | `git checkout <commit-cũ>`, đặt `REALCHECK_TAG=<commit-cũ>` trong `.env`, `docker compose up -d --no-build` | Thời gian API nạp lại model: 11,4 giây khi diễn tập local; 15,5 giây khi diễn tập Linux (gồm cả Nginx tạo lại, trong lúc đó kết nối bị từ chối chứ không phải 502 JSON) |
| Model | Đặt lại `REALCHECK_MODEL_FILE=<file-cũ>`, `docker compose up -d api` | 11,9 giây khi diễn tập local; khoảng 11 giây khi diễn tập Linux |
| Commit cũ hơn bản thêm `REALCHECK_TAG` | Compose cũ dùng tag `latest`: `git checkout <commit-cũ>`, `docker compose up -d --no-build` nếu image `latest` vẫn là bản đó, ngược lại `--build` | Thêm thời gian build nếu phải build. Build commit cũ ghi đè `latest` (image ID đổi khi diễn tập): sau đó muốn quay lại commit mới phải `docker compose build` lại hoặc dùng `--no-build` với `REALCHECK_TAG` đúng |

`nginx/nginx.conf` khác giữa hai commit thì chạy thêm `docker compose up -d --no-deps --force-recreate nginx` (mục 7); thiếu `--no-deps` thì Compose khởi động lại cả API và UI. Trong lúc API nạp lại, gateway trả 502 `API_UNAVAILABLE`. Gián đoạn thực tế khoảng 10–40 giây tùy tải máy (diễn tập Linux 2026-11-12: 15,5 giây cho rollback mã; start API lúc máy bận mất tới 39,5 giây).

Sau rollback kiểm như mục 4 và ghi vào biên bản: commit, tag, model, lý do và thời điểm.

## 10. Thông tin cho biên bản

```bash
git rev-parse HEAD; git status --short                       # commit, có sửa tay không
cat .env
docker image inspect --format '{{.RepoTags}} {{.Id}}' realcheck-api:$(git rev-parse --short HEAD) realcheck-ui:$(git rev-parse --short HEAD) nginx:1.28.0-alpine
F=$(grep '^REALCHECK_MODEL_FILE=' .env | cut -d= -f2); M=models/${F:-clip_probe_e571.joblib}   # model đang dùng (mặc định của docker-compose.yml nếu .env không có dòng này)
sha256sum "$M" && cat "$M.sha256"
sha256sum docker-compose.yml nginx/nginx.conf .env           # .env khác nhau giữa các máy (cổng, tag): không dùng để so sánh
docker compose config | sed "s#$PWD#.#g" | sha256sum        # cấu hình Compose đã nội suy; bỏ đường dẫn tuyệt đối để so sánh được giữa các máy
nproc; free -h; uname -a; docker version --format '{{.Server.Version}}'
```
