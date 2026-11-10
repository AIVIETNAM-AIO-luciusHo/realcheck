# locust/ – Đo tải

Phụ trách: Lực

## Làm gì
Các kịch bản tách riêng, cho `POST /v1/analyze` qua cổng gateway:

- **baseline** (`baseline.conf`): rate thấp, đo p95/RPS của request 200 đúng schema.
- **rate-only** (`rate_only.conf`, file này ghim `rc-scenario = rate_only`): wait=0, một IP, chỉ quan sát 10 r/s/IP và 429. Không dùng số này công bố năng lực suy luận.

- **stress** (`stress.conf`, bậc đầu 10 user), **recovery** (`recovery.conf`, 1 user), **soak** (`soak.conf`, 5 user, không có thời lượng mặc định: bắt buộc `-t <thời lượng>`, D14 chưa chốt 30/60/120 phút). Số user/spawn là profile A đề xuất ở tasks.md T031, chờ D14. Stress nhiều bậc: chạy lại với `-u 25 -r 5` rồi `-u 50 -r 5`, mỗi bậc một `RC_SIDECAR`. Wait của chúng theo `RC_WAIT_MIN/MAX` như baseline.

Locust không tự kết luận đạt/không đạt: lấy ngưỡng từ SLO đã duyệt bằng `python -m scripts.check_performance --scope load|soak|recovery` (soak cần `--rss`). Chưa có SLO duyệt thì chỉ là baseline. Stress không có ngưỡng số trong spec nên không có scope chấm. Không có Prometheus/Grafana.

## Cách chạy
```bash
pip install -r locust/requirements.txt          # từ máy đo, không phải server
RC_PAYLOAD_DIR=/đường/dẫn/payloads RC_SIDECAR=artifacts/run1.jsonl \
RC_COMMIT=<sha> RC_IMAGE=<digest> RC_MODEL=<hash> RC_PROFILE=<hash> RC_CONFIG_HASH=<hash> \
RC_CLIENT="<cpu/ram>" RC_SERVER="<cpu/ram>" \
  locust --config locust/baseline.conf --host http://<gateway>
python -m scripts.perf_report artifacts/run1.jsonl --warmup-seconds 30
python -m scripts.check_performance --sidecar artifacts/run1.jsonl --slo docs/performance/slo.json
```
`RC_PAYLOAD_DIR` có các thư mục con (ví dụ `jpeg/`, `png/`, `phone/`) chứa ảnh `.jpg/.png` thật, raw. Locustfile gửi nguyên byte, không resize, không model stub. Locust CLI (`-u -r -t`) ghi đè file conf.

## Tham số
| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RC_PAYLOAD_DIR` | `payloads` | Thư mục payload |
| `RC_MIX` | đều giữa các thư mục | Trọng số theo tên thư mục con, ví dụ `jpeg=40,png=30,phone=30` |
| `RC_WAIT_MIN`/`RC_WAIT_MAX` | 1 / 3 | Think time (giây), dùng `wait_time` của Locust |
| `RC_WARMUP_SECONDS`/`RC_WARMUP_REQUESTS` | 0 / 0 | Ghi vào meta; parser bỏ phần warmup khỏi số đo (cờ `--warmup-*` ghi đè) |
| `RC_SIDECAR` | `sidecar.jsonl` | File JSONL đầu ra |
| `RC_COMMIT`, `RC_IMAGE`, `RC_MODEL`, `RC_PROFILE`, `RC_CONFIG_HASH`, `RC_CLIENT`, `RC_SERVER` | không | Ghi vào meta nếu có; không khai thì báo cáo ghi "thiếu" |

Kịch bản chọn bằng tham số Locust `--rc-scenario baseline|rate_only|stress|recovery|soak` (mặc định `baseline`), không dùng biến môi trường: mỗi file conf ghim sẵn kịch bản của nó, nên chạy `--config locust/rate_only.conf` luôn ra wait=0 và meta `scenario: rate_only`; không có cách quên đặt biến. Chạy tay không dùng conf mà muốn rate-only thì phải truyền `--rc-scenario rate_only`.

Users/spawn/thời lượng: `baseline.conf` mặc định **5 user, spawn 1/s, 5 phút**. Đây là **đề xuất, chờ D14**; spec 000 (plan mục 10) để D14 chọn profile A/B và mix payload (khảo sát 40/30/30 hoặc 50/25/25), chưa chốt. Không tự coi các số này là quyết định.

## Input / Output
- Input: URL gateway, payload thật, biến môi trường trên.
- Output: sidecar JSONL. Dòng `meta` đầu, sau đó mỗi request một dòng: `t` (epoch bắt đầu), `outcome` (`200`, `invalid200`, `429`, `503`, `504`, `5xx`, `other`), `status`, `error_code` (envelope), `latency_ms`, `payload`. CSV tổng của Locust không dùng để tính p95 riêng 200.

## Lưu ý và giới hạn
- Chạy từ máy khác, không trên chính server; không giả `X-Forwarded-For` để né limiter.
- Response 200 sai schema hoặc score ngoài [0,1]/không hữu hạn là failure (`invalid200`).
- 429/503/504 không bao giờ tính vào RPS thành công.
- Số đo chỉ là baseline cho tới khi nhóm ký SLO sau MVP-10.
- Chưa chạy thật với `/v1/analyze` (chưa có server); chỉ kiểm bằng mock HTTP tạm, mock không phải số đo.
- Schema SLO và cách điền: xem [`docs/performance/README.md`](../docs/performance/README.md). Sidecar phải có meta `scenario` khớp scope (load=baseline, soak, recovery), nếu không `check_performance` thoát 2. Chưa có percentile toàn traffic.
- Sidecar có latency âm hoặc `--warmup-*` âm bị từ chối (thoát 2).
- `RC_MIX` sai (nhóm lạ, trọng số âm/không hữu hạn, tổng bằng 0) làm Locust thoát với thông báo `RC_MIX`. Meta `wait` ghi đúng wait thật (rate_only là `[0, 0]`). Mốc `t` là `time.time()`; latency không gồm đọc file payload.
- Test liên quan locustfile (`test_locustfile_voi_locust_that`, `test_locust_kich_ban_moi_va_soak_can_run_time`) tự bỏ qua khi máy không có locust (CI nhẹ); cài `pip install -r locust/requirements.txt` để chạy.
