# Data Model: Đồng bộ chuẩn hóa ảnh

Mô tả thực thể ở mức dữ liệu; không chứa mã cài đặt.

## NormalizationVersion

- **Là gì:** định danh phiên bản quy trình chuẩn hóa (hằng `NORMALIZATION_VERSION` trong `models/normalize.py`).
- **Giá trị:** chuỗi không rỗng; giá trị khởi tạo do Kiệt đặt (ví dụ `"1"`).
- **Quy tắc:** đổi bất kỳ tham số nào (kích thước, bộ lọc, chất lượng JPEG, thứ tự bước) thì PHẢI tăng version; sau đó PHẢI tạo lại dữ liệu, trích lại đặc trưng và train lại (constitution VI).
- **Xuất hiện ở:** cột `norm_version` của `data/labels.csv`; `data/features/manifest.json` (cạnh các tệp `.npy`); metadata của `models/clip_probe.joblib`; danh sách ảnh bị loại.

## Tham số chuẩn hóa (cố định ở version đầu)

| Tham số | Giá trị | Nguồn |
|---|---|---|
| Kích thước đầu ra | 256×256 | spec FR-002 |
| Bộ lọc resize | BICUBIC | Clarifications (câu 1) |
| Chất lượng JPEG | 95, nén đúng một lần | Clarifications (câu 1) |
| Xoay theo orientation | có, trước khi resize | Clarifications (câu 2) |
| Ngưỡng "quá nhỏ" | cạnh ngắn < 256 px | Clarifications (câu 3) |
| Ngoại lệ | CIFAKE giữ 32×32 | Clarifications (câu 3) |

## NormalizedImage (kết quả của hàm chuẩn hóa)

| Trường | Kiểu | Ghi chú |
|---|---|---|
| `jpeg` | bytes | JPEG sau đúng một lần nén; đây là nội dung ghi ra `data/processed` |
| `image` | ảnh RGB 256×256 | giải mã từ chính `jpeg`; là đầu vào của tiền xử lý CLIP |
| `version` | chuỗi | = `NORMALIZATION_VERSION` |

**Ràng buộc:** `image` PHẢI bằng kết quả giải mã `jpeg`; không được lấy từ ảnh trước khi nén.

## ImageTooSmall (lỗi nghiệp vụ)

- Xảy ra khi cạnh ngắn của ảnh < 256 px (sau xoay), với `resize=True`.
- Mang theo: kích thước gốc (rộng, cao).
- Xử lý: pipeline dữ liệu ghi vào danh sách bị loại; API từ chối kèm thông báo (mã lỗi cụ thể còn mở).

## LabelsRow (data/labels.csv, mở rộng)

| Cột | Ràng buộc |
|---|---|
| `filepath` | đường dẫn ảnh đã chuẩn hóa, duy nhất |
| `label` | 0 (thật) hoặc 1 (AI) |
| `source` | một trong `genimage_real`, `genimage_sd14`, `genimage_midjourney`, `genimage_glide`, `cifake_real`, `cifake_ai` |
| `split` | `train`, `val` hoặc `test` |
| `raw_path` | đường dẫn ảnh gốc tương ứng |
| `norm_version` | **MỚI**, chuỗi, bằng `NORMALIZATION_VERSION` lúc chạy |

## FeatureManifest (data/features/manifest.json)

Ghi cạnh các tệp đặc trưng `.npy` (không commit). Do script trích đặc trưng ghi; bước huấn luyện đọc và kiểm tra.

| Trường | Ràng buộc |
|---|---|
| `norm_version` | chuỗi, bằng `NORMALIZATION_VERSION` lúc trích đặc trưng |
| `rows` | số nguyên ≥ 0, bằng số dòng của `data/labels.csv` tại lúc trích |
| `order` | cách ghép từng vector với `filepath` (thứ tự dòng của `labels.csv`) |
| `labels_norm_version` | `norm_version` đọc từ `labels.csv` tại lúc trích |

**Ràng buộc:** hàm tải đặc trưng PHẢI từ chối khi `norm_version` của manifest khác `NORMALIZATION_VERSION` hiện hành hoặc khác `labels_norm_version`, hoặc khi `rows` không khớp `labels.csv`; bước huấn luyện (M4, ngoài phạm vi tính năng này) PHẢI dùng hàm tải này (constitution VI).

## ProcessedBaseline (data/processed_baseline.sha256)

Bảo toàn dữ liệu chuẩn hóa cũ trước khi ghi đè. Tệp văn bản nhỏ (~1 MB), không bị `.gitignore`, có thể commit. Chỉ đọc dữ liệu, không đổi dữ liệu.

| Thành phần | Ghi chú |
|---|---|
| Dòng chú thích đầu (`#`) | commit cuối cùng chạm vào `scripts/prepare_data.py` (mã đã sinh dữ liệu cũ), phiên bản Pillow, sha256 của `data/labels.csv` cũ |
| Dòng dữ liệu | `sha256  đường_dẫn_ảnh` cho mọi tệp `.jpg` trong `data/processed`, sắp theo đường dẫn, đường dẫn tính từ gốc repo |

**Quyết định (nhóm):** file này được commit như `data/labels.csv` (metadata mã băm nhỏ, không chứa ảnh, không vi phạm luật không commit dữ liệu ảnh); `data/README.md` ghi một dòng giải thích. Dữ liệu thô dùng để chuẩn hóa lại KHÔNG nằm trong repo.

**Ràng buộc:** phải tồn tại TRƯỚC khi chạy bước ghi đè dữ liệu (`scripts/prepare_data.py` mới); `sha256sum -c data/processed_baseline.sha256` phải báo mọi tệp OK tại thời điểm chụp.

## RejectedImage (danh sách bị loại, file tạm)

| Trường | Ghi chú |
|---|---|
| `raw_path` | ảnh gốc bị loại |
| `source` | nguồn dữ liệu |
| `width`, `height` | kích thước gốc |
| `reason` | lý do, ví dụ cạnh ngắn dưới 256 |
| `norm_version` | version tại lúc loại |

**Quy tắc:** mỗi ảnh bị loại PHẢI có đúng một bản ghi; ảnh có bản ghi KHÔNG được có trong `labels.csv` (SC-004).

## QualityCheckResult

- **Kiểm tra metadata (FR-009):** AUROC, khoảng tin cậy 95%, trạng thái `đạt`/`cảnh báo` so với 0.55, theo từng slice.
- **Dấu vết nén nhiều lần (FR-010):** số đo theo từng source (chỉ báo cáo, chưa có ngưỡng).
