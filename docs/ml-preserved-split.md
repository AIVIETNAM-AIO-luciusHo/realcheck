# Bản ứng viên giữ ảnh gốc và split cũ

## Phạm vi và trạng thái

Kiệt bổ sung trên nhánh `kiet/ml-normalization-release` theo hướng đã đề xuất: giữ ảnh gốc, giữ split của ảnh còn hợp lệ theo manifest 10.000 dòng và ghi riêng ảnh không dùng. Loan phản hồi giữ ảnh cũ và ghi riêng ảnh không dùng; tùy chọn giữ split được chuẩn bị để Loan/Lực review, chưa tự coi là quyết định manifest phát hành đã được phê duyệt. Phần này liên quan dữ liệu đầu vào KAN-44/T024; KAN-37/KAN-39 giữ nguyên hợp đồng chuẩn hóa/CLIP, KAN-51 chưa chạy model-test.

Main đã được đồng bộ đến `c77603c`, nhận baseline T012 (PR #24), rejected_duplicate (PR #25) và API của Quang. KAN-41 làm giúp Lực vẫn ở nhánh riêng; không đưa các thay đổi chưa merge của nhánh đó vào nhánh ML.

## Ba bộ được giữ riêng

| Bộ | Công dụng | Thay đổi lần này |
|---|---|---|
| Raw và manifest 10.000 dòng trên main | Tham chiếu ảnh/split trước migration | Không ghi đè hoặc xóa ảnh |
| Candidate QA 9.708 dòng cũ, `.cache/ml-run/labels.csv` | Tái lập model và báo cáo đã bàn giao | Giữ nguyên manifest, features và model |
| Candidate giữ split cũ 9.708 dòng | Đối chiếu và chuẩn bị manifest mới để review | Tạo riêng; 0 ảnh hợp lệ đổi split so với manifest 10.000 |

Raw bị loại vẫn nằm nguyên trong `data/raw`. Manifest ứng viên chỉ chứa ảnh hợp lệ; 292 ảnh nhỏ nằm trong `rejected_small.csv`, không vừa kept vừa rejected. Rejection invalid/duplicate lần này có header nhưng 0 dòng. Không thêm cờ used/unused vào schema labels chung.

## Cách tạo lại

Chạy từ gốc repo, dùng raw đúng cohort 10.000 của manifest tham chiếu và thư mục output chưa tồn tại:

```bash
python -m scripts.prepare_data --split-from data/labels.csv --output-dir .cache/ml-preserve/processed --labels .cache/ml-preserve/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-preserve/labels.csv
```

`--split-from` khớp theo raw identity, kiểm đủ cohort/nhãn/source và split hợp lệ trước khi ghi output; không chia mới để bù tỷ lệ sau khi loại ảnh. Thứ tự dòng tham chiếu không ảnh hưởng split. Test gốc CIFAKE không được chuyển sang train/val hoặc ngược lại. Hash tham chiếu in vào log và được kiểm lại trước khi ghi labels. Không truyền cờ này thì hành vi chia seed 42 cũ giữ nguyên để tái lập các run trước.

Đường dẫn thực của lần chuẩn bị local là `../outputs/realcheck-preserved-split/labels.csv`, processed/rejected cùng thư mục output. CSV tham chiếu trên Windows có SHA256 `7a83b1c7c5be7f09463e34cc02254db1c4eeb8b4efbacbb2ca1c7783beabe3ee`; chuyển CRLF thành LF cho SHA256 `dac186082dd3506bc91acda7cdd6ed5bb68b083e2ed7f445d7e89edc16d67931`, khớp header baseline Loan. Không sửa file tham chiếu để ép hash khớp; model/cache dùng hash bytes thực đã đọc.

## Kết quả trên dữ liệu thật

| Source | Train | Val | Test | Loại nhỏ |
|---|---:|---:|---:|---:|
| CIFAKE AI | 850 | 150 | 1.000 | 0 |
| CIFAKE real | 850 | 150 | 1.000 | 0 |
| GenImage GLIDE | 700 | 150 | 150 | 0 |
| GenImage Midjourney | 700 | 150 | 150 | 0 |
| GenImage real | 1.888 | 421 | 399 | 292 |
| GenImage SD1.4 | 700 | 150 | 150 | 0 |
| **Tổng** | **5.688** | **1.171** | **2.849** | **292** |

- 9.708 kept + 292 rejected = 10.000 raw; không lost/overlap. Ảnh giữ lại không đổi label/source/split so với manifest 10.000.
- So với manifest QA 9.708 cũ, có 1.702 ảnh đổi split. Hai manifest 9.708 có cùng tập ảnh nhưng không dùng thay thế nhau cho model/báo cáo.
- Kiểm 9.708 file JPEG output với hash tương ứng trong baseline Loan: 0 lệch. 10.000 hash baseline Loan cũng khớp tham chiếu code cũ đã tái lập trước đó; không thay biên bản review T013 của nhóm.
- `check_data`: exit 0, 0 lỗi, 0 cảnh báo. Checker normalization: exit 0, 9.708/9.708 matched, inventory 10.000/9.708/292.
- Vì output ở thư mục mới, checker chạy bằng một bản view baseline chỉ ánh xạ đường dẫn processed sang đường dẫn candidate. Mọi expected hash lấy nguyên từ `data/processed_baseline.sha256`, không tính lại từ output mới. View có header ghi SHA256 baseline gốc; baseline chính không thay đổi.

Số liệu/hash chi tiết: [ml-preserved-split.json](reports/ml-preserved-split.json). Không có accuracy/AUROC hoặc score model mới trong báo cáo này.

## Giới hạn holdout cần chốt trước KAN-44/KAN-51

GenImage của candidate giữ split có 3.988 train, 871 val, 849 test. Trong 849 test đó:

| Source | Từng ở train của bản QA cũ | Từng ở val của bản QA cũ | Từng ở test của bản QA cũ |
|---|---:|---:|---:|
| GLIDE | 0 | 0 | 150 |
| Midjourney | 0 | 0 | 150 |
| real | 275 | 59 | 65 |
| SD1.4 | 108 | 23 | 19 |
| **Tổng** | **383** | **82** | **384** |

Giữ split cũ giúp kiểm soát thay đổi cohort/split, nhưng không xóa lịch sử 383 ảnh đã dùng fit và 82 ảnh đã dùng chọn model. Không coi candidate này là holdout chưa tiếp xúc của quá trình phát triển. Nhóm cần xác nhận mục đích thí nghiệm và holdout phát hành độc lập trước khi đo chất lượng; không mở test để chọn phương án có số đẹp hơn.

Nếu phê duyệt manifest mới, cần trích features/train model vào thư mục mới theo KAN-44: dù JPEG không đổi, labels hash và membership train/val/test đã đổi nên artifact cũ không khớp. KAN-51 vẫn cần model/manifest/ngưỡng khóa và QA/audit/holdout review. Chưa chạy các bước này trong lần chuẩn bị này.

## Kiểm thử và phạm vi bàn giao

- Windows, Python 3.12.14; `ruff check .` đạt, `ruff format --check .`: 76 file đúng format.
- `python -m pytest tests/test_data_scripts.py -q`: 24 passed, gồm 14 ca mới cho giữ split và đầu vào lỗi.
- `python -m pytest --cov=app --cov-fail-under=70 -q`: 192 passed, 0 failed, 0 skipped; app coverage 72,09%. App trên main mới có thêm inference/uploads, nên số coverage không so trực tiếp với 98,31% của app cũ.
- 10 ca đặc tả CLI đã fail trước khi thêm tùy chọn, pass sau sửa; bốn ca bổ sung kiểm identity/CIFAKE/reference thay đổi. Không cần mạng/GPU/model thật để chạy pytest.
- Report local được tạo trên working tree có sửa đổi (`git_dirty=true`), kèm hash code prepare_data; chưa trình bày thành run của release commit sạch hoặc chứng nhận CI Linux.
- Chỉ nhận thay đổi đã merge của Loan/Quang từ main, không thay baseline, API, tham số chuẩn hóa/version hoặc artifact QA cũ. Phần tùy chọn split cần Loan/Lực review theo phân công pipeline.
