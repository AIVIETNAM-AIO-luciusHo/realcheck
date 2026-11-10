# Kiểm lại KAN-37, KAN-39, KAN-44 và KAN-51 — 10/11/2026

Chưa phát hiện lỗi mới trong phần chuẩn hóa, CLIP, cache, train và score qua lần kiểm lại ban đầu dưới đây. Lượt kiểm ban đầu chỉ sửa tài liệu, không thay normalization version, weights, manifest, ngưỡng hoặc protocol đã dùng. Lần mở rộng dữ liệu/train tiếp theo được ghi riêng trong [biên bản train mới](ml-data-expansion-20261110.md).

## Đủ phạm vi bốn task trên nhánh đã push

Nhánh `kiet/ml-data-expansion-20261110` kế thừa implementation KAN-37/39/44/51 đã có trên main, gồm PR #15 và #34. Vì phần chuẩn hóa/CLIP/protocol đã có ở base, chúng không xuất hiện lại như file mới trong diff PR. Không cần chép lại hoặc đổi normalization để đủ tên task.

| Task | Code/bằng chứng có trên nhánh | Trạng thái |
|---|---|---|
| KAN-37 | `models/normalize.py`; tests normalize, normalize_large, too_small; hồ sơ rà soát này | Implementation đã có trên main, giữ version 1; QA độc lập còn riêng |
| KAN-39 | `models/clip_input.py`, `score.py`, `extract_features.py`, `data_sources.py`; kiểm train–serve và cache | Kế thừa pipeline chung, bổ sung mixed sources; parity thật 8 nguồn của candidate mới đạt |
| KAN-44 | `models/train.py`, `scripts/download_expansion.py`, `scripts/train_expansion.py`; báo cáo train mới | Candidate mới đã fit trên 9.936 ảnh, C=10; chưa thay model phục vụ |
| KAN-51 | `models/holdout.py`, `models/evaluate.py`; freeze/used marker/predictions của pipeline mở rộng | GenImage 384 ảnh đã đánh giá trước đó; không chấm lại. OpenFake core/reddit mới được chấm sau khóa model; QA/release chưa duyệt |

Đã bổ sung đầy đủ hồ sơ kiểm lại và sửa thông tin bàn giao còn thiếu sau lượt push chỉ gồm phần mở rộng dữ liệu. Bộ test trên code đã đồng bộ main `274f869`: **650 passed, 2 skipped, 1 xfailed**, app coverage **98,52%**; xem lệnh và điều kiện UTF-8 trong biên bản train mới. Các số 494 test và parity bốn nguồn dưới đây thuộc lần kiểm ban đầu, không thay số kiểm sau đồng bộ.

## Kết quả theo task

| Task | Kết quả kiểm lại | Phần còn lại |
|---|---|---|
| KAN-37 | Chuẩn hóa chung EXIF → RGB → BICUBIC 256×256 → JPEG95 một lần; regression ảnh nhỏ, ảnh lớn và CIFAKE đạt. | Review baseline/QA độc lập theo phân công. |
| KAN-39 | Score dùng cùng encoder/preprocessing; kiểm classes_, xác suất hữu hạn và cache version/hash/float32/L2. Model thật khớp JPEG/tensor train–serve trên một ảnh validation mỗi nguồn GenImage. | Xác nhận bàn giao artifact với Backend; kết quả local không thay nghiệm thu tích hợp. |
| KAN-44 | Model, labels, features và feature manifest hiện có khớp hash đã khóa. Bằng chứng cũ xác nhận extract 9.708 ảnh, train C=10, validation 97,24%/871 ảnh. | Review manifest/artifact phát hành; không cần train lại chỉ vì kiểm tài liệu. |
| KAN-51 | Tám hồ sơ gốc khớp checksum; đếm lại predictions có 363/384 ca đúng, accuracy 94,53125%. Không gọi lại model trên test. | QA độc lập, review lịch sử/near-duplicate và shortcut/khả năng tổng quát hóa vẫn còn. |

## Kiểm chứng mới

- `python -m pytest -q`: **494 passed, 1 skipped, 1 xfailed**, 130,00 giây trên Windows/Python 3.12.14. Skip là dependency Locust tùy chọn; xfail strict có sẵn cho process không thoát khi scorer treo vô hạn.
- `python -m ruff check .` và `python -m ruff format --check .`: đạt, 106 file Python đúng format.
- `scripts.verify_ml` dùng CLIP cache offline đúng revision và model candidate SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494`: cả 4 nguồn validation khớp JPEG/tensor; sai khác score lớn nhất **2,8312206268310547e-7**, dưới tolerance `1e-5`. Encoder frozen/eval; smoke 4000×3000, grayscale, RGBA và từ chối ảnh nhỏ đạt.
- SHA256 khớp cho labels candidate, model candidate, features và manifest features. Tám file đối chiếu từ `original_reports_sha256` trong `docs/reports/ml-final-experiment.json` đều khớp, gồm protocol và used marker.

Report parity mới lưu local tại `outputs/ml-recheck-20261110/validation-parity.json`; có provenance và đường dẫn máy cá nhân, không dùng làm báo cáo công bố. Nguồn kiểm là HEAD `9a3ca19e7f8eee273476bcf3ea8f3c4c6510c483` với working tree có thay đổi chưa commit (`git_dirty=true`). Kết quả này không phải CI mới hoặc QA độc lập.

Lệnh parity đã chạy từ repo root, với `HF_HOME=.cache/huggingface`, `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1`:

```text
python -m scripts.verify_ml --labels ../outputs/realcheck-preserved-split/labels.csv --features ../outputs/realcheck-ml-final-run/features --model ../outputs/realcheck-ml-final-run/genimage.joblib --report outputs/ml-recheck-20261110/validation-parity.json
```

## Điều chỉnh và giới hạn

Đã sửa `docs/ml-normalization-release.md` để phân biệt lịch sử chuẩn bị với lần train/test đã hoàn tất. Đã sửa cả hồ sơ này và `models/README.md`: UI hiện nhận `decided_accuracy=null` và hiển thị “Không có ảnh nào được kết luận”; regression `test_evaluation_uncertainty_all_images_has_no_decided_accuracy` đã qua trong lượt test mới.

`models/clip_probe.joblib` vẫn là model cũ SHA256 `69810fd60940ddeed07af92d600c6bb0466641bf4144aec73554b44013ae7bdb`; candidate mới nằm ở `../outputs/realcheck-ml-final-run/genimage.joblib`. Đây là hai artifact khác nhau có chủ đích. Khi bàn giao candidate, cần truyền đúng đường dẫn/model checksum; không gán kết quả 94,53% cho file mặc định cũ.

94,53% chỉ đại diện 384 ảnh đã lọc, gồm 65 real và 19 SD1.4; đã có một real bị gọi AI ở binary threshold 0.5. Chưa đủ bằng chứng để quy nguyên nhân cho preprocessing hoặc kết luận model tổng quát tốt trên ảnh web/điện thoại. T027/JPEG ghost còn chờ phương pháp; audit metadata hằng không loại trừ shortcut. Candidate mở rộng cải thiện Reddit nhưng giảm GenImage validation/core; các số mới và giới hạn được ghi riêng trong biên bản train mới.

Lần kiểm ban đầu không train lại/tune ngưỡng hoặc mở lại holdout 384 ảnh; candidate mở rộng được chạy riêng và ghi trong biên bản train mới. Lượt rà soát này không chạy lại Docker/Linux, benchmark robustness hay kiểm trạng thái Jira. KAN-51 có bằng chứng thực thi, nhưng QA độc lập và release vẫn chưa được duyệt; nếu cải thiện model cần dữ liệu phát triển và test mới theo protocol phù hợp.
