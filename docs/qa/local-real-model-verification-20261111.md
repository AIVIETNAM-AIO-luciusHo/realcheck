# Kiểm hệ thống với model thật trên Linux (11/11/2026)

Liên quan: KAN-29 (smoke localhost), KAN-54 (gateway), KAN-56 (baseline tải), KAN-24/23 (Docker, model thật); GitHub #39, #40, #41. Người kiểm: QA (Lực) qua Tester độc lập. Đây là bằng chứng **cục bộ**, chưa phải nghiệm thu core: chưa chạy trên server lab, chưa có TLS, chưa ký SLO.

## Môi trường và đầu vào

| Mục | Giá trị |
|---|---|
| Code | `origin/main` tại `fa01cbc` (đã có #69 đến #73) cộng PR #75 (cục bộ); đo test đầy đủ tại `7cb0f2b` |
| Máy | Linux (WSL2), 12 CPU, 11,8 GB RAM, Python 3.12.3, Docker Engine 29.x |
| Model | reference e571, SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494` (release `api-model-reference-e571-20261110`) |
| CLIP | `sentence-transformers/clip-ViT-B-32`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`, chạy offline (`HF_HUB_OFFLINE=1`) |
| Ảnh | **Ảnh tổng hợp** sinh bằng `scripts.make_fixtures` và Pillow. Không có ảnh GenImage trên máy kiểm. |

## Kết quả

| Kiểm tra | Kết quả |
|---|---|
| ZIP và model SHA256 khớp release; `sha256sum -c` OK | Đạt |
| Sửa 1 byte model | Bị từ chối (`Model checksum mismatch`) trước khi nạp CLIP |
| CLI `models.score` so với `POST /v1/analyze` (4 ảnh) | Đạt, lệch tối đa 5e-9 |
| `/health` | 200, `model_ready=true`, khoảng 10 giây (uvicorn), 16 đến 27 giây (container) |
| Không đặt `REALCHECK_MODEL_PATH` | `/health` 503 `model_ready=false`, log `model_load_failed`, API không crash |
| `python -m scripts.smoke_api` gọi thẳng API | **26 ca, 0 lỗi, 0 cảnh báo, thoát 0** (uvicorn và container) |
| Docker theo `app/README.md` (cache và model mount `:ro`) | Đạt: healthcheck healthy, RAM 420 đến 436 MiB, `docker stop` thoát 0 sau 2,3 giây, điểm khớp API từng chữ số |
| Compose (`docker compose up`, PR #71) | `/health` qua Nginx 200 sau khoảng 16 đến 32 giây; chỉ Nginx publish cổng, 8000 và 8501 không truy cập được từ máy chủ |
| `python -m scripts.check_gateway --rate 10 --burst 10 --upstream prompt --require-retry-after` | **8/8 đạt, thoát 0** (429 là 38/50 khi gửi dồn); phục hồi sau khi bật lại API 9,2 giây |
| 413 qua Nginx (body 6 MiB) | JSON `FILE_TOO_LARGE`, `X-Request-ID` khớp header và body |
| Header | `Server: nginx` không có số phiên bản, không có `X-Powered-By` |
| `pause api` / `stop api` | 504 `GATEWAY_TIMEOUT` sau 15,07 giây rồi 200; 502 `API_UNAVAILABLE` |
| WebSocket `/_stcore/stream` | `101 Switching Protocols` |

## Baseline Locust sơ bộ (KAN-56), không dùng để ký SLO

`baseline.conf`, 5 người dùng, 120 giây sau 30 giây làm nóng, qua Nginx từ cùng máy, `inference_slots=1`, 8 ảnh tổng hợp, chỉ tính phản hồi 200, chạy hai lần.

| | Lần 1 | Lần 2 |
|---|---|---|
| p50 / p95 / p99 (ms) | 121,7 / 364,1 / 963,3 | 121,4 / 344,9 / 657,5 |
| Request 200 mỗi giây | 1,75 | 1,77 |
| 503 `SERVICE_BUSY` | 21,9% | 21,2% |
| 429 | 0% | 0% |
| RAM API (MiB) | 439 đến 537 | 439 |

`rate_only` (25 người dùng, 30 giây): 98,3% là 429. `check_performance` thoát 2 vì repo cố ý chưa có `slo.json`.

## Phát hiện trong lúc kiểm (đã xử lý)

| Phát hiện | Xử lý |
|---|---|
| Ca rate limit của `check_gateway` đỏ vì API trả 503 `SERVICE_BUSY` (D12) | PR #73 |
| Ca "GET đường dẫn lạ" của `smoke_api` trả 200 qua Nginx vì gốc `/` thuộc Streamlit | PR #75 |
| `smoke_api` qua Nginx bị 429 vì gửi 26 request liên tục | PR #77 (`--delay 0.15`) |
| `tests/test_docker_static.py` lỗi trên Windows (đọc file bằng cp1252) | PR #68 |

## Diễn tập M1 (demo localhost, không Nginx)

Tester chạy `uvicorn` và Streamlit trên Linux theo runbook, model e571, ảnh tổng hợp và `flower.jpg`: `/health` và `/docs` 200, smoke 26 ca đạt, UI lái bằng `AppTest` cho kết quả sau 0,18 đến 0,27 giây, ảnh có EXIF hiện đúng, text đổi đuôi `.jpg` trả 400, ảnh dưới 256 px trả 422, API tắt thì UI báo "Không kết nối được tới hệ thống" không crash. Khởi động API 8,6 giây khi cache đĩa nóng, **72,7 giây khi cache lạnh**; request đầu 1,4 giây. Cả 11 ảnh hợp lệ thử đều ra "Ảnh AI" (0,708 đến 0,999), không ảnh nào vào vùng "Chưa chắc": chỉ ghi nhận, không phải đo độ chính xác.

## Trạng thái gate nghiệm thu (`check_mvp_gates`)

Chạy `python -m scripts.check_mvp_gates` trên `main`: **9 gate đều "thiếu bằng chứng"**, chưa gate nào đạt. G01 cần `unit.xml` và `coverage.xml` sinh từ một lần chạy pytest không skip (cần cài Locust); G02 và G03 có số liệu (A\_eff 0,5 và 94,53%/384 ảnh) nhưng đều kèm giới hạn đã nêu trong báo cáo nên không nên coi là đạt tự động; G04 và G05 cần bộ test JUnit chạy qua Nginx và qua UI (chưa có trong repo); G06 đến G09 cần SLO đã ký và số đo chính thức trên server lab.

## Giới hạn

- Ảnh tổng hợp: điểm và verdict **không** nói gì về độ chính xác. Không so được điểm với số Quang đo trên ảnh thật (4 ảnh từ `data/raw`, có thể thuộc tập train).
- Một máy, tải chạy cùng máy, có tiến trình khác chạy đồng thời (load trung bình 2,5 đến 4): số Locust chỉ để tham khảo.
- Một lần chạy toàn bộ test (đồng thời với việc khác trên cùng máy) có một ca `test_api_khong_resize_anh_4000x3000` trả 504 `MODEL_TIMEOUT`; chạy riêng 3 lần và 6 lần khi ép một CPU đều đạt (0,1 đến 0,3 giây). Có thể là chập chờn khi máy bị chiếm hết CPU; chưa điều tra thêm.
- Chưa kiểm UI bằng trình duyệt qua Nginx, chưa chạy stress, recovery, soak, chưa chạy trên server lab, chưa TLS.
- Khi dừng API, mỗi request qua Nginx chờ 4 đến 5,5 giây trước khi nhận 502 (Nginx không phân giải được tên `api`). Một lần sau pause rồi stop trả 504 thay vì 502, không lặp lại trong 3 lần sau.
- `smoke_api` qua Nginx cần `--delay 0.15` (rate limit 10 r/s, burst 10).
