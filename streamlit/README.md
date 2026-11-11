# streamlit/ – Giao diện demo

Phụ trách: Loan

## Làm gì
Kéo thả ảnh, hiện kết quả từ API. Hai trang: "Kiểm tra ảnh" và "Kết quả đánh giá".

| File | Chức năng |
|---|---|
| `app.py` | Trang Kiểm tra ảnh và điều hướng |
| `api_client.py` | Gọi `POST /v1/analyze`, kiểm tra phản hồi, đổi mã lỗi thành thông báo tiếng Việt |
| `pages/1_Ket_qua_danh_gia.py` | Tab Mô hình đọc báo cáo đánh giá; tab Dữ liệu đọc `data/labels.csv` và `data/metadata_audit.json` |
| `.streamlit/config.toml` | Giới hạn tải lên 5 MB, theme sáng và tối, ẩn nút Deploy khi demo |

## Cách chạy
Từ thư mục gốc repo:
```bash
pip install -r streamlit/requirements.txt
streamlit run streamlit/app.py
```

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `REALCHECK_API_URL` | `http://localhost:8000` | Địa chỉ API; khi triển khai trỏ tới Nginx |
| `REALCHECK_API_TIMEOUT` | `60` | Thời gian chờ API (giây), tạm, chờ D11 |
| `REALCHECK_EVAL_REPORT` | `artifacts/evaluation.json` | Đường dẫn báo cáo đánh giá |

Chạy bằng Docker cùng API và Nginx: `docker compose up -d --build` ở gốc repo rồi mở `http://localhost/` (xem [`nginx/README.md`](../nginx/README.md)). Image UI build từ `streamlit/Dockerfile`; trong Compose UI gọi API qua `http://nginx`.

Kiểm thử: `pip install -r requirements.txt -r streamlit/requirements.txt`, rồi `pytest tests/test_ui.py -q`. Test dùng HTTP giả và FastAPI thật với scorer giả, chưa gồm Nginx và model thật.

## Input / Output
- Input: ảnh JPEG/PNG người dùng kéo thả; báo cáo đánh giá JSON; `data/labels.csv`, `data/metadata_audit.json`.
- Output: verdict, điểm, EXIF, lý do, thời gian xử lý, trạng thái hệ thống (`GET /health`); số đo mô hình và dữ liệu.

### Báo cáo đánh giá
Do `scripts/evaluate.py` tạo cho validation (T013), hoặc `models.evaluate` cho GenImage test theo protocol đã duyệt. `by_source` và `ood` là tùy chọn. `test: null` nghĩa là chưa đo tập test, trang sẽ hiện "Chưa đo trên tập test". Mảng `confusion_matrix` theo thứ tự `[real, ai]`, hàng là thực tế, cột là dự đoán. Nếu holdout là subset đã lọc lịch sử thì N báo cáo chỉ tính subset đó; xem [lựa chọn ML](../docs/decisions/ml-selection.md).
```json
{
  "dataset": {"version": "v1", "hash": "..."},
  "model": {"version": "v1", "hash": "..."},
  "profile": {"version": "v1", "hash": "..."},
  "thresholds": {"binary": 0.5, "low": 0.3, "high": 0.7},
  "test": {
    "n": 900,
    "accuracy": 0.0,
    "precision": 0.0,
    "recall": 0.0,
    "decided_accuracy": 0.0,
    "uncertain_n": 0,
    "confusion_matrix": [[0, 0], [0, 0]]
  },
  "by_source": [{"name": "GLIDE", "n": 150, "accuracy": 0.0, "uncertain_n": 0}],
  "ood": [{"name": "Ảnh điện thoại", "n": 150, "accuracy": 0.0, "uncertain_n": 0}]
}
```

## Lưu ý và giả định
- Gọi API qua Nginx, không gọi thẳng model; không import `models/`.
- Mỗi lần bấm chỉ gửi một request, không tự thử lại; đổi ảnh thì xóa kết quả cũ. Ảnh và kết quả chỉ nằm trong phiên của người dùng.
- Không có API hoặc báo cáo thì báo chưa sẵn sàng, không hiển thị số giả. Báo cáo sai định dạng cũng không hiển thị số nào.
- Giá trị `verdict` và định dạng lỗi (D05) chưa chốt: `api_client.py` tạm nhận `likely_real`, `real`, `uncertain`, `likely_ai`.
- Điểm AI hiển thị theo % (API vẫn trả số 0–1); đây không phải xác suất chắc chắn; EXIF không làm đổi kết luận.
- Theme mặc định theo máy người dùng; đổi Sáng/Tối ở menu ⋮ góc trên bên phải (System, Light, Dark).
- Giao diện hiện 4 mức (Ảnh thật, Dự đoán thật, Dự đoán AI, Ảnh AI), API và báo cáo vẫn dùng 3 kết luận: hai mức "Dự đoán" chính là `uncertain`/"Chưa chắc", tách theo điểm so với 0.5.
- Thang điểm vẽ theo ngưỡng 0.3 / 0.7 trong `app.py`; kết luận luôn lấy từ `verdict` của API. Đổi ngưỡng (D08) thì sửa hằng số này cho khớp.
- Giới hạn tải lên trên giao diện là 5 MiB (`maxUploadSize`), API vẫn kiểm tra lại theo D06. Cảnh báo 256 px chỉ để báo sớm, API mới là nơi từ chối.
