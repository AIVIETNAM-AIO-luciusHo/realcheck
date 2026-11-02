# scripts/ – Script tiện ích

Phụ trách: Lực (review chéo), người viết ghi tên vào PR

## Làm gì
Script đánh giá (Accuracy, Precision, Recall, confusion matrix, % "Chưa chắc") và script tải/chuẩn hóa dữ liệu.

## Cách chạy
`python scripts/<tên_script>.py` từ thư mục gốc repo.

| Script | Người viết | Làm gì |
|---|---|---|
| `download_data.py` | Loan | Tải CIFAKE, GenImage về `data/raw/` |
| `prepare_data.py` | Loan | Chuẩn hóa ảnh, chia tập, xuất `data/labels.csv` |
| `check_data.py` | Loan | Kiểm tra `labels.csv` và ảnh đã chuẩn hóa; lỗi thì thoát mã 1 |
| `baseline_filesize.py` | Loan | Dung lượng file theo nguồn, chỉ tham khảo độ chi tiết ảnh (không phải gate) |
| `metadata_audit.py` | Loan | Đoán thật/AI chỉ từ metadata, raw và post; gate post `A_eff <= 0.55`, không đạt thì thoát mã 1 (bản nháp T007) |

Thư viện cho các script dữ liệu: `pip install -r scripts/requirements-data.txt`. Thứ tự chạy xem [`data/README.md`](../data/README.md).

## Input / Output
- Input: `data/labels.csv`, `models/clip_probe.joblib`.
- Output: bảng số đo, `labels.csv`.

## Lưu ý và giả định
- Script phải chạy lại được và cho cùng kết quả.
