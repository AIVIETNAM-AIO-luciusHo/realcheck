# Implementation Plan: Đồng bộ chuẩn hóa ảnh giữa huấn luyện và API

**Branch**: chưa tạo (đặt tên theo quy ước `ten/mo-ta-ngan`) | **Date**: 2026-11-03 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-unified-image-normalization/spec.md`

## Summary

Gom logic chuẩn hóa ảnh đang nằm trong `scripts/prepare_data.py` thành một module dùng chung `models/normalize.py` (Kiệt chịu trách nhiệm chính, Loan review). Cả `prepare_data.py` và `score(image)` gọi đúng hàm đó. Hàm tái tạo đúng các bước của pipeline hiện tại (xoay theo EXIF, RGB, `ImageOps.fit` BICUBIC 256×256, JPEG chất lượng 95 một lần) để ảnh đã chuẩn hóa còn lại trùng byte với dữ liệu cũ (kiểm bằng `data/processed_baseline.sha256`, chụp trước khi ghi đè); thêm ngưỡng "quá nhỏ" (cạnh ngắn < 256 px, không phóng to), version chuẩn hóa, và hai phép kiểm tra chất lượng (metadata AUROC kèm khoảng tin cậy, dấu vết nén JPEG nhiều lần). Hai mục `verdict` và mã lỗi đã chốt tại D05 trong [`docs/decisions/realcheck-baseline.md`](../../docs/decisions/realcheck-baseline.md), nên không còn chặn task API tương ứng.

## Technical Context

**Language/Version**: Python 3.11 (theo CI hiện tại); máy local đang dùng Python 3.12

**Primary Dependencies**: Pillow (chuẩn hóa), NumPy/pandas/scikit-learn (script dữ liệu hiện có), `transformers` + PyTorch (CLIP, phía Kiệt, chưa có trong repo); `models/normalize.py` CHỈ phụ thuộc Pillow để pipeline dữ liệu không phải cài PyTorch

**Storage**: Tệp: `data/processed/*.jpg`, `data/labels.csv`, danh sách ảnh bị loại (file tạm); không có cơ sở dữ liệu

**Testing**: pytest + pytest-cov, ruff; test của tính năng này nằm trong `tests/` (Lực)

**Target Platform**: Linux (WSL2) và CI GitHub Actions trên Ubuntu; chạy CPU

**Project Type**: Thư viện nội bộ (`models/`) + script dữ liệu (`scripts/`) + API (`app/`, Quang)

**Performance Goals**: Không đặt mục tiêu hiệu năng (spec không yêu cầu). Tham chiếu: `prepare_data.py` hiện xử lý 10.000 ảnh trong ~34 giây trên máy QA (theo lần chạy lại độc lập trước đây)

**Constraints**: không phóng to ảnh; JPEG đúng một lần; ảnh còn lại phải trùng với dữ liệu cũ (so qua `data/processed_baseline.sha256`, chụp trước khi ghi đè); `models/normalize.py` không phụ thuộc FastAPI hay PyTorch

**Scale/Scope**: ~10.000 ảnh; 292/3.000 ảnh thật GenImage có cạnh ngắn < 256 px (theo `data/README.md`) sẽ bị loại

**Còn mở (NEEDS CLARIFICATION, cố ý không tự đặt)**: giá trị `verdict` ngoài `likely_ai`; mã lỗi cho ảnh không đọc được/quá nhỏ. Hai mục này chỉ chặn các task phần API tương ứng, không chặn module chuẩn hóa.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Nguyên tắc | Yêu cầu | Đánh giá (trước nghiên cứu) | Sau thiết kế |
|---|---|---|---|
| I. Kiến trúc | `models/` không phụ thuộc FastAPI/Streamlit; app lo HTTP, EXIF, schema | Đạt: `normalize.py` chỉ dùng Pillow | Đạt: API giải mã, đọc EXIF, gọi `score()` |
| II. Dữ liệu/mô hình | Giữ GenImage, `labels.csv` đủ cột, QA kiểm độc lập, báo theo source; CIFAKE là ngoại lệ 32×32 (đã ghi vào constitution) | Đạt có điều kiện: thêm cột `norm_version` cần cập nhật `check_data.py` | Đạt, ghi trong research R4 |
| III. Testing | Test hành vi, CI chạy pytest thật | **Cảnh báo**: CI bỏ qua pytest khi thiếu `requirements.txt`; cần thêm file này | Đạt khi có `requirements.txt` + test (R10) |
| IV. Code style | ruff, type hint, không nhân bản logic | Đạt: một hàm duy nhất, type hint bắt buộc | Đạt |
| V. Triển khai | Không đụng Nginx/Locust | Đạt (ngoài phạm vi) | Đạt |
| VI. Chuẩn hóa dùng chung | Một hàm, có version (cùng dữ liệu, đặc trưng và model), một lần nén, đổi tham số thì trích lại và train lại | Đạt thiết kế | Đạt: version ghi vào `labels.csv`, `data/features/manifest.json` và model |
| Quy trình | Review độc lập, README cập nhật, quyết định mở phải chốt trước khi triển khai | **Cảnh báo**: `verdict` và mã lỗi còn mở | Giữ mở, chặn task API liên quan |

Không có vi phạm cần biện minh; hai cảnh báo (CI bỏ qua pytest, hai quyết định mở) được xử lý ở R10 và ở dưới đây.

**Khác biệt cần Loan/Lực xác nhận:** `scripts/metadata_audit.py` hiện là **cổng cứng** (thoát mã 1 khi A_eff > 0.55), trong khi spec (FR-009) coi 0.55 là **ngưỡng cảnh báo**. Plan đề xuất đổi hành vi thành cảnh báo (R8); cần xác nhận vì README của `scripts/` đang mô tả nó là gate.

## Project Structure

### Documentation (this feature)

```text
specs/001-unified-image-normalization/
├── plan.md              # File này
├── research.md          # Phase 0
├── data-model.md        # Phase 1
├── quickstart.md        # Phase 1
├── contracts/
│   └── interfaces.md    # Phase 1
├── checklists/
│   └── requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks, chưa tạo)
```

### Source Code (repository root)

```text
models/
├── normalize.py            # MỚI: hàm chuẩn hóa chung + NORMALIZATION_VERSION (Kiệt, Loan review)
├── clip_input.py           # MỚI: tiền xử lý CLIP dùng chung cho trích đặc trưng và score() (Kiệt)
├── extract_features.py     # MỚI: trích đặc trưng CLIP, ghi .npy và data/features/manifest.json (Kiệt)
└── score.py                # MỚI: score(image) gọi normalize đúng một lần (Kiệt)
scripts/
├── prepare_data.py         # SỬA: import normalize, ghi danh sách ảnh bị loại, cột norm_version (Loan)
├── check_data.py           # SỬA: COLUMNS có norm_version (Loan)
├── check_normalization.py  # MỚI: so ảnh mẫu theo raw_path với baseline sha256 của dữ liệu cũ (SC-003); nhận --raw-dir (Lực)
├── jpeg_trace_check.py     # MỚI: kiểm tra dấu vết nén nhiều lần, báo theo source (Lực)
└── metadata_audit.py       # SỬA: AUROC 0.55 thành cảnh báo, giữ khoảng tin cậy (Loan)
app/
└── main.py                 # SỬA (Quang): giải mã một lần, đọc EXIF, bắt lỗi từ chối; CHỜ mã lỗi/verdict
data/
├── processed_baseline.sha256  # MỚI: sha256 dữ liệu chuẩn hóa cũ, chụp trước khi ghi đè (Loan); commit như labels.csv
└── labels.csv                # SỬA: thêm cột norm_version (Loan)
tests/
├── test_normalize.py       # MỚI: hợp đồng chuẩn hóa (Lực)
├── test_score_normalization.py  # MỚI: score() gọi chuẩn hóa đúng một lần (Lực)
└── test_extract_features.py     # MỚI: manifest ghi version, tải lại từ chối khi lệch (Lực)
requirements.txt            # MỚI: để CI chạy pytest thật (R10)
.github/workflows/ci.yml    # SỬA: cổng coverage app/ chỉ bật khi app/ có file .py (R10, Lực + Loan review)
```

**Structure Decision**: Giữ nguyên bố cục thư mục cấp 1 hiện có của repo. Không thêm thư mục mới ở gốc; module dùng chung nằm trong `models/` theo quyết định ở mục Clarifications. Cả `models/` và `scripts/` chưa có `__init__.py`; script dữ liệu chạy bằng `python -m scripts.<tên>` từ gốc repo để import được `models.normalize` (R2).

## Complexity Tracking

Không có vi phạm Constitution cần biện minh. Hai điểm cần theo dõi: tham số `resize` của hàm chuẩn hóa (chỉ để giữ ngoại lệ CIFAKE, R5) và đổi cách chạy script thành `python -m scripts.<tên>` (R2).
