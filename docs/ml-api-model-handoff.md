# Bàn giao model cho API — GitHub #39

## Model tham chiếu được giữ cho API local/lab

Giữ GenImage reference SHA256 **`e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494`**, đóng gói dưới tên **`model/clip_probe.joblib`**. Đây là lựa chọn đã được profile API local tham chiếu trước lượt mở rộng dữ liệu; không đổi weights hoặc nâng candidate mới thành bản phục vụ.

Mixed candidate SHA `26b8882963b9224eb72d2010b46dd390dbd3545173c40c4e452908fbd596c28d` được giữ riêng: cải thiện Reddit nhưng giảm GenImage validation/core. Xem [so sánh](ml-data-expansion-20261110.md). Việc giữ reference không có nghĩa model đã tổng quát tốt trên mọi ảnh web hoặc đã được QA/release duyệt.

**Phần kỹ thuật đã chuẩn bị đủ:** model, sidecar checksum, manifest, dependency pins, hướng dẫn chạy và kiểm HTTP với model thật. **Phía nhận chưa xác nhận nhận/chạy trên máy đích.** Không tự ghi người nhận đã nghiệm thu hoặc tự đóng issue thay họ. QA sản phẩm/release là trạng thái riêng, không phải lý do phải train lại trước khi đóng gói bàn giao.

## Gói giao phía API

File local trong workspace gốc:

```text
outputs/api-model-handoff-20261110/realcheck-api-model-e571-20261110.zip
outputs/api-model-handoff-20261110/realcheck-api-model-e571-20261110.zip.sha256
```

ZIP có **19.872 byte**, SHA256 **`c2fdd5139c1927af93ad60c0f6f99a780b3e52028d7166c57f6f1c78d49c0adb`**. Đã kiểm CRC archive và SHA256 từng file theo manifest. ZIP/weights không nằm trong Git; chuyển gói này cho người phụ trách API qua kênh bàn giao của nhóm. Bản ghi công bố không có đường dẫn máy cá nhân: [evidence](reports/ml-api-handoff-20261110.json).

Nội dung gồm:

- `model/clip_probe.joblib` và `model/clip_probe.joblib.sha256`.
- `manifest.json`: danh tính model, CLIP revision, ngưỡng, training commit, trạng thái thử nghiệm và hash các file.
- `requirements.txt`, `requirements-ml.txt`, `README.md` hướng dẫn nạp/chạy.
- `evaluation-reference.json`, `comparison-mixed-candidate.json`, `api-smoke.json` làm bằng chứng chọn reference và tích hợp.

Probe được train tại commit sạch `4a87e4ac3f14d34e0501303d47e25a02828363ce`; đổi tên file không đổi nội dung/hash. File này chỉ chứa probe + metadata, **không chứa trọng số CLIP**. Phía API cần cache đúng `sentence-transformers/clip-ViT-B-32`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f` và dependency ML đã ghim.

## Cách nạp trên code API đã đồng bộ

Từ checkout nhánh ML đã đồng bộ main, giải nén gói vào `artifacts/api-reference/` rồi chạy PowerShell:

```powershell
python -m pip install -r requirements.txt -r models/requirements-ml.txt
$env:HF_HOME = '.cache/huggingface'
# Nếu cache chưa có, tải CLIP đúng revision một lần khi được phép truy cập mạng:
python -c "from models.clip_input import load_encoder; load_encoder()"

$env:REALCHECK_MODEL_PATH = (Resolve-Path artifacts/api-reference/model/clip_probe.joblib).Path
$env:REALCHECK_THRESHOLD_LOW = '0.3'
$env:REALCHECK_THRESHOLD_HIGH = '0.7'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Đặt đường dẫn model **tường minh**: file mặc định cũ ở `models/clip_probe.joblib` có SHA `69810fd6…ae7bdb`, khác reference bàn giao. Không ghi đè âm thầm hoặc nhầm candidate mới với reference. Loader kiểm sidecar/profile trước nạp CLIP; chỉ nhận joblib từ nguồn nhóm tin cậy, checksum không tự xác thực tác giả.

`score()` nhận PIL ảnh gốc đã giải mã, chuẩn hóa version 1 đúng một lần, trả số hữu hạn `[0,1]`. API nhận JPEG/PNG gốc tại multipart field `file`; không resize/nén thêm trước scorer. Ngưỡng binary 0.5 dùng cho metrics; API low/high 0.3/0.7, gồm hai biên trong vùng Chưa chắc. Các ngưỡng này chưa phải xác suất đã hiệu chuẩn hay phê duyệt release.

## Kiểm chứng thực tế ngày 10/11/2026

Dùng `TestClient` với loader/CLIP/probe thật trên API code commit **`d5fd941ac70ca843e2131952ed744bb308723971`**, không dùng scorer giả. Các file Python API/ML được đối chiếu với commit trước chạy.

| Kiểm tra | Kết quả |
|---|---|
| Nạp model + warmup trong lifespan | Loader gọi đúng 1 lần; encoder frozen/eval |
| `GET /health` sau nạp | HTTP 200, `model_ready=true`; health không chạy inference |
| `POST /v1/analyze`, một validation mỗi nguồn real/SD1.4/GLIDE/Midjourney | **4/4 HTTP 200** |
| Score trực tiếp so với HTTP | Sai khác lớn nhất **0**, tolerance `1e-5` |
| Upload bytes không phải ảnh | HTTP 400 `INVALID_IMAGE`, **0 lần gọi model** |
| Model nguồn và model mặc định cũ | Giữ nguyên hash, không ghi đè |

Đây là kiểm tích hợp local trong process, chưa phải chạy trên máy Quang/lab, server thật, Docker/Linux hoặc benchmark tải. Chỉ dùng validation, không chấm lại GenImage test/holdout đã mở. Code trước lượt bổ sung tài liệu này đã qua 650 tests, app coverage 98,52%; lượt bàn giao không thay logic Python hoặc Backend.

## Xác nhận của bên nhận để đóng vòng bàn giao

Người phụ trách API kiểm SHA gói/model, cache/dependencies, `/health` và một lượt `/v1/analyze` trên máy đích rồi xác nhận model SHA đang dùng. Khi có xác nhận thật mới ghi receiver acceptance và đóng issue bàn giao theo quy trình nhóm. Không cần gộp việc đó với tuyên bố QA chất lượng hoặc production release approved; các gate ấy vẫn được theo dõi riêng.
