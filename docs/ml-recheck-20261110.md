# Rà soát KAN-37, KAN-39, KAN-44, KAN-51 — 10/11/2026

PR A chỉ công bố tài liệu và bằng chứng đã có. Implementation chuẩn hóa/score từ các PR trước nằm trên main; **không coi việc thêm tài liệu là thực hiện lại hoặc đóng cả bốn task**. GitHub issue #39 là bàn giao artifact, khác Jira KAN-39 (đồng bộ score/CLIP).

| Jira | Bằng chứng hiện có | Phần còn lại / trạng thái đề nghị |
|---|---|---|
| KAN-37 | Normalization v1 dùng chung EXIF → RGB → BICUBIC 256×256 → JPEG95; parity và smoke ảnh nhỏ/lớn/grayscale/RGBA đã chạy. D02 được ghi rõ trong decision bổ sung. | Implementation có sẵn; chờ review/QA theo quy trình. PR A không sửa normalizer. |
| KAN-39 | Encoder/profile/cache được kiểm; 4 nguồn GenImage validation khớp tensor train–serve, sai khác score tối đa `2,8312206268310547e-7 < 1e-5`. API thật trên main khớp direct score. | Xác nhận ML contract đã ghi; Quang/Lực review và Quang xác nhận máy đích còn chờ. |
| KAN-44 | Reference e571 train trên commit sạch `4a87e4ac…`, seed42, C10, validation 97,24%/871. Pipeline mở rộng và fit sạch mới ở PR B #61. | Review candidate trong PR B; không nâng mixed thành model phục vụ. QA provenance dữ liệu/split còn thiếu. |
| KAN-51 | Tám hồ sơ gốc khớp checksum trong lần rà soát; đếm lại predictions có 363/384 đúng, 94,53125%; không gọi lại model trên test. | Chưa QA độc lập; thiếu review near-duplicate/lịch sử, shortcut và khả năng tổng quát. Không ghi “đạt 90%” chung. |

Đây là **bảng đề nghị cập nhật Jira**, chưa phải trạng thái trực tiếp trên Jira. Không đổi Jira/đóng task khi chưa có quyền truy cập hoặc xác nhận thực tế.

## Bằng chứng và provenance

[JSON parity đã bỏ đường dẫn máy cá nhân](reports/ml-recheck-20261110.json) lưu nguyên nguồn lịch sử `9a3ca19e7f8eee273476bcf3ea8f3c4c6510c483`, **`git_dirty=true`**, Python 3.12.14. Việc xuất bản report không biến lần kiểm đó thành clean run hay QA độc lập.

Lần rà soát lịch sử: **494 passed, 1 skipped, 1 xfailed**, 130,00 giây; Ruff check/format đạt (106 file). Skip do dependency Locust tùy chọn; xfail strict có sẵn cho scorer treo vô hạn. Đây không phải test suite chạy mới trên PR A.

Lệnh parity lịch sử từ repo root, với `HF_HOME=.cache/huggingface`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`:

```text
python -m scripts.verify_ml --labels ../outputs/realcheck-preserved-split/labels.csv --features ../outputs/realcheck-ml-final-run/features --model ../outputs/realcheck-ml-final-run/genimage.joblib --report outputs/ml-recheck-20261110/validation-parity.json
```

4 nguồn validation đều khớp tensor; smoke ảnh tổng hợp 4000×3000, grayscale, RGBA và từ chối ảnh nhỏ qua. Chỉ dùng validation. [Report bàn giao mới](reports/ml-api-handoff-20261110.json) kiểm API/CLI thật trên mã main `274f869…`, độc lập PR B. Nó không thay cho nghiệm thu trên máy Quang.

## Quyết định và giới hạn

[Bàn giao #39](ml-api-model-handoff.md) chọn reference **e571…**, không phải default cũ **69810fd6…**, cũng không phải mixed candidate của PR B. Không gán số test của model này cho artifact khác. [Hồ sơ thí nghiệm gốc](ml-final-experiment.md) là nguồn metrics cũ.

94,53% chỉ trên 384 ảnh đã lọc gồm 65 real, 19 SD1.4; test đã được mở. Audit metadata không loại trừ shortcut JPEG/dung lượng/nội dung. Không train/tune bằng test, không mở lại holdout để chứng minh tài liệu. Docker/Linux, load benchmark, FR-A06 stage logging và nghiệm thu máy đích chưa kiểm trong PR A. Không sửa README `models/` hay code để đáp ứng issue #39.
