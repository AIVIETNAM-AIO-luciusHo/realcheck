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

`test_ml_pipeline.py` kiểm chuẩn hóa JPEG/parity train-serve, ảnh nhỏ/ảnh điện thoại, fingerprint gắn version, cache sai model/đổi ảnh, xác suất không hợp lệ, cột AI theo `classes_`, và fit chỉ trên train. Bộ này chạy với `requirements.txt`, không cần `requirements-ml.txt`. Kiểm thử model thật được ghi riêng trong `docs/ml-handoff.md`.

- Cột AI được kiểm cho cả `classes_=[0,1]` và `[1,0]` với hai xác suất khác nhau; hardcode cột 0 hoặc 1 đều làm test thất bại.
- Test recipe JPEG chỉ tái viết các lệnh Pillow trên ảnh tổng hợp. Chưa chạy code `prepare_data` cũ với baseline thật của Loan; T012/T013 và `check_normalization.py` vẫn chưa hoàn thành.
- `test_data_scripts.py`: chạy CLI chuẩn hóa với worker thật trên ảnh tổng hợp; kiểm chia tập, giữ test CIFAKE, loại trùng, tách CSV ảnh nhỏ/hỏng, chống ghi đè, lỗi ghi file, decompression bomb và checker bắt buộc `norm_version`.
- `test_verify_ml.py`: kiểm chính script audit bằng mock; chỉ chọn validation, ghi môi trường, fail khi byte JPEG/tensor/score sai hoặc encoder không frozen. Không tải torch hay weights trên CI.
- `test_run_info.py`: UUID phân biệt hai run dù đồng hồ trùng; không bịa commit nếu Git không có sẵn. CLI train cũng có test đối chiếu lệnh và hash artifact trong báo cáo.

Kiệt bổ sung regression test cho phần tích hợp của PR #15; Lực/Loan vẫn phụ trách review và kiểm chứng độc lập theo spec 001. Các test này không tự nghiệm thu phần việc QA.

`test_ml_release.py` kiểm phần bổ sung cho KAN-39/44/51 bằng ảnh tổng hợp và mock CLIP: raw_path rỗng/trùng/alias, cache sai dtype/L2 dù checksum khớp, model không khớp manifest, protocol chưa duyệt hoặc bị đổi hash/ngưỡng, đánh giá không fit lại, dự đoán/metric theo source, marker ngăn replay và giữ lần lỗi. CLI chuẩn bị protocol không gọi predict. Không dùng GenImage test thật trong pytest.
