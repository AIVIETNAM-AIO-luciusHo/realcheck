# Biên bản deploy máy lab: <ngày>

Người deploy: <tên>. Người kiểm độc lập: <tên>. Lệnh lấy thông tin: [`deploy.md` mục 10](deploy.md#10-thông-tin-cho-biên-bản).

## Máy và truy cập

| Mục | Giá trị |
|---|---|
| URL gateway | `http://<địa chỉ>:<cổng>` |
| Cách truy cập | Mạng lab / SSH tunnel |
| CPU (model, số nhân `nproc`) | |
| RAM (`free -h`) | |
| OS, kernel (`uname -a`) | |
| Docker Engine, Compose | |
| Cổng mở ra ngoài | Chỉ cổng gateway |

## Phiên bản

| Mục | Giá trị |
|---|---|
| Commit | |
| `git status --short` | Trống (không sửa tay) |
| `REALCHECK_TAG` | |
| Image ID `realcheck-api` | |
| Image ID `realcheck-ui` | |
| Image ID `nginx:1.28.0-alpine` | |
| `REALCHECK_MODEL_FILE`, SHA256 model | |
| SHA256 `docker-compose.yml`, `nginx/nginx.conf`, `.env` | |
| SHA256 `docker compose config` | |

## Cấu hình chạy

| Mục | Giá trị |
|---|---|
| Worker, slot suy luận | 1 worker, `REALCHECK_INFERENCE_SLOTS=1` |
| Thread CLIP | 4 |
| Timeout model / gateway / UI | 10 s / 15 s / 60 s |
| Rate limit | 10 r/s, burst 10 nodelay |
| Giới hạn CPU/RAM container | api 4 CPU / 2 GiB, ui 1 / 512 MiB, nginx 0,5 / 128 MiB (proposed) |
| RAM đỉnh đo trên máy lab (`docker stats`) | |

## Kiểm từ máy khác

Máy kiểm: <tên, OS>. Ghi lệnh và kết quả thật.

| Kiểm | Kết quả |
|---|---|
| `GET /health` | |
| `GET /docs` | |
| `scripts.smoke_api` với model thật | |
| `scripts.check_gateway` | |
| UI: ảnh JPEG điện thoại, ảnh PNG, file lỗi, WebSocket | |

## Rollback

| Bước | Thời điểm | Commit / tag / model | Kết quả |
|---|---|---|---|
| Deploy | | | |
| Rollback | | | |
| Phục hồi | | | |

Log: <đường dẫn file log đính kèm>.
