# Chạy thử chuỗi robustness trên dữ liệu tổng hợp (12/11/2026)

Liên quan: GitHub #49 (ADV-05, QA review), #51 (ADV-07, biến thể và `--robustness`), #52 (ADV-08, chạy và phân tích). Người kiểm: QA (Lực) qua Tester độc lập. **Không có số đo robustness thật ở đây**: chỉ kiểm rằng chuỗi nối thông và từ chối đúng.

## Phạm vi

Chuỗi gồm ba bước: (1) tạo biến thể và cohort (`scripts.robustness_manifest`, PR #74); (2) chấm bằng `python -m scripts.evaluate --robustness` với model e571 thật (PR #74); (3) phân tích bằng `scripts.analyze_robustness` (PR #64): flip rate và degradation so với ảnh cha, bootstrap theo group. Dữ liệu: 12 ảnh cha tổng hợp (JPEG và PNG, 2 nguồn, hai ảnh cha cùng group), 3 cohort nhỏ (`phone`, `ai_new`, `zalo`). Tổng 104 ảnh. Chỉ ảnh tổng hợp, không đụng ảnh GenImage.

Khi chạy thử, #64 chưa merge nên Tester dựng bước 3 bằng cách đè 5 file của #64 lên bản `main` (trong repo tạm). #64 đã merge sau đó; kết quả bước 3 chưa chạy lại trên `main` thuần.

## Kết quả

| Bước | Kết quả |
|---|---|
| Biến thể và cohort | Đạt: 7 biến thể mỗi ảnh cha, con giữ `group_id`, nhãn, nguồn của cha; cạnh ngắn không dưới 256 |
| Preflight (`--preflight`) | Đạt, thoát 0 |
| `evaluate --robustness` | Đạt: 104/104 `ok`, đúng 11 cột contract ADV-08; ghi `predictions.csv`, `.run.json` và `<protocol>.used.json` |
| `analyze_robustness` | Đạt, thoát 0 khi đủ cohort |
| Thiếu cohort | `incomplete`, thoát 1; `metrics`, `ci95`, `pairing` null, N bằng 0: không bịa số |
| Số học | Flip rate và degradation khớp tính lại bằng pandas ở cả 7 loại biến thể và Zalo (trên file dự đoán tự dựng có điểm ngẫu nhiên) |
| Từ chối: sửa 1 bit ảnh | Bị chặn (preflight thoát 2). Runner từ chối nhưng **muộn**; đã sửa ở PR #86 |
| Từ chối: sửa ngưỡng trong protocol | `Protocol refused: thresholds differ from the model`, thoát 2, không tạo `.used.json` |
| Từ chối: chạy lần hai cùng protocol | `Protocol already used`, thoát 2 |

Một `protocol.json` dùng được cho cả runner và analyzer; analyzer đòi thêm `runner.commit`, `analysis_commit`, `history`, `parent_exposure`, `bootstrap`, runner không đọc các trường này.

## Điểm lệch còn lại

| Mức | Vấn đề | Trạng thái |
|---|---|---|
| Nên sửa | Runner kiểm hash ảnh sau khi nạp CLIP và ghi `.used.json`; một ảnh lệch đốt protocol | **Đã sửa, PR #86** |
| Nên sửa | Bước biến thể xuất 4 file JSONL riêng, runner chỉ nhận một manifest, không có lệnh gộp; phải `cat` tay và tự chép `n_expected`, `transform`, hash vào protocol; đường dẫn ảnh chỉ đúng khi các file cùng thư mục | Chưa sửa (nhận xét ở #51) |
| Nên sửa | `n_clamped_geometry` chỉ đếm khi kích thước giữ nguyên: cha 400×400 có downscale thực tế 0,64 vẫn báo 0 ảnh bị cắt | Chưa sửa (nhận xét ở #51) |
| Nit | Analyzer chấp nhận `predictions.csv` bị sửa điểm nếu verdict vẫn nhất quán | Chưa sửa |
| Nit | Runner không kiểm `runner.commit`, `analysis_commit`, `history` (chỉ analyzer kiểm) | Chưa sửa |
| Nit | Analyzer từ chối checkout "bẩn", kể cả `__pycache__` chưa ignore (dùng `PYTHONDONTWRITEBYTECODE=1`) | Chưa sửa |
| Nit | Không có gì chống xóa `.used.json` (tài liệu cấm xóa) | Chưa sửa |

## Checklist trước khi chạy thật (mỗi protocol chỉ chấm một lần)

1. Manifest cohort và biến thể đã gộp thành **một** file; hash ảnh khớp (đã có kiểm trước khi nạp model từ PR #86).
2. `data/labels.csv` hoặc manifest cha có `group_id` (hiện `labels.csv` chưa có cột này; cần cho AC-18).
3. Protocol `status: locked`, đủ `manifest_lock_ref` và `split_review_ref`, hash model, model manifest, manifest khớp; ngưỡng 0,3/0,5/0,7 khớp model; mọi cohort có mặt đã đăng ký với cùng `transform`.
4. Ảnh cha thuộc split `test`: tập test GenImage đã mở một lần (384 ảnh holdout). Số robustness chỉ ghi để báo cáo suy giảm của model đã khóa, **không** dùng để chọn lại model hay ngưỡng (AC-26).
5. Cohort chưa thu được (điện thoại, AI mới, Zalo ở #50) phải đăng ký là thiếu; kết quả `incomplete` là hợp lệ và phải ghi trong báo cáo, không điền số giả.
6. Chạy từ checkout sạch, đúng commit ghi trong protocol, với `PYTHONDONTWRITEBYTECODE=1`.
7. Sau khi chạy: không xóa `<protocol>.used.json`; lưu `predictions.csv`, `.run.json`, và đầu ra analyzer; QA chạy lại phần phân tích độc lập từ `predictions.csv` trước khi báo cáo.

## Giới hạn

- Model thật cho mọi ảnh tổng hợp điểm 0,94 đến 0,999 (đều "AI"), nên flip và degradation thật đều bằng 0; chưa quan sát được flip thật từ model thật.
- Chưa chạy analyzer trên `main` thuần sau khi #64 merge; chưa kiểm near-duplicate hay lịch sử thật (`history.csv` tự dựng 3 dòng).
- Chưa có ba cohort thật (#50), chưa có `group_id` cho `labels.csv`, nên chuỗi chưa chạy được số đo thật.
