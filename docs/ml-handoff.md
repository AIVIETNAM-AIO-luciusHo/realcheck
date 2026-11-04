# Bàn giao ML – KAN-16 đến KAN-20

Ngày thực hiện: 04/11/2026. Người phụ trách: Kiệt. Code nền đồng bộ từ `origin/main` tại `24bd0a6c301e251695c436ab9f941b5513476d5e`; nhánh làm việc `kiet/clip-vit-b32-ml`. Phần OpenCode nằm ngoài phạm vi.

## Phạm vi đã thực hiện

| Task | Kết quả và bằng chứng |
|---|---|
| KAN-16 – Chuẩn bị CLIP, thống nhất đầu vào | Nạp đúng `sentence-transformers/clip-ViT-B-32`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`, bằng `SentenceTransformer`; eval, tắt gradient, embedding 512 chiều L2. Chuẩn hóa chung theo spec 001, version `1` |
| KAN-17 – CIFAKE + Logistic Regression | Chạy 4.000 ảnh CIFAKE, train/validation/test riêng, xuất model chạy thử và [số đo CIFAKE](reports/ml-cifake.json) |
| KAN-18 – Đặc trưng GenImage | Trích đủ 5.708 ảnh GenImage cùng 4.000 CIFAKE; `features.npy` shape `(9708,512)`, float32; manifest kiểm row order, hash dữ liệu và model/version |
| KAN-19 – Train và đánh giá ban đầu | Train LR GenImage trên 3.996 ảnh, chọn C trên 856 validation; xuất [báo cáo validation](reports/ml-genimage.json). Giữ 856 test GenImage chưa chấm điểm |
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

Không chạy migration ghi đè dữ liệu chính, không tự tạo chứng nhận baseline trên máy Loan. Test ảnh tổng hợp chứng minh byte JPEG khớp thuật toán cũ trong cùng runtime; việc so với baseline thực của Loan và QA độc lập T012/T013 vẫn còn.

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

Các source riêng chỉ có một lớp nên AUROC là `null`. Validation đã dùng chọn C nên 95,68% **không phải** kết quả test độc lập và không chứng minh mục tiêu ≥90% GenImage test. CIFAKE chỉ chứng minh luồng thử.

## Kiểm tra dữ liệu và tính nhất quán

- `scripts.check_data`: 0 lỗi, 0 cảnh báo trên manifest mới; không phát hiện exact/near dHash trùng train–val hoặc train–test theo checker hiện có. Đây không phải chứng minh tuyệt đối không có ảnh gần trùng; review QA vẫn cần.
- [Metadata audit](reports/ml-metadata-audit.json): post A_eff=0,50, CI95% `[0,50;0,50]` cho overall và ba cặp real–generator; gate hiện có đạt. Control dương=1,00, âm GenImage=0,5245. Protocol D03/D04 của script vẫn là bản nháp; không tự đổi gate thành cảnh báo.
- [Baseline dung lượng](reports/ml-filesize-baseline.json): GenImage post balanced accuracy LR=66,75%; real–GLIDE=84,54%. Metadata sạch không chứng minh sạch shortcut pixel; độ mịn/chi tiết ảnh và lịch sử JPEG vẫn là hạn chế phải ghi rõ, đặc biệt khi đem model ra ảnh điện thoại/AI mới.
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

- 80 pytest chạy qua, coverage `app/` 98,31% trên Windows, Python 3.12.14; test nhẹ không cần torch. Danh sách dependency của lần train nằm trong JSON báo cáo.
- Ruff check/format đạt; kiểm tra Git không có unmerged entry hoặc lỗi whitespace.
- Code ML được bàn giao trên nhánh `kiet/clip-vit-b32-ml`, phát triển từ `origin/main` tại `24bd0a6`; chưa mở PR. Không thể bảo đảm nhánh không conflict với các thay đổi được nhóm push trong tương lai.
- Reviewer nên xem trước `models/`, rồi phần gọi shared normalization trong `scripts/prepare_data.py`, checker manifest và tests. Không có thay đổi ở `.opencode`, không commit dữ liệu hoặc trọng số.
