# nginx/ – Gateway và Compose core

Phụ trách: Quang

## Làm gì
`nginx.conf` là cổng public duy nhất của stack `docker-compose.yml` ở gốc repo: route API trước UI, giới hạn body và tốc độ, trả lỗi theo envelope D05. API (`:8000`) và UI (`:8501`) chỉ có cổng nội bộ trong mạng Compose.

| Đường dẫn | Tới | Ghi chú |
|---|---|---|
| `/v1/` | API | Rate limit, timeout 15 giây |
| `/health`, `/docs`, `/openapi.json` | API | Không rate limit |
| `/_stcore/stream` | UI | WebSocket của Streamlit |
| `/` | UI | Còn lại |

UI gọi API qua gateway (`REALCHECK_API_URL=http://nginx`), không gọi thẳng container API và không import `models/`.

## Cách chạy
Từ gốc repo:

1. Cấp model và trọng số CLIP như mục "Model đang dùng" của [`app/README.md`](../app/README.md): `models/clip_probe_e571.joblib` và `.sha256` đã khớp checksum release, cache CLIP ở `.cache/huggingface`. Model khác thì đặt `REALCHECK_MODEL_FILE=<tên file trong models/>`.
2. Chạy:
   ```bash
   docker compose up -d --build
   ```
3. Đợi API nạp model (khoảng 20 giây), rồi kiểm tra:
   ```bash
   curl http://localhost/health        # 200 {"status":"ok","model_ready":true}
   curl -F "file=@anh.jpg" http://localhost/v1/analyze
   ```
   Mở `http://localhost/` cho UI và `http://localhost/docs` cho Swagger.

Cổng 80 bận thì đặt `REALCHECK_HTTP_PORT=8080`. Trong lúc API còn nạp model, `/v1/` và `/health` trả 502 `API_UNAVAILABLE`.

Kiểm cấu hình và gateway:
```bash
docker compose config --quiet
docker run --rm -v "$PWD/nginx/nginx.conf:/etc/nginx/nginx.conf:ro" nginx:1.28.0-alpine nginx -t
python -m scripts.check_gateway --base-url http://localhost --fixture <ảnh.jpg> --rate 10 --burst 10 --upstream prompt --require-retry-after
```

## Giới hạn và lỗi
Giá trị đánh dấu "proposed" chờ Lực duyệt trong [`docs/decisions/realcheck-baseline.md`](../docs/decisions/realcheck-baseline.md); đổi thì sửa `nginx.conf`, sổ quyết định và README này cùng lúc.

| Mục | Giá trị | Quyết định |
|---|---|---|
| File tối đa (API kiểm) | 5.242.880 byte | D06, approved |
| Body tối đa (Nginx, `client_max_body_size`) | 5184k = 5.308.416 byte | D06 body dư 64 KiB, proposed |
| Rate limit `/v1/` | 10 request/giây theo IP kết nối, `burst=10 nodelay` | D13, proposed |
| Timeout model (API) | 10 giây | D11, approved tạm |
| Timeout gateway `/v1/` | 15 giây (`proxy_read_timeout`) | D11, proposed |
| Timeout UI | 60 giây (`REALCHECK_API_TIMEOUT`) | Mặc định của UI |

Lỗi do chính Nginx tạo, cùng envelope `{"error":{code,message,request_id}}` và header `X-Request-ID`, không trả trang HTML:

| HTTP | `code` | Khi nào |
|---|---|---|
| 413 | `FILE_TOO_LARGE` | Body vượt 5184k |
| 429 | `RATE_LIMITED` | Vượt rate limit; kèm `Retry-After: 1` |
| 502 | `API_UNAVAILABLE` | API không chạy, đang khởi động hoặc từ chối kết nối |
| 504 | `GATEWAY_TIMEOUT` | API không trả lời trong 15 giây |

Lỗi của API (kể cả 413 `FILE_TOO_LARGE`, 503 `SERVICE_BUSY`, 504 `MODEL_TIMEOUT`) đi qua nguyên vẹn.

## Lưu ý và giả định
- **Chung IP:** rate limit tính theo IP kết nối (`$binary_remote_addr`), không tin `X-Forwarded-For` client gửi. Mọi phiên UI gọi API từ cùng container Streamlit, nên **dùng chung 10 request/giây**; không phải giới hạn theo từng trình duyệt.
- **Request ID:** client gửi UUID hợp lệ thì giữ nguyên, ngược lại Nginx tạo mới; API nhận cùng ID, nên log Nginx và log API khớp nhau.
- **Gửi dồn:** burst cho khoảng 11 request đi qua cùng lúc, nhưng API chỉ có 1 slot (D12), nên phần dư nhận 503 `SERVICE_BUSY` từ API. Đây là hành vi đúng, không phải lỗi gateway.
- **API khởi động lại:** Nginx phân giải lại tên `api` mỗi 10 giây, nên container API đổi IP vẫn tới được, không cần khởi động lại Nginx.
- Không TLS, chỉ dùng trong mạng lab hoặc qua SSH tunnel (D13). Không có Prometheus hay Grafana trong phạm vi MVP.
