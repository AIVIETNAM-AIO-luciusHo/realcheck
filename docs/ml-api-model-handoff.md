# Bàn giao model cho API — GitHub #39

## Lựa chọn model

Kiệt chọn **GenImage giữ split, SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494`**, đóng gói thành `model/clip_probe.joblib`, cho cấu hình API local/lab. Đây là reference đã được dùng trong profile API. Model mặc định cũ `69810fd60940ddeed07af92d600c6bb0466641bf4144aec73554b44013ae7bdb` không được chọn cho gói này; phải đặt `REALCHECK_MODEL_PATH` tường minh.

Không chọn mixed candidate `26b88829…` hoặc bản fit tái lập `7164eeca…`: candidate giảm accuracy trên GenImage validation (97,24% → 86,45%, N=871) và mẫu OpenFake core/test (84,13% → 80,38%, N=1.040). Thí nghiệm mở rộng dữ liệu nằm riêng ở [PR B #61](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/pull/61). PR tài liệu này độc lập với PR B, không sửa mã `models/`, API, chuẩn hóa hoặc weights.

Lựa chọn reference local/lab **không phải phê duyệt chất lượng hay production release**. GenImage test 94,53% là số lịch sử trên **384 ảnh đã lọc**, chỉ 65 real và 19 SD1.4; không đại diện mọi ảnh web/điện thoại, chưa QA độc lập và chưa loại trừ shortcut JPEG, dung lượng, metadata, nội dung. Không chấm lại test trong lượt bàn giao.

## Nơi lấy artifact

[GitHub prerelease bàn giao e571](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/releases/tag/api-model-reference-e571-20261110) cung cấp ZIP, checksum ZIP, model và sidecar. Git chỉ chứa tài liệu/report; weights và dữ liệu không commit vào nhánh.

| Artifact | Giá trị |
|---|---|
| ZIP | `realcheck-api-model-e571-20261110-v2.zip`, 24.132 byte |
| SHA256 ZIP | `baf7bd5772bb2146c07ed0189413d99a26c170ee1cfdcd1747be55a1e6beea07` |
| Model trong ZIP | `model/clip_probe.joblib` + sidecar raw hash |
| Kiểm nội bộ | CRC archive và SHA256 từng file theo manifest khớp |
| Evidence công bố | [reports/ml-api-handoff-20261110.json](reports/ml-api-handoff-20261110.json) |

Gói có requirements, manifest, báo cáo reference/candidate, kiểm API/CLI, quan sát D02 và script đo từng bước offline. CLIP weights **không nằm trong ZIP**. `joblib` chỉ được nạp từ nguồn dự án tin cậy; checksum không tự chứng minh tác giả.

## Provenance và dependencies

| Mục | Giá trị |
|---|---|
| Commit train reference | `4a87e4ac3f14d34e0501303d47e25a02828363ce`, `dirty=false` |
| Seed, C | 42, 10 |
| Manifest labels | `4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad` |
| Features | `1a08a1005c3ea3f6daf2172f944b97d51a6d3d33f73ec812558840d2cedfa217` |
| Python train | 3.12.14 |
| torch / transformers / sentence-transformers | 2.15.0 / 5.22.1 / 6.2.0 |
| Pillow / scikit-learn / joblib | 13.0.0 / 1.9.1 / 1.6.0 |
| CLIP | `sentence-transformers/clip-ViT-B-32` |
| CLIP revision | `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f` |
| Normalization | Version `1` |

Nguồn số đo/train cũ: [ml-final-experiment.md](ml-final-experiment.md), [JSON](reports/ml-final-experiment.json). Không gán provenance dirty của mixed candidate cho reference này, hoặc sửa lịch sử thí nghiệm mixed thành clean.

Cache HF cần mount: **thư mục gốc host `.cache/huggingface` → `/hf-cache` trong container**, đặt `HF_HOME=/hf-cache`. Giữ nguyên cây `hub/`, blobs và liên kết snapshots; snapshot cần có là `hub/models--sentence-transformers--clip-ViT-B-32/snapshots/327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`. Không mount riêng snapshot thành `HF_HOME`. Đây là cấu hình đề nghị cho môi trường đích; lượt này chưa chạy Docker Python 3.11 trên Linux.

## Kiểm checksum và chạy lại

Giải nén ZIP vào `artifacts/api-reference/`. Từ thư mục gói, Bash:

```bash
sha256sum -c SHA256SUMS
# Lệnh đúng tên trong issue #39, chạy ở thư mục verification:
cd verification
sha256sum -c clip_probe.joblib.sha256
cd ..
```

Hai format checksum có chủ đích: `model/clip_probe.joblib.sha256` **chỉ có hash** vì loader hiện tại yêu cầu như vậy; `SHA256SUMS` và `verification/clip_probe.joblib.sha256` có hash + tên file cho GNU. Không thay runtime sidecar bằng GNU manifest.

Từ repo main hoặc nhánh PR A, PowerShell:

```powershell
python -m pip install -r requirements.txt -r models/requirements-ml.txt
$env:HF_HOME = '.cache/huggingface'
# Nếu cache trống, tải đúng revision một lần khi có mạng, trước khi bật offline:
python -c "from models.clip_input import load_encoder; load_encoder()"
$env:REALCHECK_MODEL_PATH = (Resolve-Path artifacts/api-reference/model/clip_probe.joblib).Path
$env:REALCHECK_THRESHOLD_LOW = '0.3'
$env:REALCHECK_THRESHOLD_HIGH = '0.7'
$env:REALCHECK_INFERENCE_SLOTS = '1'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
python -m models.score <anh-validation-goc> --model artifacts/api-reference/model/clip_probe.joblib
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

CLI phải in số hữu hạn trong `[0,1]`; `/health` phải có `model_ready=true`. Gửi JPEG/PNG gốc vào multipart field `file` của `/v1/analyze`.

## Trả lời PR #36 và hợp đồng score

**Đa luồng:** chưa chứng nhận cùng một `Scorer`/encoder an toàn khi gọi đồng thời nhiều thread. Frozen/eval không đủ chứng minh điều đó. Giữ **1 worker, `REALCHECK_INFERENCE_SLOTS=1`**, mỗi process một scorer. Tăng slot cần kiểm đồng thời, parity, RSS và tải riêng; chưa cho phép `inference_slots > 1` dựa trên smoke này.

**Thời gian từng bước:** gói có `profile_stages.py`, dùng cùng normalize → CLIP → LR, đối chiếu score gốc trong tolerance `1e-5`. Từ repo root, đặt `PYTHONPATH` tới repo rồi chạy:

```text
python artifacts/api-reference/profile_stages.py <anh-validation-goc> --model artifacts/api-reference/model/clip_probe.joblib --repeat 5 --output profile.json
```

N=5 lượt tuần tự trên một ảnh real validation: median normalize/JPEG **2,75 ms**, CLIP **102,13 ms**, LR **0,50 ms**, total **105,46 ms**. Đây là chẩn đoán offline Windows, không phải p95 và không thêm telemetry từng request vào API. **FR-A06 logging từng bước trong API còn thuộc phần Backend**, không đánh dấu hoàn tất bằng script này.

**Xác nhận kỹ thuật phía ML:** `score(PIL.Image gốc đã giải mã) -> float` hữu hạn `[0,1]`; giữ EXIF cho normalizer, API giải mã một lần và không resize/nén; scorer chuẩn hóa đúng một lần. Ảnh nhỏ phát `ImageTooSmall`; lỗi suy luận phát ra để API ánh xạ lỗi. Loader khởi tạo một lần trong lifespan. Binary threshold 0.5; API 0.3/0.7, cả hai biên thuộc `uncertain`. Ghi xác nhận ML để Quang/Lực review; chưa tự đổi trạng thái phê duyệt chung thành `approved`.

D02 alpha/ICC/subsampling và trạng thái duyệt ghi tại [decision bổ sung](decisions/ml-api-handoff-39.md).

## Kiểm chứng và việc còn lại

Code API/ML được đối chiếu nội dung với main commit **`274f869ada646400d00f832b0aa3723c219d7742`** trước chạy:

- Real CLIP/probe: loader 1 lần, encoder frozen/eval, `/health` 200 và không chạy inference.
- 4 ảnh validation, mỗi nguồn real/SD1.4/GLIDE/Midjourney một ảnh: **4/4 HTTP 200**, sai khác với direct score tối đa **0** (`tolerance=1e-5`). Đây là parity, không phải accuracy trên N=4.
- Bytes không phải ảnh: 400 `INVALID_IMAGE`, thêm **0** lần gọi model.
- CLI thật in `AI score: 0.06939249`; GNU checksum từ `verification/` báo `../model/clip_probe.joblib: OK` trên máy gửi.
- CRC và SHA archive khớp. Không đổi model gốc hoặc default cũ; không train/mở test trong PR A.

**Chưa có xác nhận phía nhận.** @AIVIETNAM-AIO-DangQuang cần tải gói, chạy checksum và CLI trên máy mình, đăng output cùng model SHA trong [issue #39](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/39). Để issue mở đến khi có bằng chứng đó; merge PR tài liệu chỉ hoàn tất phần tài liệu/quyết định/bằng chứng máy gửi. QA độc lập và release vẫn chưa duyệt.

Jira chưa cập nhật trực tiếp vì chưa có kết nối tài khoản. [Bảng rà soát](ml-recheck-20261110.md) phân biệt phần đã có bằng chứng và phần còn lại, không ghi nhận transition Done giả.
