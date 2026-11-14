# docs/ – Tài liệu

Phụ trách: Lực (tổng hợp), mỗi người viết phần mình

## Làm gì
Báo cáo, kịch bản demo, số đo và bảng đánh giá.

- [GenImage: lần train/test theo user authorization](ml-final-experiment.md): validation 97,24%/871, test holdout 94,53%/384; QA độc lập/release chưa được duyệt.

## Mục con
- [ADV-06 cohort thực tế](cohorts-adv06.md): ảnh điện thoại, AI mới, Zalo; số thực nhận, ảnh bị loại, bảo vệ riêng tư, kết quả chấm e571 (ảnh thật iPhone 3,6%), hạn chế; ảnh không chia sẻ, chỉ có hash và kết quả.
- [ADV-08 robustness](robustness-adv08.md): helper phân tích predictions, protocol bàn giao #51 và trạng thái chưa chạy thật do thiếu đầu vào.
- [Mở rộng dữ liệu và train lại ngày 10/11](ml-data-expansion-20261110.md): 9.936 ảnh train, candidate mixed v3; kết quả Reddit/GenImage/core và giới hạn trước khi sử dụng.
- [`test-plan.md`](test-plan.md) và [`bug-report-template.md`](bug-report-template.md): kế hoạch test tuần 1 và mẫu báo lỗi (KAN-26).
- `qa/integration-report-template.md`: mẫu biên bản kiểm thử tích hợp localhost (KAN-29).

## Lưu ý và giả định
- Tài liệu viết tiếng Việt; code và commit viết tiếng Anh.

## Bàn giao ML/API và rà soát

- [Bàn giao model #39](ml-api-model-handoff.md): artifact e571, checksum, provenance/cache, hợp đồng và nghiệm thu còn chờ.
- [Rà soát bốn task](ml-recheck-20261110.md): tách bằng chứng kỹ thuật khỏi trạng thái Jira/QA.
- [Bổ sung quyết định D02/D12/score](decisions/ml-api-handoff-39.md): hiện trạng kiểm được, chờ review chung.
- [JSON bàn giao](reports/ml-api-handoff-20261110.json), [JSON parity lịch sử](reports/ml-recheck-20261110.json).
- Dữ liệu mở rộng/train candidate được review riêng tại [PR B #61](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/pull/61); PR tài liệu không phụ thuộc PR B.

## Sổ quyết định và hồ sơ ML

- [**Sổ quyết định kỹ thuật** (D01–D14, hợp đồng `score`, manifest, phạm vi M1/M2)](decisions/realcheck-baseline.md): trạng thái từng quyết định, người duyệt, ngày; nguồn chính khi tài liệu khác lệch nhau.
- [Manifest, holdout và ngưỡng Kiệt chọn (05/11)](decisions/ml-selection.md).
- [Kiểm độc lập bộ dữ liệu mở rộng (ADV-09, #54)](data-review-adv09.md).
- Hồ sơ ML lịch sử, viết trước khi chọn e571 hoặc cho candidate cũ (số trong đó, như 95,68%/856, là của model cũ): [bàn giao ML KAN-16 đến KAN-20](ml-handoff.md), [bản ứng viên giữ split](ml-preserved-split.md), [KAN-37, KAN-39, KAN-44, KAN-51](ml-normalization-release.md), [truy vết và tái lập thí nghiệm](ml-reproducibility.md), [Jira liên quan đến nhánh ML](ml-jira-links.md).

## Đối chứng shortcut ADV-10

- [Thiết kế và kết quả #59](shortcut-adv10.md): model e571, validation/CI và giới hạn.
- [JSON ADV-10](reports/shortcut-adv10.json): số đo thật, chưa QA độc lập.

## Triển khai

- [SLO hiệu năng](performance/README.md): mẫu SLO (`slo.template.json`), cách điền từ số đo thật và ký; `slo.json` cố ý không có trong repo.
- [Deploy core lên máy lab](deploy.md): cài, kiểm, cập nhật mã và model, rollback (MVP-08); [mẫu biên bản deploy](deploy-record-template.md).
- [Diễn tập deploy, rollback, phục hồi (11/11)](reports/deploy-rollback-rehearsal-20261111.md): chạy local, chưa phải bằng chứng trên server.

## Biên bản QA

- [Runbook M1 và kịch bản demo](qa/m1-runbook-and-demo.md): các bước chạy localhost với model e571, bằng chứng KAN-29, bảng 6 ảnh và giới hạn khi demo (ảnh thật chụp điện thoại có thể ra "Ảnh AI"); diễn tập 11/11.
- [Mẫu biên bản kiểm gateway](qa/gateway-report-template.md) (KAN-54).
- [Kiểm với model thật trên Linux (11/11)](qa/local-real-model-verification-20261111.md): smoke, gateway, Docker, Compose, baseline Locust sơ bộ; ảnh tổng hợp, chưa phải nghiệm thu.
- [Review KAN-25: nạp model](qa/kan-25-model-loading-review.md): đối chiếu tiêu chí, vấn đề cần sửa trước bàn giao.
- [Chạy thử chuỗi robustness (12/11)](qa/robustness-chain-dry-run.md): biến thể, chấm, phân tích trên dữ liệu tổng hợp; điểm lệch và checklist trước khi chạy thật.
