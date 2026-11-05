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
| `check_normalization.py` | Lực | `python -m scripts.check_normalization --raw-dir <dữ liệu thô>`: so sha256 của `jpeg` chuẩn hóa lại với `data/processed_baseline.sha256`, kiểm kê ảnh thô (labels hoặc `rejected_small/invalid/duplicate.csv`, tham số `--rejected-dir`, `--rejected-small/-invalid/-duplicate`). Thoát 0 đạt, 1 lỗi kiểm tra, 2 thiếu đầu vào, 3 ảnh thô hỏng. `rejected_duplicate.csv` tùy chọn để đọc được output cũ chưa có file này; `prepare_data` hiện luôn ghi file này |
| `jpeg_trace_check.py` | Lực | **Chưa có** (T027, KAN-46): chờ nhóm xác nhận phương pháp JPEG ghost; chưa dùng được |
| `perf_report.py` | Lực | `python -m scripts.perf_report <sidecar.jsonl> [--warmup-seconds N] [--warmup-requests N] [--output f.json]`: p50/p95/p99 chỉ của 200, offered RPS, RPS 200, đếm 429/503/504/5xx/other, tỉ lệ lỗi không tính 429; số đo thiếu ghi "thiếu". Thoát 2 nếu sidecar thiếu/rỗng/hỏng. Thuần stdlib |
| `check_performance.py` | Lực | `python -m scripts.check_performance --sidecar <jsonl> --slo docs/performance/slo.json`: thoát 0 đạt, 1 không đạt, 2 thiếu/hỏng SLO hoặc sidecar (in "chỉ là baseline, không kết luận đạt SLA"). SLO là JSON `{"p95_ms_max","rps200_min","error_ratio_max"}` do nhóm ký sau MVP-10; script không tự tạo SLO |
| `baseline_filesize.py` | Loan | Dung lượng file theo nguồn, chỉ tham khảo độ chi tiết ảnh (không phải gate) |
| `metadata_audit.py` | Loan | Đoán thật/AI chỉ từ metadata, raw và post; gate post `A_eff <= 0.55`, không đạt thì thoát mã 1 (bản nháp T007) |
| `verify_ml.py` | Kiệt | Model thật: parity tensor train/serve, score từ raw so feature cache, ảnh lớn/mode ảnh/ảnh nhỏ; chỉ lấy mẫu validation |

Thư viện cho các script dữ liệu: `pip install -r scripts/requirements-data.txt`. Thứ tự chạy xem [`data/README.md`](../data/README.md).

Chuẩn hóa mới dùng chung `models.normalize` với ML, không cần torch. Để giữ nguyên dữ liệu/manifest cũ:

```bash
python -m scripts.prepare_data --output-dir .cache/ml-run/processed-v1 --labels .cache/ml-run/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-run/labels.csv
```

`prepare_data` từ chối ghi đè output đã có; dùng đường dẫn mới khi chạy lại. `rejected_small.csv` chỉ chứa ảnh quá nhỏ; ảnh hỏng và `DecompressionBombError` vào `rejected_invalid.csv` riêng, ảnh trùng vào `rejected_duplicate.csv`, cùng các cột `raw_path,source,width,height,reason,norm_version` (kích thước là 0 nếu chưa đọc được). Lỗi ghi output phải làm lần chạy thất bại, không được coi là ảnh hỏng. `--workers` mặc định 2 để tránh tạo quá nhiều process trên Windows. Trước khi thay dữ liệu chuẩn chính của Loan vẫn cần baseline theo spec 001.

`check_data` yêu cầu đủ sáu cột, bao gồm `norm_version` ở cuối và đúng version hiện hành. Manifest cũ thiếu version là lỗi (exit 1), không còn chỉ cảnh báo; không tự thêm version vào dữ liệu cũ. Ảnh processed hỏng hoặc decompression bomb được ghi FAIL, lần kiểm tra thoát mã 1. Lệnh train xem [`models/README.md`](../models/README.md).

`verify_ml` chỉ lấy mẫu validation, từ chối nếu thiếu nguồn GenImage/ảnh validation, tensor lệch, score lệch, encoder chưa frozen hoặc ảnh nhỏ vẫn được chấp nhận. Báo cáo có UUID, lệnh gọi, commit, trạng thái dirty, Python và OS; test mock không thay thế lần chạy model thật. Xem [truy vết và tái lập](../docs/ml-reproducibility.md).

## Input / Output
- Input: `data/labels.csv`, `models/clip_probe.joblib`.
- Output: bảng số đo, `labels.csv`.

## Lưu ý và giả định
- Script phải chạy lại được và cho cùng kết quả.
