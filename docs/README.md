# docs/ – Tài liệu

Phụ trách: Lực (tổng hợp), mỗi người viết phần mình

## Làm gì
Báo cáo, kịch bản demo, số đo và bảng đánh giá.

- [GenImage: lần train/test theo user authorization](ml-final-experiment.md): validation 97,24%/871, test holdout 94,53%/384; QA độc lập/release chưa được duyệt.

## Mục con
- [ADV-08 robustness](robustness-adv08.md): helper phân tích predictions, protocol bàn giao #51 và trạng thái chưa chạy thật do thiếu đầu vào.
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
