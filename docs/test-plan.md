# Kế hoạch test tuần 1

Nguồn: [spec nền tảng hệ thống](../specs/000-realcheck-system-baseline/spec.md), [spec chuẩn hóa ảnh](../specs/001-unified-image-normalization/spec.md), [quyết định kỹ thuật](decisions/realcheck-baseline.md) và tiêu chí Q1 của KAN-26 trên Jira ("Xây dựng kế hoạch test và quy trình báo lỗi").

Bản đầu viết ngày 2026-10-29, trước khi nhóm chốt D05–D07; bản này cập nhật theo trạng thái của `main` ngày 2026-11-05 (commit `a30cfe0`).

## 1. Phạm vi và mục tiêu

Kiểm tra ba thứ: API `/v1/analyze`, nhánh quyết định `verdict`, và dữ liệu huấn luyện. Mục tiêu: có bộ test chạy lại được, tiêu chí pass/fail rõ, và mẫu báo lỗi thống nhất ([`bug-report-template.md`](bug-report-template.md)).

Quy tắc chung:

- Nhãn: `real` = 0, `ai` = 1. `score` càng gần 1 càng giống ảnh AI.
- Giá trị `verdict` của API (D05, đã duyệt) là enum máy đọc: `likely_real`, `uncertain`, `likely_ai`. Quy tắc theo `app/verdict.py` với ngưỡng mặc định trong `app/settings.py` (`threshold_low` = 0.3, `threshold_high` = 0.7):
  - `score` < 0.3: `likely_real`.
  - 0.3 <= `score` <= 0.7 (gồm cả hai biên): `uncertain`.
  - `score` > 0.7: `likely_ai`.
- Nhãn trên giao diện Streamlit không phải giá trị API. "Ảnh thật" và "Ảnh AI" ứng với `likely_real` và `likely_ai`; riêng `uncertain` được giao diện tách thành "Dự đoán thật" (`score` < 0.5) và "Dự đoán AI" (`score` >= 0.5) kèm dòng "Phân loại: Chưa chắc" (`streamlit/app.py`). Test API và verdict dùng giá trị enum, không dùng nhãn giao diện.
- Ngưỡng hiển thị D08 (Kiệt chọn 0.3/0.5/0.7) vẫn ở trạng thái `proposed`, xem mục 5.
- EXIF chỉ là bằng chứng phụ, không quyết định `verdict`.
- Người làm dữ liệu không tự viết test dữ liệu của mình; QA kiểm tra để người kiểm tra khác người làm.
- CI xanh không thay thế việc đọc số test thật và coverage. Phần "Kết quả kiểm chứng" của PR template ghi số test thực sự chạy, có bị skip không và coverage; test chưa được QA kiểm độc lập thì không ghi "đạt".

### Mã lỗi (D05, đã duyệt)

Mọi lỗi trả envelope `{"error": {"code", "message", "request_id"}}` và header `X-Request-ID`. Nguồn: [`decisions/realcheck-baseline.md`](decisions/realcheck-baseline.md), `app/errors.py`.

| HTTP | `code` | Khi nào |
|---|---|---|
| 400 | `EMPTY_FILE` | File 0 byte |
| 400 | `INVALID_IMAGE` | Không đọc được ảnh (text giả `.jpg`) hoặc ảnh bị cắt cụt |
| 413 | `FILE_TOO_LARGE` | Vượt 5.242.880 byte (D06) |
| 413 | `TOO_MANY_PIXELS` | Vượt 24 MP hoặc cạnh vượt 10.000 px (D07) |
| 415 | `UNSUPPORTED_FORMAT` | Không phải JPEG/PNG, hoặc nhiều khung hình |
| 422 | `MISSING_FILE` | Thiếu trường `file` |
| 422 | `MULTIPLE_FILES` | Nhiều hơn một file |
| 422 | `IMAGE_TOO_SMALL` | Cạnh ngắn < 256 px |
| 422 | `INVALID_REQUEST` | Yêu cầu sai khác |
| 404 / 405 | `NOT_FOUND` / `METHOD_NOT_ALLOWED` | Sai đường dẫn / phương thức |
| 500 | `MODEL_ERROR`, `INTERNAL_ERROR` | `score` lỗi hoặc ngoài [0, 1]; lỗi khác, không lộ stacktrace |
| 503 | `MODEL_NOT_READY`, `SERVICE_BUSY` | Model chưa sẵn sàng; hết slot suy luận |
| 504 | `MODEL_TIMEOUT` | Quá thời gian xử lý (10 giây, D11 duyệt tạm) |

## 2. Bảng test case

Cột "Tự động hóa / bằng chứng" chỉ ghi test hoặc script có thật trong repo. Ghi "chưa tự động hóa" hoặc "thủ công" khi không có. Tên dạng `file::ca` là ca pytest; một số ca được tham số hóa nên chạy nhiều lần.

| Mã | Nhóm | Mô tả | Đầu vào/dữ liệu | Kết quả mong đợi | Pass/Fail khi nào | Người phối hợp | Tự động hóa / bằng chứng |
|---|---|---|---|---|---|---|---|
| TC-01 | API | Ảnh hợp lệ trả đủ trường | 1 ảnh JPEG (và PNG) hợp lệ, có EXIF | HTTP 200, JSON đúng bốn trường `verdict`, `score`, `exif`, `reason`, không trường thừa | Pass nếu đủ và không thừa; Fail nếu thiếu hoặc thừa trường | Quang (Backend) | `tests/test_analyze.py::test_200_bon_truong_dung_hop_dong`; `tests/test_schemas.py::test_analyze_response_hop_le`, `tests/test_schemas.py::test_cam_truong_thua`; `scripts/smoke_api.py` (kiểm tay bằng server thật, xem mục 3) |
| TC-02 | API | `score` nằm trong [0,1] | Ảnh hợp lệ; scorer giả trả giá trị lỗi | 0 <= `score` <= 1; `score` ngoài khoảng, NaN, vô cực bị chặn thành 500 `MODEL_ERROR` | Fail nếu có `score` ngoài khoảng được trả ra | Quang | `tests/test_schemas.py::test_score_bien_hop_le`, `tests/test_schemas.py::test_score_ngoai_0_1_hoac_nan_bi_tu_choi`; `tests/test_analyze.py::test_500_model_error_va_khong_lo_chi_tiet` |
| TC-03 | API | Thiếu file | Gọi `/v1/analyze` không đính kèm file (hoặc không có body) | 422 `MISSING_FILE`, đúng envelope | Pass nếu đúng mã HTTP và `code`; Fail nếu 200 hoặc 500 | Quang | `tests/test_analyze.py::test_422_missing_file_khong_co_truong_file`, `tests/test_analyze.py::test_422_missing_file_khong_co_body` |
| TC-04 | API | File giả ảnh | File nội dung text, đặt tên `.jpg` | 400 `INVALID_IMAGE`, không gọi model, không crash | Pass nếu đúng mã và model không bị gọi; Fail nếu 500 hoặc trả `verdict` | Quang | `tests/test_analyze.py::test_400_invalid_image_text_gia_jpg`; ca liên quan: `tests/test_analyze.py::test_400_empty_file`, `tests/test_analyze.py::test_400_invalid_image_bi_cat_cut`, `tests/test_analyze.py::test_scorer_khong_duoc_goi_voi_dau_vao_khong_hop_le` |
| TC-05 | API | Ảnh thiếu EXIF | Ảnh JPEG/PNG đã xóa EXIF | Vẫn xử lý được (200); `exif` bằng hằng `MISSING_EXIF` trong `app/verdict.py`, hiện là "Không có thông tin máy chụp" | Pass nếu 200 và `exif` đúng hằng; EXIF không đổi `verdict` | Quang | `tests/test_analyze.py::test_khong_exif_van_tra_verdict_va_exif_mac_dinh`; `tests/test_analyze.py::test_exif_khong_doi_verdict`; `tests/test_verdict.py::test_hang_missing_exif` |
| TC-06 | Verdict | Vùng `likely_real` | `score` = 0.1 | `likely_real` | Pass nếu đúng giá trị | Quang | `tests/test_verdict.py::test_decide_verdict_bien_theo_D05_proposed`; `tests/test_analyze.py::test_verdict_theo_score_tiem_vao` (mock scorer trả `score`) |
| TC-07 | Verdict | Vùng `uncertain` | `score` = 0.5 | `uncertain` | Pass nếu đúng giá trị | Quang | Như TC-06 |
| TC-08 | Verdict | Vùng `likely_ai` | `score` = 0.9 | `likely_ai` | Pass nếu đúng giá trị | Quang | Như TC-06 |
| TC-09 | Verdict | Biên dưới | `score` = 0.3 | `uncertain` (biên thuộc vùng giữa) | Fail nếu ra `likely_real` | Quang | Như TC-06 (ca 0.3) |
| TC-10 | Verdict | Biên trên | `score` = 0.7 | `uncertain` (biên thuộc vùng giữa); 0.700001 ra `likely_ai` | Fail nếu 0.7 ra `likely_ai` | Quang | Như TC-06 (ca 0.7 và 0.700001) |
| TC-11 | Dữ liệu | Nhãn khớp thư mục | `labels.csv` và thư mục ảnh | Dòng có `source` kết thúc `_real` có `label` 0, còn lại 1; thư mục chứa ảnh khớp `source` | Fail nếu có dòng lệch | Loan (Data) | `scripts/check_data.py` (bước 2); chạy trong `tests/test_data_scripts.py::test_prepare_and_check_data_cli_rejections_splits_and_overwrite` (dữ liệu tổng hợp). Chưa có test độc lập chạy trên dữ liệu thật |
| TC-12 | Dữ liệu | Đủ cột `labels.csv` | `labels.csv` | Đúng sáu cột `filepath,label,source,split,raw_path,norm_version`; `norm_version` đúng version hiện hành; không ô trống | Fail nếu thiếu cột, sai thứ tự hoặc sai version | Loan | `scripts/check_data.py` (bước 1); `tests/test_data_scripts.py::test_check_data_cli_requires_current_norm_version`. Lưu ý: `data/labels.csv` đang commit là bản cũ năm cột (không có `norm_version`) và sẽ không qua checker hiện hành, xem mục 5 |
| TC-13 | Dữ liệu | Không trùng giữa các split | `labels.csv` và ảnh | Không ảnh nào trùng hệt giữa train và val/test (so dHash); ảnh gần trùng chỉ cảnh báo; ảnh trùng pixel bị loại khi chuẩn bị dữ liệu | Fail nếu có ảnh trùng hệt (GenImage); CIFAKE 32×32 và gần trùng chỉ là cảnh báo | Loan | `scripts/check_data.py` (bước 5); `tests/test_data_scripts.py::test_prepare_records_duplicates_and_leaves_no_lost_image`, `tests/test_data_scripts.py::test_prepare_duplicate_hashes_remove_conflicting_labels`. Chưa có test chạy trên dữ liệu thật |
| TC-14 | Dữ liệu | Ảnh đọc được | Toàn bộ ảnh trong `labels.csv` | Mọi ảnh mở được, là JPEG RGB | Fail nếu có ảnh hỏng/không mở được | Loan | `scripts/check_data.py` (bước 3, 4); `tests/test_data_scripts.py::test_check_images_reports_decompression_bomb` |
| TC-15 | Dữ liệu | Đồng nhất định dạng/kích thước/chất lượng JPEG và metadata | Toàn bộ ảnh | Cùng JPEG chất lượng 95, RGB, không EXIF, 256×256 (GenImage) hoặc 32×32 (CIFAKE); metadata không phân biệt được real và ai: `A_eff = max(AUROC, 1-AUROC) <= 0.55` | Fail nếu sai định dạng/kích thước hoặc vượt ngưỡng `A_eff` | Loan | `scripts/check_data.py` (bước 4); `scripts/metadata_audit.py` ra `data/metadata_audit.json` (thủ công); tham số chuẩn hóa: `tests/test_normalize.py::test_parameters_pinned_by_fingerprint_next_to_version`, `tests/test_normalize_large.py::test_quantization_tables_match_jpeg_quality_95_not_other_qualities`. `scripts/metadata_audit.py` chưa có test pytest; probe và cỡ mẫu (D03/D04) đang dùng giá trị tạm |
| TC-16 | Dữ liệu | Chạy lại cho cùng kết quả | Chạy pipeline dữ liệu 2 lần (seed 42) | `labels.csv` và split giống nhau | Fail nếu khác | Loan | Chưa tự động hóa: không có test so sánh hai lần chạy `scripts/prepare_data.py`. Chỉ có tài liệu seed trong `data/README.md` và test giữ split khi chuẩn bị từ manifest tham chiếu (`tests/test_data_scripts.py::test_prepare_preserves_reference_splits_and_raw_files`) |
| TC-17 | Dữ liệu | Baseline kích thước file | Chỉ dùng một đặc trưng: dung lượng file (KB) | Ghi lại độ chính xác cân bằng (balanced accuracy) theo từng nguồn; đoán mò là 50% | Theo `data/README.md`, đây là số tham khảo về độ chi tiết ảnh, không phải gate. Báo cáo kèm giải thích nếu cao hơn hẳn 50% (nguy cơ model học độ mịn thay vì nội dung) | Loan | `scripts/baseline_filesize.py` ra `data/baseline_filesize.json` (thủ công); chưa có test pytest |

Ca ngoài TC-01..17 đã có test cho từng mã lỗi D05: `tests/test_analyze.py` (các ca `test_413_*`, `test_415_*`, `test_422_image_too_small*`, `test_422_multiple_files`, `test_503_model_not_ready_khi_scorer_none`, `test_404_not_found`, `test_405_method_not_allowed_co_allow`) và `tests/test_errors.py::test_error_table_phu_het_error_code`. Đây là bằng chứng bổ sung, không thuộc danh sách TC của tuần 1.

## 3. Test tuần 1 và kiểm thử sau

Tuần 1 gồm TC-01 đến TC-17. Phần dưới là giai đoạn sau.

Công cụ đã có trên `main` nhưng chưa có số đo thật (chờ server KAN-55 và model được nối vào API):

- Locust (`locust/baseline.conf`, `locust/rate_only.conf`, `locust/locustfile.py`): baseline (rate thấp, p95/RPS của request 200 đúng schema) và rate-only (chỉ quan sát 429).
- Parser `scripts/perf_report.py` và so SLO `scripts/check_performance.py`; test trên sidecar tổng hợp tại `tests/test_performance_reporting.py`. SLO chưa được ký nên chưa kết luận đạt hay không.
- Kiểm thử khói HTTP `scripts/smoke_api.py` với ảnh mẫu từ `scripts/make_fixtures.py`; test của chính công cụ ở `tests/test_smoke_api.py`, `tests/test_make_fixtures.py`. Chưa chạy với `/v1/analyze` và model thật.

Vẫn là giai đoạn sau, chưa làm:

- Stress, soak và tải xác nhận (profile tải: D14).
- Chống phá: ảnh pixel cực lớn qua Nginx, gửi liên tục để kiểm tra 429 (rate-only mới có công cụ, chưa có số đo).
- Độ bền mô hình: xoay, cắt viền, thu nhỏ, chỉnh sáng ảnh, xem kết luận có bị lật không.
- Nginx (giới hạn tốc độ, kích thước, lỗi 413/429 cùng envelope).
- Kiểm tra dấu vết JPEG (T027, KAN-46): script chưa có, chờ nhóm xác nhận phương pháp JPEG ghost.

Test tuần 1 khác kiểm thử tải và chống phá ở chỗ: chạy được trên CI, không cần server thật, model thật hay mạng, và kiểm hành vi đúng sai của hợp đồng, không đo hiệu năng.

## 4. Tiêu chí đạt của kế hoạch này

Ánh xạ năm tiêu chí của KAN-26 (Q1) tới tài liệu. Đối chiếu lại với Jira khi review.

| Tiêu chí | Nằm ở |
|---|---|
| Có ca ảnh hợp lệ, file giả, thiếu EXIF | TC-01, TC-04, TC-05 (mục 2) |
| Có kiểm nhãn và split | TC-11, TC-12, TC-13 (mục 2) |
| Có tiêu chí pass/fail | Cột "Pass/Fail khi nào" (mục 2), quy tắc verdict và bảng mã lỗi (mục 1) |
| Mẫu báo lỗi có bước tái hiện, mong đợi, thực tế, bằng chứng | [`bug-report-template.md`](bug-report-template.md) |
| Phân biệt test tuần 1 với kiểm thử tải và chống phá | Mục 3 |

## 5. Điểm chưa chốt

Đọc theo [`decisions/realcheck-baseline.md`](decisions/realcheck-baseline.md) và spec 000, 001:

- D11 (timeout 10 giây) và D12 (1 slot, không xếp hàng) mới là "approved tạm"; xem lại sau benchmark, chưa đo trên model thật. D07 (24 MP) cũng chưa đo RAM.
- D08 (ngưỡng score/hiển thị 0.3/0.5/0.7) là `proposed`, chờ review release.
- Hợp đồng `score` (`models/score.py`, `score(image) -> float`) là `proposed`, chờ Kiệt và Lực.
- D14 (profile tải, thời lượng soak) còn `[NEEDS CLARIFICATION]` trong spec 000.
- Phần body dư cho multipart (64 hoặc 128 KiB) thuộc cấu hình Nginx, chưa chốt.
- Split và manifest chính thức còn chờ nhóm xác nhận. `data/labels.csv` đang commit là bản cũ (năm cột), bản mới nằm trong luồng `.cache/ml-run` mô tả tại `data/README.md`.
- Probe, protocol và cỡ mẫu tối thiểu của audit metadata (D03/D04) đang dùng giá trị tạm.
- Phương pháp JPEG ghost (KAN-46, T027) chờ nhóm xác nhận.
- D05 đã `approved`; ranh giới 400/415 và ba mã bổ sung (`NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INVALID_REQUEST`) đã ghi là đã duyệt. Repo không có danh sách câu hỏi D05 còn mở.

## 6. Mục tiêu dự án và số đo hiện có

Mục tiêu theo kế hoạch nhóm: ít nhất 15 test pytest; coverage thư mục `app/` từ 70%.

Số đo thật, chạy ngày 2026-11-05 trên `main` commit `a30cfe0`, Python 3.12.3, cài `requirements.txt` và `streamlit/requirements.txt` (CI dùng Python 3.11):

```text
pytest --cov=app --cov-fail-under=70
471 passed, 1 skipped, 1 xfailed
app/ coverage: 98.47% (326 câu lệnh, 5 chưa phủ)
```

Số này đo local, không phải số lấy từ log CI. `xfail(strict=True)` là giới hạn D12 đã ghi nhận (process không thoát khi scorer treo vô hạn). Coverage chỉ đo `app/`, không đo `models/` hay `scripts/`.
