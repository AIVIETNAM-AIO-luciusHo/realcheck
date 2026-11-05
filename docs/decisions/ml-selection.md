# Manifest, holdout và ngưỡng được Kiệt chọn ngày 05/11/2026

## Trạng thái

**Cập nhật chỉ dẫn và kết quả:** sau khi biết QA độc lập chưa được duyệt, Kiệt yêu cầu trực tiếp “hãy làm đi” đối với việc train và chấm GenImage test. Đã thực hiện một lần thử nghiệm, giữ nguyên manifest/holdout/ngưỡng đã chọn: **test accuracy 94,53% trên 384 ảnh**. Protocol ghi `authorization_scope=user_authorized_experiment`, người cho phép là Kiệt và `independent_qa_approved=false`; không điền Loan/Lực đã duyệt và không coi đây là nghiệm thu release. Không chọn lại model/ngưỡng bằng test. Xem [kết quả, commit và lệnh thật](../ml-final-experiment.md).

Kiệt đã xác nhận lựa chọn để triển khai qua chat: **bản mới 9.708 ảnh giữ split của manifest 10.000**; test chỉ lấy ảnh chưa dùng train; dùng bảng ngưỡng dưới đây. Đây là lựa chọn của người phụ trách ML, không thay xác nhận độc lập về dữ liệu/audit hoặc phê duyệt release của nhóm. Reviewer dữ liệu/holdout: Loan/Lực theo phân công trong spec 001 và spec 000.

Nguồn repo cập nhật: main `0c1bdc4`, đã merge baseline của Loan (#24), dedup (#25), script đánh giá (#32), API và contract test (#31). Tại thời điểm kiểm tra, PR QA #23 còn OPEN, chưa có review và check lint/ci-ok đang fail; do đó không điền QA evidence giả hoặc tự đổi protocol sang approved.

## 1. Manifest đã chọn

- Raw 10.000 ảnh giữ nguyên; manifest 10.000 dùng làm tham chiếu split, không ghi đè.
- Candidate giữ split có 9.708 dòng, 292 ảnh nhỏ ghi riêng rejected; SHA256 labels `4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad` tại `../outputs/realcheck-preserved-split/labels.csv`.
- Bộ QA cũ SHA256 `72313cf272f101c84c757d25c29869af8d290743e2be3151b5c9aa6debeae8c5` vẫn dùng tái lập model/báo cáo cũ, không phải manifest mới vừa chọn.
- Có thể tạo lại candidate bằng `scripts.prepare_data --split-from data/labels.csv` với đúng các đường dẫn ở [bản đối chiếu](../ml-preserved-split.md). Đường dẫn output khác sẽ làm labels hash khác; phải khóa đúng file dùng train/evaluate.

## 2. Holdout theo lịch sử đang lưu

Giữ nguyên split trong manifest, thêm bản ghi lựa chọn phục vụ đánh giá; không chuyển các ảnh đã tiếp xúc sang train để làm mất dấu lịch sử.

```bash
python -m models.holdout --labels ../outputs/realcheck-preserved-split/labels.csv --history-labels .cache/ml-run/labels.csv --output ../outputs/realcheck-preserved-split/holdout-final-selection.json
```

Selector không tải CLIP, không fit và không dự đoán. Nó loại ảnh có cùng raw identity hoặc pixel chuẩn hóa với train/val của candidate hiện tại hay các lịch sử được cung cấp; loại bản trùng pixel trong test. Khác tên file hoặc metadata JPEG không làm ảnh đã học trở thành ảnh mới. Hash CSV lịch sử và digest pixel đã tiếp xúc được lưu để khóa bằng chứng.

Kết quả kiểm tra trên lịch sử đã cung cấp:

| Source | Test trước lọc | Đủ điều kiện | Bị loại vì train/val trước |
|---|---:|---:|---:|
| GenImage real | 399 | 65 | 334 |
| GenImage SD1.4 | 150 | 19 | 131 |
| GenImage GLIDE | 150 | 150 | 0 |
| GenImage Midjourney | 150 | 150 | 0 |
| **Tổng** | **849** | **384** | **465** |

Đây là đánh giá trên một **subset đã lọc lịch sử**, không được báo thành accuracy của toàn bộ 849 test. N=384 lệch lớp (65 real, 319 AI), riêng SD1.4 chỉ 19; báo kết quả theo source/N, FPR trên real và giới hạn cỡ mẫu. Chọn tập theo lịch sử trước khi biết score, không chọn theo dự đoán đúng/sai.

Selector chỉ chứng minh không trùng raw identity/pixel với các lịch sử được cung cấp; không thay review group/near-duplicate. Nếu thành viên khác đã train hoặc tune trên các ảnh này, phải bổ sung manifest lịch sử bằng cờ `--history-labels` lặp lại và chuẩn bị protocol mới trước khi mở test. Không khẳng định ảnh chưa từng xuất hiện trong pretraining CLIP hoặc các lần chạy không có bằng chứng.

## 3. D08: score, API và giao diện

Lựa chọn của Kiệt: binary metric cố định `0.5`; API low/high `0.3/0.7`; giao diện tách vùng uncertain tại `0.5`. Không tối ưu các mốc này bằng test.

| Điểm AI thô | API | Giao diện |
|---|---|---|
| `0 <= score < 0.3` | `likely_real` | Ảnh thật |
| `0.3 <= score < 0.5` | `uncertain` | Dự đoán thật |
| `0.5 <= score <= 0.7` | `uncertain` | Dự đoán AI |
| `0.7 < score <= 1` | `likely_ai` | Ảnh AI |

API quyết định trước khi làm tròn phần trăm; UI lấy verdict từ API và chỉ tách uncertain theo score. Tại đúng 30%, 50%, 70% API đều uncertain; 50%/70% giao diện là Dự đoán AI. Logic hiện có trong `app/verdict.py` và `streamlit/app.py` đã khớp bảng; không cần thêm enum thứ tư. Score không được diễn giải thành xác suất đã hiệu chuẩn hoặc cam kết ảnh thật/AI chắc chắn.

Accuracy/precision/recall/confusion matrix binary vẫn tính toàn bộ holdout đã khóa theo `score >= 0.5`, kể cả mẫu uncertain. Báo riêng uncertain rate và decided coverage; không bỏ uncertain để làm đạt 90%. Mục tiêu chất lượng theo AC-25 vẫn là accuracy binary >=90%, chưa đo nên chưa ghi đạt.

## 4. Thứ tự chạy tiếp theo

1. Loan/Lực review manifest, kiểm kê, audit metadata và lịch sử holdout. Hash baseline khớp không thay đầy đủ gate độc lập FR-D08/AC-25.
2. Sau xác nhận dữ liệu, KAN-44 trích features/train vào thư mục mới theo candidate đã chọn. Không lấy model/caches của manifest cũ để chấm candidate mới.
3. Chuẩn bị protocol bằng `models.evaluate --prepare-lock ... --history-labels .cache/ml-run/labels.csv`. Protocol khóa model/features/labels/ngưỡng cùng subset holdout và lịch sử; trạng thái ban đầu proposed, evidence/reviewer chưa tự điền.
4. Khi có phê duyệt thật, dùng `models.evaluate --lock ... --history-labels .cache/ml-run/labels.csv` đúng một lần. Omit/đổi lịch sử so với lock là lỗi trước prediction. Marker vẫn chống chạy lại vô ý; giữ log khi lỗi.

`scripts.evaluate --split val` của Loan tiếp tục dùng cho validation. GenImage `--split test` ở script này được chặn để mọi đường model-test dùng cùng protocol; CIFAKE smoke test vẫn có thể chạy riêng. Báo cáo `models.evaluate` có schema test/by_source/thresholds cho trang đánh giá và thêm provenance/holdout/predictions.

CLI `models.evaluate` bắt buộc truyền `--history-labels` khi chuẩn bị hoặc sử dụng lock. Không có cờ này thì dừng trước khi đọc model; không ngầm đánh giá cả 849 ảnh khi quên cung cấp lịch sử. Lịch sử khác hoặc bị bỏ qua so với protocol đã khóa bị từ chối trước prediction.

Phần chuẩn bị ban đầu chỉ chọn dữ liệu/kiểm code. Sau chỉ dẫn tiếp theo của người dùng, phần chạy KAN-44/KAN-51 đã có kết quả thử nghiệm thật tại commit `4a87e4a`; QA độc lập/release vẫn chưa được ghi approved. Tập 384 này nay đã mở, không được tune rồi gọi lại là holdout chưa tiếp xúc.

## Kiểm chứng local

Windows/Python 3.12.14: Ruff check và format đạt. `python -m pytest --cov=app --cov-fail-under=70 -q -rs`: **393 passed, 1 skipped**, coverage app **92,64%**. Test bị skip là `test_locustfile_voi_locust_that`, vì chưa cài dependency tùy chọn `locust/requirements.txt`; các test chọn holdout/ML không bị skip. Không trình bày kết quả local này thành CI Linux hoặc nghiệm thu QA độc lập.

Manifest lựa chọn không bị ghi đè, model/features/report cũ giữ nguyên. [Bằng chứng kiểm code ban đầu](../reports/ml-selection-verification.json) ghi đúng `git_dirty=true` ở giai đoạn đó. Các lần extract/train/verify/test thật sau chỉ dẫn mới chạy từ commit sạch `4a87e4a`; xem [biên bản thực thi và kiểm tra trước push](../ml-final-experiment.md).
