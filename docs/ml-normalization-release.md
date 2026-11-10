# KAN-37, KAN-39, KAN-44 và KAN-51

Nguồn đồng bộ ban đầu: `origin/main` tại `9364fdb`; cập nhật đến `0c1bdc4` để nhận baseline/dedup/evaluation của Loan và API/contract tests của nhóm. Nhánh làm việc: `kiet/ml-normalization-release`. Ngày 05/11/2026 Kiệt chọn candidate giữ split cũ, rồi yêu cầu chạy train/test khi đã biết QA độc lập còn chờ; lần chạy thật dùng commit `4a87e4a`.

**Đã chạy thử nghiệm theo yêu cầu của Kiệt; chưa nghiệm thu release:** sau khi được thông báo QA độc lập còn chờ, người dùng yêu cầu train/test ngay. KAN-44 đã trích features và train model mới; KAN-51 đã chấm một lần trên holdout lọc lịch sử, đạt **94,53%/384 ảnh**. Protocol ghi đúng user authorization và QA độc lập chưa duyệt. Xem [biên bản kết quả thật](ml-final-experiment.md); không chuyển các gate release khác thành approved.

Rà soát ngày 10/11/2026: [kết quả kiểm lại bốn task](ml-recheck-20261110.md). Phần triển khai ML chưa phát hiện lỗi mới trong các kiểm tra đã chạy; UI đã xử lý `decided_accuracy=null`. Các bước chuẩn bị và số kiểm thử ban đầu bên dưới là lịch sử, không phải trạng thái chưa thực thi của candidate hiện tại.

| Jira | Phần thực hiện | Điều kiện còn lại |
|---|---|---|
| [KAN-37](https://quangtadang4206.atlassian.net/browse/KAN-37) | T005/T019 spec 001: rà soát normalize hiện có, kiểm JPEG95 một lần, EXIF trước resize, 4000×3000, 255/256 và CIFAKE. Không đổi tham số/version 1. | Loan/Lực review theo phân công; baseline thật T012/T013 là task dữ liệu/QA riêng. |
| [KAN-39](https://quangtadang4206.atlassian.net/browse/KAN-39) | T009-T011: cùng encode CLIP cố định, score chuẩn hóa một lần; siết raw_path và cache float32 L2; dùng chung kiểm cột AI/xác suất cho serve và evaluate. | Quang/Lực xác nhận hợp đồng PIL Image và QA tích hợp HTTP ở ticket Backend/Q5. |
| [KAN-44](https://quangtadang4206.atlassian.net/browse/KAN-44) | T024: đã extract lại 9.708 ảnh và train C=10 theo candidate giữ split, validation 97,24%/871 ảnh; artifact mới riêng. | Phần thực thi đã có bằng chứng; Loan/Lực review QA và nghiệm thu artifact phát hành còn riêng. |
| [KAN-51](https://quangtadang4206.atlassian.net/browse/KAN-51) | MVP-04: protocol đã khóa, test một lần 384 ảnh theo user authorization; accuracy 94,53%, đủ predictions/report theo source. | QA độc lập/release chưa duyệt; không tiếp tục tune bằng bộ test đã mở hoặc coi chất lượng pass là toàn bộ MVP pass. |

## Vì sao bổ sung

Main đã có phần ML chính. Hai regression trên bản cũ được tái hiện: read_labels không từ chối raw_path rỗng/trùng (kể cả alias), load_features vẫn nhận float64 hoặc vector không có L2=1 khi checksum tương ứng. Bản sửa chặn các trường hợp đó; kiểm hash không đủ để bảo đảm hợp đồng embedding. Extraction cũng phát hiện labels thay đổi trong lúc chạy và không xuất cache mang nhãn của snapshot khác.

Trước đây `train --evaluate-test` vừa chọn C/train vừa chấm test. Với GenImage, lệnh này nay từ chối và yêu cầu `models.evaluate` trên model đã có. CIFAKE smoke test vẫn hỗ trợ cờ cũ. `Scorer.predict_features` dùng cùng quy tắc classes_/finite/sum-to-one với serving, không nạp lại CLIP để đánh giá cache đã kiểm.

Protocol ghi exact hash model, labels, features, manifest features, profile/version/Pillow/CLIP revision, thresholds và N test. Cần tham chiếu xác nhận thật về data QA, metadata audit, holdout review và thresholds; công cụ không thực hiện audit độc lập thay Lực. Report đạt accuracy không đồng nghĩa các gate release khác đã đạt. CLI quality fail vẫn lưu báo cáo và thoát 1.

## Manifest và test đang giữ nguyên

Cập nhật quyết định của Kiệt: chọn candidate giữ split từ bản 10.000. Bộ 9.708 cũ vẫn giữ để tái lập, không phải manifest mới đã chọn. Holdout lọc lịch sử còn 384 ảnh, đã được chấm một lần với accuracy 94,53%. Xem [manifest/ngưỡng/holdout đã chọn](decisions/ml-selection.md). Các số 856 dưới đây thuộc bộ QA cũ, không dùng làm N test của candidate mới.

- Manifest chính trên main: 10.000 ảnh, chưa có norm_version. Bộ thí nghiệm riêng: 9.708 ảnh, gồm 4.000 CIFAKE và 5.708 GenImage, loại 292 real ảnh nhỏ.
- Bộ 9.708 có 856 GenImage test chưa chấm điểm. 1.702 ảnh còn lại đổi split so với manifest cũ; chưa tự xác nhận holdout độc lập đối với mọi lần train trước của cả nhóm.
- Chưa thay data/labels.csv, không thay bù KAN-34, không tạo chứng nhận baseline thay Loan/Lực, không thay metadata gate.
- Lần kiểm ban đầu chạy test của Lực ngoài repo. Bản main mới đã merge checker/test QA; đồng bộ main chỉ nhận lại phần đã merge. Theo đề nghị mới, bổ sung tùy chọn giữ split trong prepare_data, cần Loan/Lực review; không sửa quyết định API của Quang.

### Cập nhật phương án giữ split cũ

Phản hồi của Loan là giữ ảnh cũ và ghi riêng ảnh không dùng. Nhánh ML chuẩn bị chế độ `--split-from` để tạo bản ứng viên giữ nguyên split của ảnh còn hợp lệ; không coi tin nhắn này là phê duyệt toàn bộ manifest/QA/holdout. Raw 10.000 ảnh, manifest cũ và bộ QA 9.708 dùng cho model/báo cáo cũ giữ nguyên. Bản ứng viên riêng có 9.708 ảnh, 292 ảnh nhỏ ghi rejected; không ảnh hợp lệ nào đổi split so với bản 10.000.

Baseline T012 của Loan đã có trên main (PR #24); 10.000 hash khớp tham chiếu code cũ đã tái lập, nhưng chưa thay việc review nghiệm thu T013. Manifest ứng viên mới không phải holdout chưa từng tiếp xúc: trong 849 GenImage test có 383 ảnh từng ở train và 82 ở validation của lần QA cũ. Lần chạy sau đó đã train trên candidate và chỉ chấm 384 ảnh còn lại sau khi lọc lịch sử. Chi tiết chuẩn bị ở [ml-preserved-split.md](ml-preserved-split.md), kết quả thực thi ở [ml-final-experiment.md](ml-final-experiment.md).

## Chạy và bàn giao

Lệnh extract/train và hai bước prepare/evaluate protocol nằm ở [models/README.md](../models/README.md). Loan có thể dùng output evaluation.json/predictions của lớp ML để làm adapter UI tại MVP-03; không cần một lần train hoặc chấm test độc lập thứ hai trong scripts/evaluate.py.

Trường hợp toàn bộ mẫu là Chưa chắc, `decided_accuracy=null` (không có mẫu để tính). Validator UI đã nhận null và hiển thị “Không có ảnh nào được kết luận”; regression được kiểm bằng `test_evaluation_uncertainty_all_images_has_no_decided_accuracy`. Không đổi null thành 0 hoặc 100% để ép UI nhận. Các trường version/hash, thresholds, test và by_source giữ cấu trúc báo cáo đã mô tả trong README UI.

Giữ artifacts/protocol thực trong thư mục output không đưa vào commit tự động. Khi công bố báo cáo, kiểm đường dẫn cá nhân trong run_info, giữ nguyên bản provenance gốc ở gói QA và chỉ công bố bản đã ẩn đường dẫn có ghi chú. Joblib cần checksum và nguồn tin cậy; checksum không xác thực tác giả.

95,68% vẫn là validation chọn C. Post metadata hằng/A_eff=0,50 chưa chứng minh không có shortcut; baseline real-GLIDE 84,54% là số của cohort cũ đã báo. Không tự đưa số này thành kết quả của manifest phát hành mới. JPEG ghost T027 vẫn chờ xác nhận/triển khai.

## Kết quả kiểm chứng local ban đầu (lưu lịch sử)

- Windows, Python 3.12.14; Ruff check và format đạt.
- Bộ test repo: 122 passed, coverage app 98,31%. Các ca mới dùng dữ liệu tổng hợp, không đọc điểm GenImage test.
- Chạy riêng 35 test từ nhánh `luc/qa-check-normalization` (normalize, normalize_large, too_small, score_normalization, extract_features) trên code ML mới: 35 passed. File test nằm ngoài repo để giữ quyền triển khai/review của Lực; chưa thay biên bản QA trên máy Lực.
- Kiểm model CLIP thật bằng `scripts.verify_ml` trên một ảnh validation mỗi nguồn GenImage: JPEG khớp bytes, tensor train/serve khớp từng phần tử, sai khác score lớn nhất `3,3527612686157227e-7` dưới tolerance `1e-5`; encoder frozen/eval, ảnh nhỏ bị từ chối, smoke 4000×3000/grayscale/RGBA đạt.
- Ở lần kiểm ban đầu, protocol cho bộ thí nghiệm 9.708 ảnh được chuẩn bị với trạng thái proposed và evidence trống. Lần train/test theo user authorization sau đó đã hoàn tất, xem biên bản kết quả thật ở đầu tài liệu; manifest phát hành vẫn chưa được nghiệm thu.

Lệnh kiểm model thật (report lưu ngoài repo) tương đương:

```bash
python -m scripts.verify_ml --labels .cache/ml-run/labels.csv --features data/features --model models/clip_probe.joblib --report ../outputs/realcheck-ml-completion/validation-parity.json
```

Report local ghi đúng base commit `9364fdb` và `git_dirty=true` do kiểm trên working tree trước khi commit; không trình bày thành run của một release commit sạch. Các số test trên là kết quả local, chưa thay bằng chứng CI trên PR. Chưa kiểm Docker/Linux hoặc API HTTP thật trong phạm vi ML này.
