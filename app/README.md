# app/ – FastAPI

Phụ trách: Quang

## Làm gì
API nhận 1 ảnh, kiểm tra hợp lệ, gọi `score(image)` từ `models/`, đọc EXIF và trả `verdict`, `score`, `exif`, `reason`.

| File | Chức năng |
|---|---|
| `main.py` | `create_app(scorer, settings, loader)`: tạo app, gắn middleware, lỗi, route; lifespan nạp model |
| `routes.py` | Khai báo endpoint |
| `schemas.py` | Hợp đồng JSON: `verdict`, response, mã lỗi |
| `verdict.py` | Ngưỡng và câu chữ `reason`; không lặp logic này ở nơi khác |
| `errors.py` | Bảng mã lỗi, envelope lỗi dùng chung |
| `inference.py` | `InferenceService`: chạy suy luận trên thread riêng, giới hạn slot và timeout; hàm nạp model thật |
| `uploads.py` | Đọc file có giới hạn, giải mã một lần, đọc EXIF, kiểm tra điểm từ model |
| `settings.py` | Cấu hình đọc từ biến môi trường |
| `logging.py` | `X-Request-ID` và log có cấu trúc |

Endpoint: `POST /v1/analyze`, `GET /health`, `GET /docs`, `GET /openapi.json`. Giai đoạn nâng cao: `GET /metrics`.

## Cách chạy
Từ thư mục gốc repo:
```bash
pip install -r requirements.txt -r models/requirements-ml.txt
uvicorn app.main:app
```
Lúc khởi động, lifespan gọi `models.score.load_scorer` một lần trên worker thread: kiểm checksum, metadata, rồi warmup CLIP. Server chỉ nhận request sau khi nạp xong (Kiệt đo local khoảng 30 giây). Cần `models/clip_probe.joblib` cùng file `.sha256`, hoặc đặt `REALCHECK_MODEL_PATH`, và trọng số CLIP đã cache (xem [`models/README.md`](../models/README.md)).

Thiếu file, sai checksum, sai metadata hoặc thiếu torch: ghi log `model_load_failed`, server vẫn chạy và `/health` trả 503. Không có chế độ model giả, không nạp lại model trong request. Chỉ cài `requirements.txt` thì server luôn ở trạng thái này. Nạp xong ghi log `model_loaded` kèm thời gian.

Test tiêm scorer giả qua `create_app(scorer=...)`, hoặc hàm nạp qua `create_app(loader=...)`; `loader` chỉ chạy khi app đi qua lifespan. `create_app()` không có loader nên không nạp model.

## Chạy bằng Docker
Image chứa API, code trong `models/` và dependency ML (torch bản CPU). **Không** chứa model, dữ liệu hay trọng số CLIP: cả ba mount từ máy chủ lúc chạy, chỉ đọc. Build từ gốc repo:
```bash
docker build -t realcheck-api .
```

Cung cấp model cho container:

| Mount vào | Từ máy chủ | Biến môi trường trong image |
|---|---|---|
| `/models` | Thư mục có `clip_probe.joblib` và `clip_probe.joblib.sha256` (thường là `models/`) | `REALCHECK_MODEL_PATH=/models/clip_probe.joblib` |
| `/hf-cache` | Cache Hugging Face đã tải đúng revision CLIP (thường là `.cache/huggingface`) | `HF_HOME=/hf-cache`, `HF_HUB_OFFLINE=1` |

Container không tải gì từ mạng lúc khởi động, nên trọng số CLIP phải được tải trước trên máy chủ (xem [`models/README.md`](../models/README.md)). Model khác tên thì đặt lại `-e REALCHECK_MODEL_PATH=/models/<tên>.joblib`, file `.sha256` cùng tên phải nằm cạnh.

Chạy (PowerShell; bash thay `${PWD}` bằng `$PWD` và `` ` `` bằng `\`):
```powershell
docker run --rm -p 8000:8000 `
  -v "${PWD}/models:/models:ro" `
  -v "${PWD}/.cache/huggingface:/hf-cache:ro" `
  --name realcheck-api realcheck-api
```
Kiểm tra: `curl http://localhost:8000/health` và mở `http://localhost:8000/docs`.

- Không mount model thì container vẫn chạy, `/docs` trả 200, `/health` trả 503 và log `model_load_failed`. Healthcheck của image báo `unhealthy` trong trường hợp này.
- Healthcheck gọi `/health` mỗi 30 giây, chờ 120 giây lúc khởi động để kịp nạp và warmup CLIP.
- Container chạy bằng user không phải root (uid 10001), nên các file mount phải cho phép đọc.
- **Kiểm tra với model thật hoàn tất ở ticket B3:** nạp `clip_probe.joblib` thật, warmup CLIP từ cache chỉ đọc và chấm điểm ảnh thật trong container chưa được kiểm.

## Giới hạn suy luận, timeout và shutdown
- Mỗi request giữ một slot trong cả lúc giải mã, đọc EXIF và chấm điểm. Hết slot trả 503 `SERVICE_BUSY` ngay, không xếp hàng. `/health` không dùng slot nên vẫn trả lời khi đang bận.
- Quá `REALCHECK_MODEL_TIMEOUT_S` trả 504 `MODEL_TIMEOUT`. Thread không hủy được CLIP, nên slot chỉ nhả khi việc thật sự kết thúc; trong lúc đó request mới nhận 503. Client ngắt kết nối cũng không nhả slot sớm.

| Tầng | Timeout | Nguồn |
|---|---|---|
| API, model | 10 giây (`REALCHECK_MODEL_TIMEOUT_S`) | D11, approved tạm |
| Nginx (`proxy_read_timeout`) | 15 giây | Đề xuất, chờ duyệt cùng D11; Nginx chưa có cấu hình |
| UI Streamlit | 60 giây (`REALCHECK_API_TIMEOUT`) | Mặc định trong `streamlit/api_client.py` |

Mỗi tầng phải dài hơn tầng phía sau. Thời gian khởi động và warmup không tính vào các timeout này.

**Shutdown:** khi server dừng, việc chưa chạy bị hủy, việc đang chạy không bị chờ cũng không bị hủy. Python vẫn chờ thread đang chạy kết thúc trước khi thoát tiến trình.

**Khi thread treo vĩnh viễn:**
- Dấu hiệu: mọi `POST /v1/analyze` trả 503 `SERVICE_BUSY`, trước đó có request 504 trong log, còn `/health` vẫn trả 200.
- Xử lý: restart tiến trình API (`docker compose restart api` khi đã có Compose). Tiến trình không tự thoát được, nên Docker sẽ gửi SIGKILL sau thời gian chờ dừng; chạy tay thì phải kill tiến trình.
- Đây là giới hạn đã biết của D12, có test `xfail` trong `tests/test_inference.py`. Không có cơ chế tự phát hiện hay tự restart.

## Cấu hình
Biến môi trường, giá trị mặc định xem `settings.py`. Lý do chọn: [`docs/decisions/realcheck-baseline.md`](../docs/decisions/realcheck-baseline.md).

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `REALCHECK_MAX_FILE_BYTES` | 5242880 | Dung lượng file tối đa |
| `REALCHECK_MAX_PIXELS` | 24000000 | Số pixel tối đa |
| `REALCHECK_MAX_SIDE` | 10000 | Cạnh tối đa |
| `REALCHECK_MODEL_TIMEOUT_S` | 10 | Timeout suy luận (giây) |
| `REALCHECK_INFERENCE_SLOTS` | 1 | Số ảnh xử lý đồng thời |
| `REALCHECK_THRESHOLD_LOW` | 0.3 | Dưới ngưỡng này là `likely_real` |
| `REALCHECK_THRESHOLD_HIGH` | 0.7 | Trên ngưỡng này là `likely_ai` |
| `REALCHECK_MODEL_PATH` | `models/clip_probe.joblib` | File model; cần file `.sha256` cùng tên bên cạnh |

## Input / Output
- Input: `multipart/form-data`, đúng một file ở trường `file`. Chỉ nhận JPEG hoặc PNG một khung hình, xác định theo nội dung file, không theo đuôi. Tối đa 5.242.880 byte, 24 MP, cạnh dài 10.000 px; cạnh ngắn tối thiểu 256 px.
- Output: JSON `{verdict, score, exif, reason}`; `verdict` là `likely_real`, `uncertain` hoặc `likely_ai`, ngưỡng 0.3 / 0.7.
- `exif` chỉ gồm hãng và model máy; thiếu thì trả `Không có thông tin máy chụp`.
- Lỗi trả envelope `{"error": {code, message, request_id}}`, bảng mã xem D05 trong [`docs/decisions/realcheck-baseline.md`](../docs/decisions/realcheck-baseline.md).

```bash
curl -F "file=@anh.jpg" http://localhost:8000/v1/analyze
```

## Lưu ý và giả định
- Độ bao phủ test của `app/` từ 70% trở lên.
- Đổi schema response phải sửa tài liệu trong cùng PR.
