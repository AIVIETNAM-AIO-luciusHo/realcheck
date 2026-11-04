# Bàn giao ML – KAN-16 đến KAN-20

Ngày chạy ban đầu: 04/11/2026; cập nhật sau review: 05/11/2026. Người phụ trách: Kiệt. Nhánh `kiet/clip-vit-b32-ml` đã rebase lên `origin/main` tại `43caa16` (thêm ba commit Streamlit và merge commit), không conflict. Nguồn gốc báo cáo cũ, commit/lệnh của lần chạy lại và môi trường nằm trong [hồ sơ tái lập](ml-reproducibility.md). Phần OpenCode nằm ngoài phạm vi.

## Phạm vi đã thực hiện

| Task | Kết quả và bằng chứng |
|---|---|
| KAN-16 – Chuẩn bị CLIP, thống nhất đầu vào | Nạp đúng `sentence-transformers/clip-ViT-B-32`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`, bằng `SentenceTransformer`; eval, tắt gradient, embedding 512 chiều L2. Chuẩn hóa chung theo spec 001, version `1` |
| KAN-17 – CIFAKE + Logistic Regression | Chạy 4.000 ảnh CIFAKE, train/validation/test riêng, xuất model chạy thử và [số đo CIFAKE](reports/ml-cifake.json) |
| KAN-18 – Đặc trưng GenImage | Trích đủ 5.708 ảnh GenImage cùng 4.000 CIFAKE; `features.npy` shape `(9708,512)`, float32; manifest kiểm row order, hash dữ liệu và model/version |
| KAN-19 – Train và đánh giá ban đầu | Train LR GenImage trên 3.996 ảnh, chọn C trên 856 validation; accuracy 95,68% chưa loại trừ shortcut dung lượng file/độ mịn/dấu vết JPEG. [Báo cáo validation](reports/ml-genimage.json); 856 test GenImage chưa chấm điểm, T027 chưa có |
| KAN-20 – Bàn giao score | Có `models/clip_probe.joblib`, checksum, `load_model()` và `score(PIL.Image)->float`; kiểm thử model thật/parity trong [biên bản tích hợp](reports/ml-integration.json). Quang tiếp nhận tích hợp HTTP, Lực review độc lập |

Đây là kết quả triển khai và chạy thí nghiệm cục bộ, chưa phải xác nhận QA/reviewer đã nghiệm thu các task Jira hoặc bản phát hành. Không cập nhật trạng thái Jira.

## Model và dữ liệu đang có trên máy

| Đường dẫn từ gốc repo | Nội dung |
|---|---|
| `models/clip_probe.joblib` | Probe GenImage + metadata + ngưỡng + phiên bản dependency |
| `models/clip_probe.joblib.sha256` | `69810fd60940ddeed07af92d600c6bb0466641bf4144aec73554b44013ae7bdb` |
| `models/cifake_probe.joblib` | Probe chỉ để thử CIFAKE, loader Backend từ chối |
| `.cache/huggingface/` | Trọng số CLIP đã tải, dùng `HF_HOME` để tái sử dụng |
| `data/raw/` | 10.000 ảnh gốc từ script download hiện có, giữ nguyên bytes |
| `.cache/ml-run/processed-v1/` | 9.708 JPEG chuẩn hóa, có `rejected_small.csv` |
| `.cache/ml-run/labels.csv` | Manifest mới có `norm_version`; SHA256 `72313cf272f101c84c757d25c29869af8d290743e2be3151b5c9aa6debeae8c5` |
| `data/features/features.npy`, `manifest.json` | Đặc trưng và thông tin kiểm tra tính khớp dữ liệu |

Ảnh, features, cache và joblib không nằm trong Git. Các báo cáo JSON nhỏ trong `docs/reports/` có thể review cùng code. Khi bàn giao sang máy khác cần chuyển **cả joblib lẫn file checksum**, cài dependency theo `models/requirements-ml.txt` cùng `requirements.txt`, và tải/cache đúng revision CLIP. Hash chỉ giúp phát hiện file không khớp, không thay thế việc nhận artifact từ nguồn tin cậy.

`data/labels.csv` đang track vẫn là bản cũ 10.000 dòng, không bị ghi đè. Bộ chạy mới là 4.000 CIFAKE + 2.708 real GenImage + 1.000 ảnh mỗi nguồn GLIDE/Midjourney/SD1.4. Đã loại 292 real GenImage cạnh ngắn <256 px, không phóng to; không có ảnh hỏng hoặc trùng pixel bị loại thêm. Chưa bổ sung ảnh thay thế của KAN-34.

Không chạy migration ghi đè dữ liệu chính, không tự tạo chứng nhận baseline trên máy Loan. Test recipe JPEG chỉ so với các lệnh Pillow được **viết lại trong test trên ảnh tổng hợp**; không chạy `prepare_data.py` cũ trên baseline thật. T012/T013 chưa hoàn thành, chưa có `scripts/check_normalization.py` (T016/T022). Trạng thái đã ghi trong [tasks.md](../specs/001-unified-image-normalization/tasks.md); không dùng test này để nghiệm thu migration.

## Kết quả thực đo

Binary threshold công khai của lần chạy: `0.5`; chưa coi là D08 được nhóm phê duyệt. Vùng Chưa chắc `[0.3,0.7]`, gồm hai biên. Tất cả mẫu, kể cả Chưa chắc, đều được tính vào accuracy nhị phân.

| Bộ đánh giá | N | Accuracy | Precision AI | Recall AI | AUROC | Chưa chắc |
|---|---:|---:|---:|---:|---:|---:|
| CIFAKE validation | 300 | 91,33% | 89,74% | 93,33% | 0,95836 | 9,00% |
| CIFAKE test | 2.000 | 93,00% | 92,49% | 93,60% | 0,98244 | 8,90% |
| GenImage validation | 856 | 95,68% | 96,40% | 95,33% | 0,99485 | 7,36% |
| GenImage test | 856 | Chưa đo | Chưa đo | Chưa đo | Chưa đo | Chưa đo |

Grid C cố định `[0.01, 0.1, 1, 10, 100]`, chọn bằng accuracy validation; hòa chọn C nhỏ hơn. CIFAKE chọn C=100; GenImage chọn C=10. Seed 42, `max_iter=2000`; không fit trên validation hoặc test. Confusion matrix GenImage validation, hàng thật/AI và cột thật/AI: `[[390,16],[21,429]]`. FPR tại binary threshold là 3,94%; tỷ lệ real bị gọi `likely_ai` (score >0.7) là 0,74%.

| Source GenImage validation | N | Accuracy | Chưa chắc |
|---|---:|---:|---:|
| Real | 406 | 96,06% | 7,14% |
| GLIDE | 150 | 96,00% | 5,33% |
| Midjourney | 150 | 93,33% | 12,00% |
| SD1.4 | 150 | 96,67% | 5,33% |

Các source riêng chỉ có một lớp nên AUROC là `null`. Validation đã dùng chọn C nên 95,68% **không phải** kết quả test độc lập và không chứng minh mục tiêu ≥90% GenImage test. Kết quả vẫn có nguy cơ học shortcut từ dung lượng file, độ mịn/chi tiết và dấu vết nén JPEG; `jpeg_trace_check.py` (T027) chưa được triển khai, phương pháp còn chờ nhóm xác nhận. CIFAKE chỉ chứng minh luồng thử.

## Kiểm tra dữ liệu và tính nhất quán

- `scripts.check_data`: 0 lỗi, 0 cảnh báo trên manifest mới; không phát hiện exact/near dHash trùng train–val hoặc train–test theo checker hiện có. Đây không phải chứng minh tuyệt đối không có ảnh gần trùng; review QA vẫn cần.
- [Metadata audit](reports/ml-metadata-audit.json): toàn bộ 13 đặc trưng metadata post đều hằng trong từng dataset. Vì probe không còn tín hiệu phân biệt từ các cột này, A_eff=0,50 và CI95% `[0,50;0,50]` là kết quả hiển nhiên của phép kiểm tra đó, **không phải bằng chứng không có shortcut**. Gate hiện có đạt theo các cột được đo. Control dương=1,00, âm GenImage=0,5245. Protocol D03/D04 vẫn là bản nháp; không tự đổi gate thành cảnh báo.
- [Baseline dung lượng](reports/ml-filesize-baseline.json): chỉ dùng dung lượng file cũng đạt balanced accuracy LR=66,75% trên GenImage post và **84,54% ở real–GLIDE**. Phép kiểm metadata không đo dung lượng, pixel hay lịch sử nén trong pixel. Shortcut dung lượng/độ mịn/dấu vết JPEG vẫn còn là nguy cơ; T027 chưa có, chưa được kết luận mô hình đã học dấu vết AI tổng quát.
- Model thật: chọn một ảnh validation mỗi source; JPEG chuẩn hóa trong bộ nhớ khớp byte file processed; tensor thực của CLIP bằng nhau từng phần tử giữa train/serve. Sai khác điểm lớn nhất giữa suy luận một ảnh và feature batch là `3,36e-7`, dưới mức kiểm thử `1e-5` của lần chạy (không phải cam kết mọi phần cứng).
- Ảnh tổng hợp kích thước 4000×3000, grayscale và RGBA cho score hữu hạn; ảnh 32×32 bị `ImageTooSmall`. Đây là smoke test kích thước/mode, không phải đánh giá accuracy trên ảnh điện thoại thật.
- Startup + warmup khoảng 27,86 giây; bốn lượt score sau warmup khoảng 0,088–0,094 giây/lượt trên máy local. Không suy ra p95/RPS hoặc SLO server từ bốn mẫu này.

## Chạy lại và bàn giao cho Quang

Các lệnh cài đặt, chuẩn hóa, trích đặc trưng, train và hợp đồng Backend nằm trong [`models/README.md`](../models/README.md). Để tái hiện CIFAKE test đã báo, thêm `--evaluate-test` vào lệnh train CIFAKE. GenImage giữ mặc định không evaluate test.

Hai script audit của Loan mặc định đọc manifest chính. Lần chạy này đổi đường dẫn trong tiến trình để đo đúng bộ mới và không ghi đè báo cáo cũ:

```bash
python -c "from pathlib import Path; import scripts.metadata_audit as a; a.LABELS_CSV=Path('.cache/ml-run/labels.csv'); a.OUT_JSON=Path('.cache/ml-run/metadata_audit.json'); a.main()"
python -c "from pathlib import Path; import scripts.baseline_filesize as a; a.LABELS_CSV=Path('.cache/ml-run/labels.csv'); a.OUT_JSON=Path('.cache/ml-run/baseline_filesize.json'); a.main()"
python -m scripts.verify_ml --labels .cache/ml-run/labels.csv
```

Model phải nạp/warmup trước khi API ready. `score` nhận PIL Image gốc đã giải mã, không nhận ảnh processed, không tự tải model ở request đầu. API đọc EXIF trước, kiểm dung lượng/pixel/định dạng, gọi scorer trong cơ chế worker của Quang và bắt `ImageTooSmall`. Scorer không quyết định verdict hoặc thay EXIF.

Main đang có health/schema nhưng chưa có `POST /v1/analyze`. Không sửa module API/UI để tránh chồng vào phần Quang/Loan; KAN-20 ở đây bàn giao hàm/model và bằng chứng gọi trực tiếp. Demo HTTP hoàn chỉnh, Docker/Linux, kiểm tải, robust JPEG/Zalo/OOD và QA độc lập chưa được nghiệm thu.

## Kiểm thử và trạng thái Git

- Lần kiểm tra ban đầu có 80 pytest qua, coverage `app/` 98,31% trên Windows, Python 3.12.14. Lượt review bổ sung regression tests cho script và cả hai thứ tự `classes_`; log và số test cập nhật ghi trong hồ sơ tái lập. Test nhẹ không cần torch; `pandas` đã thêm vào requirements để CI chạy test script thật.
- Ruff check/format đạt; kiểm tra Git không có unmerged entry hoặc lỗi whitespace.
- Code ML bàn giao qua [PR #15](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/pull/15), đã rebase lên main `43caa16`. Chưa merge; conflict với các thay đổi tương lai phải kiểm lại khi tích hợp.
- Reviewer nên xem trước `models/`, rồi phần gọi shared normalization trong `scripts/prepare_data.py`, checker manifest và tests. Không có thay đổi ở `.opencode`, không commit dữ liệu hoặc trọng số.

## Vì sao PR ML có sửa scripts và tests

PR này mở rộng sang adapter của `prepare_data.py` và `check_data.py` để lần chạy ML riêng tạo đúng JPEG từ hàm chung, manifest version 1 và đặc trưng cùng contract với `score()`. Các regression test do Kiệt bổ sung kiểm trực tiếp phần tích hợp đã thay đổi. Đây là phần phạm vi chồng lấn với T014/T015 của Loan và phần kiểm thử của Lực; mô tả PR ban đầu đã thiếu giải thích này.

Người phụ trách trong spec vẫn là Loan/Lực. Các thay đổi này cần họ review trước merge, không thay thế baseline T012, QA độc lập T013/T030 hay cho phép Kiệt tự nghiệm thu các task đó. Bộ dữ liệu chạy riêng không ghi đè manifest/data chính. Lần sửa review tách ảnh nhỏ vào `rejected_small.csv`, ảnh hỏng/bomb vào `rejected_invalid.csv`, giữ trace theo source; `check_data` thiếu hoặc sai `norm_version` phải FAIL.
