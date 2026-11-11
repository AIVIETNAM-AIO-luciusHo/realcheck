# KAN-25 (B5): review mã mô hình và cách nạp model từ góc nhìn tích hợp API

Mã task: B5. Phạm vi: `models/score.py`, `models/clip_input.py`, `app/inference.py`, `app/main.py`, `app/settings.py`, `Dockerfile`, `models/requirements-ml.txt`, và cách chạy trong `app/README.md`. Mã trên `main` tại `7cb0f2b`. Soạn bởi QA (Lực) thay cho người được giao (Quang) trên cơ sở đọc mã và kết quả chạy thật ngày 11/11 ([biên bản](local-real-model-verification-20261111.md)); Quang xác nhận lại các điểm tích hợp. Không sửa mã trong PR này.

## Kết luận ngắn

Cách nạp đúng hợp đồng và an toàn hơn mức tối thiểu: kiểm checksum trước khi giải mã joblib, kiểm metadata, nạp CLIP đúng revision, warmup lúc khởi động. Có **hai điểm nên sửa trước bàn giao** (model mặc định, ràng buộc phiên bản Pillow) và vài điểm lưu ý. Không có lỗi chặn MVP.

## Đối chiếu từng tiêu chí

| Tiêu chí KAN-25 | Kết quả | Bằng chứng |
|---|---|---|
| Cách nạp CLIP và `clip_probe.joblib` | **Đạt**, kèm điểm cần sửa bên dưới | `load_bundle` đọc `.sha256` cạnh file, so với SHA256 file, rồi mới `joblib.load`; kiểm `metadata` (dataset, hợp đồng đặc trưng, `norm_version`), ngưỡng `0 < binary < 1`, `0 <= low < high <= 1`, `Scorer(probe, None)` kiểm lớp `{0,1}` và 512 đặc trưng. `load_scorer` nạp CLIP đúng revision `327ab672…`, `trust_remote_code=False`, `eval()` và tắt gradient, rồi warmup một ảnh 256×256. Chạy thật 11/11: checksum sai bị từ chối trước khi nạp CLIP |
| Đầu vào và ý nghĩa điểm khớp giao diện đã thống nhất | **Đạt** | `Scorer.__call__` nhận ảnh gốc đã giải mã, gọi `normalize_image` đúng một lần, trả `float` P(AI). Cột AI lấy theo `classes_` (không hardcode). Xác suất bị từ chối nếu không hữu hạn, ngoài `[0,1]` hoặc không cộng bằng 1. API (`app/uploads.py`) chỉ nhận `float` và numpy float. Điểm CLI và API lệch tối đa 5e-9 |
| Hướng dẫn dependency và đường dẫn | **Đạt một phần** | `models/requirements-ml.txt` ghim `torch==2.15.0`, `sentence-transformers==6.2.0`, `transformers==5.22.1`; `Dockerfile` dùng cùng `torch` từ index CPU. `HF_HOME`, `HF_HUB_OFFLINE=1` đã đặt trong `Dockerfile`. Điểm 1 và 5 bên dưới |
| Ghi nhận xét và vấn đề cần sửa trước bàn giao | Văn bản này | |

## Vấn đề cần sửa hoặc quyết định

| # | Mức | Vấn đề | Đề xuất |
|---|---|---|---|
| 1 | Nên sửa | `DEFAULT_MODEL_PATH` (`models/clip_probe.joblib`) vẫn là model cũ `69810fd6…`. Quên `REALCHECK_MODEL_PATH` thì API nạp nhầm model cũ nếu file đó tồn tại, hoặc `/health` 503. `Dockerfile` cũng đặt mặc định `/models/clip_probe.joblib`. | Quyết định với Kiệt: đổi mặc định sang e571, hoặc từ chối khởi động nếu không đặt biến. Ít nhất ghi trong README (đã có ở PR #67) |
| 2 | Nên sửa | `feature_contract()` đưa `pillow_version` vào hợp đồng và `load_bundle` so từng khóa. Model train với Pillow 13.0.0 sẽ **từ chối nạp** nếu đổi phiên bản Pillow (ví dụ bản vá bảo mật), thông báo `Incompatible model: pillow_version; retrain before serving`. Có thể là chủ ý (bảo đảm tái lập đặc trưng) nhưng chưa được ghi. | Ghi rõ ràng buộc này trong `models/README.md` và `Dockerfile` (ghim `pillow==13.0.0` đã có ở `requirements.txt`); hoặc tách khỏi điều kiện từ chối nếu bằng chứng cho thấy đặc trưng không đổi giữa hai phiên bản |
| 3 | Lưu ý | `torch.set_num_threads(4)` cố định trong `load_encoder`. Trên máy ít hoặc nhiều lõi hơn, độ trễ khác và không cấu hình được; ảnh hưởng số đo SLO. | Cho đọc từ biến môi trường, hoặc ghi 4 luồng vào điều kiện đo SLO |
| 4 | Lưu ý | Lỗi nạp model (file hỏng, thiếu cache) bị nuốt: app vẫn khởi động, `/health` 503 mãi và không tự thử lại; container chỉ `unhealthy`, không tự restart (`restart: unless-stopped` chỉ khởi động lại khi tiến trình thoát). | Đúng với AC-20; lab nên giám sát trạng thái `unhealthy` và ghi vào hướng dẫn rollback (#42) |
| 5 | Lưu ý | Chạy ngoài Docker (uvicorn trực tiếp) không tự đặt `HF_HUB_OFFLINE=1`; thiếu cache thì tải CLIP khi khởi động, request chưa nhận được trong lúc đó (`load` không có timeout, D11 tính startup riêng). | Hướng dẫn chạy cục bộ nhắc đặt `HF_HUB_OFFLINE=1` (có ở #67); lab dùng Docker |
| 6 | Lưu ý | Checksum cạnh file chỉ chống hỏng file, không chống thay thế có chủ ý (kẻ ghi được thư mục `models/` thay cả model lẫn `.sha256`); `joblib.load` thực thi mã. Docstring đã cảnh báo. | `models/` mount `:ro` (Compose đã làm); không bao giờ nạp file người dùng gửi lên; cân nhắc ký số khi lên production |
| 7 | Lưu ý | `Scorer` chưa được chứng nhận an toàn đa luồng; API dùng `inference_slots=1`. Số đo sơ bộ cho thấy 5 người dùng đồng thời gây khoảng 21% 503. | Chờ Kiệt xác nhận ở #44; giữ 1 slot nếu chưa kịp |
| 8 | Nit | `_log_failure` ghi `str(exc)` vào log (có thể chứa đường dẫn file). Không lộ ra response. | Chấp nhận được; cân nhắc rút gọn nếu log đi ra ngoài |

## Chưa kiểm

- Chưa chạy lại `models/score.py` với model và ảnh thật của Quang; chạy thật chỉ có ảnh tổng hợp trên Linux và 4 ảnh GenImage trên Windows (Quang).
- Chưa đo thời gian từng bước normalize, CLIP, LR qua API (FR-A06); có profiler offline nhưng chưa chạy.
- Đa luồng thật chưa thử.

## Điều kiện đóng KAN-25

Văn bản này được merge vào `main`; Quang xác nhận các điểm tích hợp; điểm 1 và 2 được xử lý hoặc có issue theo dõi; comment Jira dẫn tới file này và PR.
