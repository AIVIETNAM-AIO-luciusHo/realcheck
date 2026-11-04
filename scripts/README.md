# scripts/ – Script tiện ích

Phụ trách: Lực (review chéo), người viết ghi tên vào PR

## Làm gì
Script đánh giá (Accuracy, Precision, Recall, confusion matrix, % "Chưa chắc") và script tải/chuẩn hóa dữ liệu.

## Cách chạy
`python -m scripts.<tên_script>` từ thư mục gốc repo.

| Script | Người viết | Làm gì |
|---|---|---|
| `download_data.py` | Loan | Tải CIFAKE, GenImage về `data/raw/` |
| `prepare_data.py` | Loan | Chuẩn hóa ảnh, chia tập, xuất `data/labels.csv` |
| `check_data.py` | Loan | Kiểm tra `labels.csv` và ảnh đã chuẩn hóa; lỗi thì thoát mã 1 |
| `baseline_filesize.py` | Loan | Dung lượng file theo nguồn, chỉ tham khảo độ chi tiết ảnh (không phải gate) |
| `metadata_audit.py` | Loan | Đoán thật/AI chỉ từ metadata, raw và post; gate post `A_eff <= 0.55`, không đạt thì thoát mã 1 (bản nháp T007) |
| `verify_ml.py` | Kiệt | Model thật: parity tensor train/serve, score từ raw so feature cache, ảnh lớn/mode ảnh/ảnh nhỏ; chỉ lấy mẫu validation |

Thư viện cho các script dữ liệu: `pip install -r scripts/requirements-data.txt`. Thứ tự chạy xem [`data/README.md`](../data/README.md).

Chuẩn hóa mới dùng chung `models.normalize` với ML, không cần torch. Để giữ nguyên dữ liệu/manifest cũ:

```bash
python -m scripts.prepare_data --output-dir .cache/ml-run/processed-v1 --labels .cache/ml-run/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-run/labels.csv
```

`prepare_data` từ chối ghi đè output đã có; dùng đường dẫn mới khi chạy lại. Ảnh quá nhỏ/hỏng có bản ghi trong `rejected_small.csv` cạnh output. `--workers` mặc định 2 để tránh tạo quá nhiều process trên Windows. Trước khi thay dữ liệu chuẩn chính của Loan vẫn cần baseline theo spec 001. Checker đọc manifest cũ nhưng cảnh báo chưa có version; extractor ML chỉ nhận manifest có version đúng. Lệnh train xem [`models/README.md`](../models/README.md).

## Input / Output
- Input: `data/labels.csv`, `models/clip_probe.joblib`.
- Output: bảng số đo, `labels.csv`.

## Lưu ý và giả định
- Script phải chạy lại được và cho cùng kết quả.
