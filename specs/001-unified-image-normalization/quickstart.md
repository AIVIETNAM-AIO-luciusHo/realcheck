# Quickstart: Kiểm chứng đồng bộ chuẩn hóa ảnh

Hướng dẫn chạy để chứng minh tính năng hoạt động từ đầu đến cuối. Hợp đồng chi tiết ở [contracts/interfaces.md](contracts/interfaces.md), thực thể ở [data-model.md](data-model.md). Các lệnh dưới đây là kế hoạch: tệp tương ứng chưa tồn tại cho đến khi tasks được thực hiện.

## Điều kiện cần

- Chạy từ gốc repo; Python 3.11+; đã cài `scripts/requirements-data.txt` và `requirements.txt` (sẽ thêm).
- Dữ liệu gốc đã tải về `data/raw/` (`python -m scripts.download_data cifake`, `genimage`), không cần PyTorch cho các bước 1–4.

## 1. Kiểm tra mã chuẩn

```bash
ruff check .
ruff format --check .
pytest --cov=app --cov-fail-under=70
```

Mong đợi: ruff sạch; pytest chạy thật các test mới (không bị bỏ qua) và qua.

## 2. Chuẩn hóa dữ liệu bằng hàm chung

```bash
python -m scripts.prepare_data
```

Mong đợi: ghi `data/labels.csv` có cột `norm_version`; in số ảnh bị loại theo source (kỳ vọng ~292 ảnh thật nhỏ, theo `data/README.md`); CIFAKE giữ 32×32; mọi ảnh bị loại có bản ghi lý do.

## 3. Ảnh mẫu theo `raw_path` trùng baseline dữ liệu cũ (SC-003)

```bash
python -m scripts.check_normalization --raw-dir <thư mục dữ liệu thô>
```

Điều kiện: `data/processed_baseline.sha256` đã được chụp trước khi chạy bước 2; dữ liệu thô không có sẵn trên mọi máy, nên chỉ định bằng `--raw-dir` (vd. thư mục dữ liệu thô do T013 tải, ngoài repo); bỏ `--raw-dir` thì dùng `data/raw`. Mong đợi: mọi ảnh mẫu chuẩn hóa lại từ `raw_path` có sha256 trùng dòng tương ứng trong baseline; thoát mã 0.

## 4. Kiểm tra dữ liệu và chất lượng

```bash
python -m scripts.check_data
python -m scripts.metadata_audit
python -m scripts.jpeg_trace_check
```

Mong đợi: `check_data` không lỗi (nhớ rằng cân bằng lớp có thể cảnh báo tới khi KAN-34 bù ảnh); `metadata_audit` in AUROC và khoảng tin cậy, cảnh báo nếu vượt 0.55; `jpeg_trace_check` in số đo theo từng source.

## 5. Kiểm thử hành vi bằng test

```bash
pytest tests/test_normalize.py tests/test_score_normalization.py
```

Mong đợi (ảnh tổng hợp bằng Pillow, mock CLIP, không cần dữ liệu thật):

| Kịch bản | Kết quả |
|---|---|
| Ảnh 4000×3000 | đầu ra 256×256, nén JPEG chất lượng 95 đúng một lần |
| Ảnh cạnh ngắn < 256 | ném `ImageTooSmall`, không phóng to |
| Ảnh có cờ orientation | được xoay trước khi resize |
| `score()` | gọi hàm chuẩn hóa đúng một lần; không nhận cờ `resize` |
| Cùng ảnh qua đường huấn luyện và đường API | đầu vào CLIP giống hệt (độ lệch 0) |

## 6. Kiểm thử API

Mã lỗi và `verdict` theo D05 trong [`docs/decisions/realcheck-baseline.md`](../../docs/decisions/realcheck-baseline.md). Kịch bản: gửi ảnh 4000×3000 mong đợi kết quả hợp lệ; gửi ảnh 200×200 mong đợi từ chối kèm thông báo.
