# Interface Contracts: Đồng bộ chuẩn hóa ảnh

Hợp đồng giữa các thành phần của repo. Chỉ mô tả hành vi và ràng buộc, không phải mã cài đặt. Mục `[CẦN CHỐT]` là quyết định chưa có, không được tự đặt.

## C1. Hàm chuẩn hóa chung (`models/normalize.py`)

**Người chịu trách nhiệm:** Kiệt (review: Loan). **Người gọi:** `scripts/prepare_data.py`, `models/score.py`.

| Mục | Quy định |
|---|---|
| Đầu vào | Một ảnh đã giải mã (Pillow), cờ `resize` mặc định bật |
| Đầu ra | `NormalizedImage` gồm `jpeg` (bytes), `image` (giải mã từ `jpeg`), `version` |
| Thứ tự bước | xoay theo orientation EXIF → RGB → cắt giữa và resize về 256×256 bằng BICUBIC (`ImageOps.fit`) → JPEG chất lượng 95, đúng một lần → giải mã lại từ bytes |
| Lỗi | Ném `ImageTooSmall` khi cạnh ngắn < 256 và `resize` bật; không phóng to |
| Cờ `resize=False` | CHỈ cho CIFAKE trong `prepare_data.py`: bỏ cắt/resize và kiểm tra kích thước, vẫn xoay, RGB, JPEG 95 |
| Phụ thuộc | Chỉ Pillow; KHÔNG PyTorch, KHÔNG FastAPI |
| Tính xác định | Cùng ảnh vào thì cùng `jpeg` ra |

**Bất biến kiểm chứng được:**
1. Ảnh 4000×3000 cho `image` 256×256, `jpeg` nén một lần ở chất lượng 95.
2. Ảnh gốc theo `raw_path` cho `jpeg` có sha256 trùng với dòng tương ứng trong `data/processed_baseline.sha256` (dữ liệu cũ, với ảnh không bị loại).
3. Ảnh có cạnh ngắn < 256 ném `ImageTooSmall`, không có đầu ra.

## C2. `score` (`models/score.py`)

**Người chịu trách nhiệm:** Kiệt. **Người gọi:** `app/main.py`.

| Mục | Quy định |
|---|---|
| Chữ ký | `score(image) -> float` với `image` là ảnh gốc đã giải mã, **chưa chuẩn hóa** (Clarifications, câu 5) |
| Hành vi | Gọi hàm chuẩn hóa (C1) **đúng một lần**; đưa `NormalizedImage.image` qua tiền xử lý CLIP (`models/clip_input.py`); đưa vào bộ phân loại |
| Đầu ra | Số thực hữu hạn trong [0, 1]; càng gần 1 càng giống ảnh AI (AI = 1) |
| Lỗi | Để `ImageTooSmall` truyền ra; không bắt và không đổi thành điểm giả |
| Kiểm tra version | Từ chối chạy nếu version lưu trong model khác `NORMALIZATION_VERSION` hiện hành |
| Cấm | Không tự resize hoặc nén ảnh; không nhận cờ `resize` |

## C3. Tiền xử lý CLIP dùng chung (`models/clip_input.py`)

Một hàm duy nhất cho cả bước trích đặc trưng huấn luyện (M3) và `score()`. Cùng ảnh đã chuẩn hóa vào thì cùng tensor đầu vào CLIP ra, giống từng giá trị (SC-002). Tên tệp là đề xuất, có thể đổi nhưng phải là một hàm dùng chung.

## C3b. Trích đặc trưng và manifest (`models/extract_features.py`)

**Người chịu trách nhiệm:** Kiệt. Chạy bằng `python -m models.extract_features` (cần PyTorch).

| Mục | Quy định |
|---|---|
| Đầu vào | Ảnh trong `data/labels.csv` (ảnh đã chuẩn hóa) |
| Xử lý | Mỗi ảnh đi qua hàm tiền xử lý CLIP dùng chung (C3); KHÔNG tự resize hay nén |
| Đầu ra | Tệp `.npy` trong `data/features/` và `data/features/manifest.json` (xem data-model, FeatureManifest) |
| Tải lại | Hàm đọc đặc trưng PHẢI kiểm manifest và từ chối khi version hoặc số dòng không khớp; bước huấn luyện PHẢI dùng hàm này |

## C4. API `POST /v1/analyze` (phần liên quan chuẩn hóa)

**Người chịu trách nhiệm:** Quang.

| Bước | Quy định |
|---|---|
| 1 | Giải mã ảnh **một lần**; ảnh không đọc được thì từ chối |
| 2 | Đọc EXIF (hãng, model máy) từ ảnh gốc này, trước khi chuẩn hóa |
| 3 | Gọi `score(ảnh gốc)` |
| 4 | Bắt `ImageTooSmall` và từ chối kèm thông báo nêu rõ lý do và kích thước tối thiểu 256 px |
| 5 | Trả `verdict`, `score`, `exif`, `reason` theo schema đã có |
| Cấm | API KHÔNG resize hoặc nén ảnh; không kiểm lại ngưỡng kích thước riêng |

**Chưa chốt (chặn task phần này):**
- Mã lỗi HTTP và định dạng lỗi cho ảnh không đọc được và ảnh quá nhỏ: `[CẦN CHỐT]`.
- Giá trị máy đọc của `verdict` ngoài `likely_ai`: `[CẦN CHỐT]`.

## C5. Hợp đồng dữ liệu của pipeline (`scripts/prepare_data.py`)

| Mục | Quy định |
|---|---|
| Gọi | Chạy bằng `python -m scripts.prepare_data` từ gốc repo |
| Ảnh đủ điều kiện | Ghi `NormalizedImage.jpeg` ra `data/processed`; thêm cột `norm_version` vào `labels.csv` |
| Ảnh quá nhỏ (GenImage) | Không ghi vào `data/processed`/`labels.csv`; ghi một bản ghi vào danh sách bị loại (xem data-model) |
| CIFAKE | Gọi với `resize=False`, giữ 32×32 |
| Báo cáo cuối lần chạy | In số ảnh bị loại theo source và lý do; không có ảnh nào mất mà không có bản ghi |

## C6. Kiểm tra chất lượng

| Script | Đầu ra | Quy định |
|---|---|---|
| `scripts/metadata_audit.py` | AUROC, khoảng tin cậy 95%, trạng thái theo từng slice | Vượt 0.55 thì in cảnh báo (đề xuất, cần Loan/Lực xác nhận, xem research R8) |
| `scripts/jpeg_trace_check.py` | Số đo dấu vết nén nhiều lần theo từng source | Chỉ báo cáo, không có ngưỡng đạt/không đạt |
| `scripts/check_normalization.py` | So sha256 của `jpeg` do hàm mới tạo (từ `raw_path`) với `data/processed_baseline.sha256`; KHÔNG so với `data/processed` hiện tại vì sau khi ghi đè đó là chính hàm mới. Tham số `--raw-dir <thư mục>` đóng vai trò `data/raw` (mặc định `data/raw`) | Thoát mã khác 0 nếu có ảnh mẫu không trùng, hoặc nếu thư mục dữ liệu thô không tồn tại/thiếu ảnh cần so (nêu rõ đường dẫn đã thử, không tự giả định, không bỏ qua) |
