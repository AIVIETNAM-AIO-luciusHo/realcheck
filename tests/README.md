# tests/ – pytest

Phụ trách: Lực

## Làm gì
Từ 15 test trở lên cho API, model và dữ liệu. Test chống phá: ảnh pixel cực lớn, file giả đuôi `.jpg`, gửi liên tục để kiểm tra 429. Test độ bền model: xoay, cắt viền, thu nhỏ, chỉnh sáng.

## Cách chạy
`pytest --cov=app --cov-fail-under=70`

## Input / Output
- Input: code trong `app/`, `models/`, pipeline dữ liệu.
- Output: kết quả pass/fail và độ bao phủ.

## Lưu ý và giả định
- Người kiểm tra dữ liệu phải khác người làm dữ liệu.
- Mock CLIP trong test để CI không phải tải model nặng.

`test_ui.py` kiểm giao diện Streamlit bằng AppTest: một lần bấm một POST, không tự thử lại, các mức kết luận, lỗi HTTP và mất mạng, cách ly phiên, trang đánh giá; thêm hợp đồng với FastAPI thật (scorer giả). Cần `pip install -r streamlit/requirements.txt`. Chưa kiểm qua Nginx hay với model thật.

`test_ml_pipeline.py` kiểm chuẩn hóa JPEG/parity train-serve, ảnh nhỏ/ảnh điện thoại, fingerprint gắn version, cache sai model/đổi ảnh, xác suất không hợp lệ, cột AI theo `classes_`, và fit chỉ trên train. Bộ này chạy với `requirements.txt`, không cần `requirements-ml.txt`. Kiểm thử model thật được ghi riêng trong `docs/ml-handoff.md`.

Test chuẩn hóa spec 001 (ảnh tổng hợp + mock CLIP, không cần mạng, dataset hay trọng số):

| Mã task | File | Kiểm gì |
|---|---|---|
| T006 | `test_normalize.py` | `image` bằng JPEG giải mã; `jpeg` khớp công thức Pillow cũ; đầu ra xác định; SHA256 ghim cạnh `NORMALIZATION_VERSION` |
| T007 | `test_score_normalization.py` | `score` gọi `normalize_image` đúng một lần, không có tham số `resize`; đầu vào CLIP giống nhau giữa đường đĩa và đường API |
| T008 | `test_extract_features.py` | manifest ghi `norm_version`, `labels_norm_version`, `rows`; loader từ chối version hoặc số dòng lệch |
| T018 | `test_normalize_large.py` | 4000×3000 ra 256×256; bảng lượng tử JPEG quality 95; `save` đúng một lần; EXIF orientation áp trước resize |
| T020 | `test_too_small.py` | cạnh ngắn 255 bị `ImageTooSmall`, 256 qua; `resize=False` giữ 32×32; không phóng to |
| T016/T022 | `test_check_normalization.py` | logic `scripts/check_normalization.py` trên dữ liệu tổng hợp; chưa thay thế lần chạy trên raw thật |

Chạy riêng: `pytest tests/test_normalize.py tests/test_score_normalization.py tests/test_extract_features.py tests/test_normalize_large.py tests/test_too_small.py`.

Công cụ kiểm thử tích hợp KAN-29: `test_smoke_api.py` chạy `scripts/smoke_api.py` với server HTTP giả (stdlib, thread) cho kịch bản đúng hợp đồng (thoát 0), body/mã lỗi sai (thoát 1, nêu đúng ca), cổng đóng hoặc thiếu fixture (thoát 2); `test_make_fixtures.py` kiểm kích thước, EXIF, 0 byte, đúng 5.242.880 và +1 byte, sha256 giống nhau giữa hai lần sinh. Không cần mạng ngoài hay model; chưa thay thế lần smoke thật với `/v1/analyze` và model thật.

- Cột AI được kiểm cho cả `classes_=[0,1]` và `[1,0]` với hai xác suất khác nhau; hardcode cột 0 hoặc 1 đều làm test thất bại.
- Test recipe JPEG chỉ tái viết các lệnh Pillow trên ảnh tổng hợp. Chưa chạy code `prepare_data` cũ với baseline thật của Loan; T013 và lần chạy `check_normalization.py` trên raw độc lập (T016/T022/T030) vẫn chưa hoàn thành.
- `test_data_scripts.py`: chạy CLI chuẩn hóa với worker thật trên ảnh tổng hợp; kiểm chia tập, giữ test CIFAKE, loại trùng, tách CSV ảnh nhỏ/hỏng, chống ghi đè, lỗi ghi file, decompression bomb và checker bắt buộc `norm_version`.
- `test_verify_ml.py`: kiểm chính script audit bằng mock; chỉ chọn validation, ghi môi trường, fail khi byte JPEG/tensor/score sai hoặc encoder không frozen. Không tải torch hay weights trên CI.
- `test_run_info.py`: UUID phân biệt hai run dù đồng hồ trùng; không bịa commit nếu Git không có sẵn. CLI train cũng có test đối chiếu lệnh và hash artifact trong báo cáo.

Kiệt bổ sung regression test cho phần tích hợp của PR #15; Lực/Loan vẫn phụ trách review và kiểm chứng độc lập theo spec 001. Các test này không tự nghiệm thu phần việc QA.


- `test_inference.py`: kiểm `app/inference.py` (D11, D12; AC-20/21/22) bằng scorer giả điều khiển bằng Event: hết slot từ chối ngay, timeout giữ slot tới khi việc xong, hủy/lỗi không rò slot, không vượt số slot, event loop không bị chặn, loader lỗi, close(), không kéo torch. Một ca `xfail(strict=True)` ghi nhận giới hạn D12/FR-A04: process không thoát khi scorer treo vô hạn.

`test_performance_reporting.py` (KAN-56): parser `scripts/perf_report.py` và `scripts/check_performance.py` trên sidecar tổng hợp. Kiểm percentile chỉ trên 200, 429 không vào RPS thành công, ca chỉ 429, loại warmup (giây, số request, từ meta), sidecar rỗng/hỏng, thiếu SLO hoặc thiếu trường thì thoát khác 0. Không cần locust hay mạng; chưa thay thế lần đo thật qua `/v1/analyze`.

