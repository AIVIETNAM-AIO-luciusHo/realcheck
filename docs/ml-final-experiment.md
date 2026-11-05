# GenImage: train và đánh giá theo yêu cầu của Kiệt

## Kết quả và phạm vi

Đã trích lại CLIP trên 9.708 ảnh, train Logistic Regression trên manifest giữ split cũ và chấm một lần trên **384 ảnh holdout đã lọc lịch sử**. Người dùng yêu cầu tiếp tục dù QA độc lập chưa được duyệt. Protocol ghi `user_authorized_experiment`, người cho phép là Kiệt, `independent_qa_approved=false` và `release_approved=false`; không ghi Loan/Lực đã duyệt thay.

| Chỉ số | Validation | Test holdout đã lọc |
|---|---:|---:|
| N | 871 | 384 |
| Accuracy binary, ngưỡng 0.5 | 97,24% | **94,53%** |
| Precision AI | 97,97% | 99,67% |
| Recall AI | 96,67% | 93,73% |
| AUROC | 0,9958 | 0,9909 |
| Chưa chắc, score trong [0.3,0.7] | 49 (5,63%) | 35 (9,11%) |

Accuracy test là **363/384**, tính cả ca Chưa chắc. Confusion matrix theo hàng thật, cột dự đoán, thứ tự `[real, ai]`: `[[64,1],[20,299]]`. Có 1/65 ảnh thật bị gọi AI theo ngưỡng binary (FPR 1,54%). Accuracy trên 349 ca đã kết luận là 97,71%, không dùng thay accuracy toàn tập hoặc để làm đạt 90%.

| Source test | N | Đúng | Accuracy |
|---|---:|---:|---:|
| Real | 65 | 64 | 98,46% |
| SD1.4 | 19 | 19 | 100,00% |
| GLIDE | 150 | 142 | 94,67% |
| Midjourney | 150 | 138 | 92,00% |

Mục tiêu accuracy >=90% đạt **trong phạm vi thử nghiệm này**. Đây không phải kết quả toàn bộ 849 ảnh test của manifest, không phải kiểm chứng trên mọi ảnh ngoài thực tế và không thay nghiệm thu QA/MVP. SD1.4 chỉ 19 ảnh, real 65; cần đọc số liệu cùng N và sự lệch lớp.

## Dữ liệu, model và truy vết

- Manifest: 9.708 dòng giữ split theo bản 10.000; 292 ảnh nhỏ ghi riêng, raw giữ nguyên. Labels SHA256 `4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad`.
- GenImage: train 3.988, val 871, test gốc 849. Trước khi train đã chọn 384 ảnh không trùng raw/pixel với train/val của candidate và các lịch sử được cung cấp; loại 465 ảnh đã tiếp xúc. Lịch sử được kiểm là bộ QA cũ SHA256 `72313cf272f101c84c757d25c29869af8d290743e2be3151b5c9aa6debeae8c5`.
- CLIP: `sentence-transformers/clip-ViT-B-32`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`, frozen, CPU 4 threads, embedding 512 float32 L2-normalized.
- Đã encode lại thật toàn bộ 9.708 ảnh. Features hash vẫn là `1a08a1005c3ea3f6daf2172f944b97d51a6d3d33f73ec812558840d2cedfa217`: JPEG và encoder không đổi nên vector xác định trùng bản cũ là bình thường. Không sửa hash labels trong cache cũ để giả lần extract mới.
- LR: grid cố định C=[0.01,0.1,1,10,100], seed 42, chọn C bằng validation, hòa chọn C nhỏ hơn. Kết quả **C=10**. Không fit lên val/test, không đổi model/ngưỡng sau test.
- Model mới SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494`. Model/báo cáo QA cũ giữ nguyên; không tự thay model mặc định Backend đang dùng.
- Code nguồn khi extract/train/verify/test: **`4a87e4ac3f14d34e0501303d47e25a02828363ce`**, working tree sạch (`dirty=false`). Windows/Python 3.12.14, thư viện ML theo dependencies trong validation report.
- Model và ngưỡng 0.3/0.5/0.7 được khóa trước khi chấm. Marker `protocol.user-authorized.json.used.json` lưu lần mở test; không xóa marker hoặc đổi protocol để chọn kết quả đẹp.

Số đầy đủ và hash các báo cáo gốc: [ml-final-experiment.json](reports/ml-final-experiment.json). Bản công bố chỉ giữ các trường provenance không có đường dẫn máy cá nhân; file JSON gốc với command/runtime đầy đủ nằm trong gói local. Không đổi timestamp hoặc số liệu thủ công để tạo provenance.

## Lệnh đã chạy

Từ gốc repo, output riêng ở `../outputs/realcheck-ml-final-run`. CLIP lấy từ cache offline đúng revision; không tải lại model khác.

```bash
python -m models.extract_features --labels ../outputs/realcheck-preserved-split/labels.csv --output-dir ../outputs/realcheck-ml-final-run/features --batch-size 32
python -m models.train --labels ../outputs/realcheck-preserved-split/labels.csv --features ../outputs/realcheck-ml-final-run/features --dataset genimage --output ../outputs/realcheck-ml-final-run/genimage.joblib --report ../outputs/realcheck-ml-final-run/validation.json --binary-threshold 0.5
python -m scripts.verify_ml --labels ../outputs/realcheck-preserved-split/labels.csv --features ../outputs/realcheck-ml-final-run/features --model ../outputs/realcheck-ml-final-run/genimage.joblib --report ../outputs/realcheck-ml-final-run/verification.json
python -m models.evaluate --labels ../outputs/realcheck-preserved-split/labels.csv --features ../outputs/realcheck-ml-final-run/features --model ../outputs/realcheck-ml-final-run/genimage.joblib --history-labels .cache/ml-run/labels.csv --prepare-lock ../outputs/realcheck-ml-final-run/protocol.proposed.json
python -m models.evaluate --labels ../outputs/realcheck-preserved-split/labels.csv --features ../outputs/realcheck-ml-final-run/features --model ../outputs/realcheck-ml-final-run/genimage.joblib --history-labels .cache/ml-run/labels.csv --lock ../outputs/realcheck-ml-final-run/protocol.user-authorized.json --output-dir ../outputs/realcheck-ml-final-run/test-result
```

Giữa chuẩn bị và chạy test, bản proposed được giữ nguyên; tạo file protocol riêng để ghi đúng cho phép thử nghiệm của Kiệt, evidence từ các lần tự kiểm thực tế và trạng thái QA độc lập chưa duyệt. Không ghi reviewer giả. File `user-authorization.json`, `inputs-lock.json`, protocol proposed/authorized/used và log được giữ cùng nhau.

Lệnh test trên là lịch sử lần chạy đã hoàn thành, không phải yêu cầu chấm lại. Khi audit kết quả, dùng `predictions.csv` đã lưu: đã đếm lại độc lập số đúng, confusion matrix, precision/recall, số uncertain và danh sách row_index theo protocol, khớp JSON. Không cần gọi model lần hai để dựng bảng.

## Kiểm chứng và giới hạn còn lại

- Parity model thật trên một ảnh validation mỗi source: tensor khớp chính xác; sai khác score lớn nhất **2,8312206268310547e-7**, dưới tolerance 1e-5. Encoder frozen/eval; ảnh nhỏ bị từ chối; ảnh 4000×3000, grayscale, RGBA chạy được. Đây là smoke, không phải benchmark p95 hoặc robustness accuracy.
- Metadata audit bản nháp chạy trên manifest mới: post A_eff=0,50 ở các slice; positive control=1,00, negative control GenImage=0,522. 13 feature post đều hằng nên điểm chance là hiển nhiên, chưa chứng minh không còn shortcut.
- Dung lượng file, độ mịn và dấu vết JPEG vẫn là rủi ro; con số real–GLIDE 84,54% chỉ từ file size thuộc cohort cũ, không phải phép đo mới trên 384 ảnh. T027/JPEG ghost chưa có.
- Chỉ lọc theo lịch sử đã cung cấp và trùng raw/pixel; group/near-duplicate và các lần train không lưu manifest vẫn cần review. Không cam kết ảnh chưa có trong pretraining CLIP.
- Bộ test 384 nay đã mở. Không dùng kết quả này để tune rồi lại gọi nó là holdout chưa từng thấy.
- Full suite trước phần bổ sung metadata authorization: 393 passed, 1 skip (Locust tùy chọn), app coverage 92,64%; thêm hai test liên quan report/CLI đã pass sau bổ sung. Ruff đạt. Các lần chạy real extract/train/verify/test đều exit 0.

Phần thực thi tương ứng KAN-44 đã có model/features/validation mới; KAN-51 đã có một kết quả test đã khóa theo yêu cầu người dùng. Nghiệm thu release, QA độc lập và triển khai model vào Backend vẫn là trạng thái riêng; không tự tick tất cả gate vì accuracy đạt.
