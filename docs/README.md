# docs/ – Tài liệu

Phụ trách: Lực (tổng hợp), mỗi người viết phần mình

## Làm gì
Báo cáo, kịch bản demo, số đo và bảng đánh giá.

- [GenImage: lần train/test theo user authorization](ml-final-experiment.md): validation 97,24%/871, test holdout 94,53%/384; QA độc lập/release chưa được duyệt.

## Mục con
- [Bàn giao model cho API — GitHub #39](ml-api-model-handoff.md): gói reference `clip_probe.joblib`, checksum, hướng dẫn nạp và HTTP smoke với model thật; còn xác nhận của bên nhận.
- [Kiểm lại đủ bốn task ML](ml-recheck-20261110.md): KAN-37/39/44/51, phần đã có trên main và bằng chứng còn chờ QA.
- [Mở rộng dữ liệu và train lại ngày 10/11](ml-data-expansion-20261110.md): 9.936 ảnh train, candidate mixed v3; kết quả Reddit/GenImage/core và giới hạn trước khi sử dụng.
- [`test-plan.md`](test-plan.md) và [`bug-report-template.md`](bug-report-template.md): kế hoạch test tuần 1 và mẫu báo lỗi (KAN-26).
- `qa/integration-report-template.md`: mẫu biên bản kiểm thử tích hợp localhost (KAN-29).

## Lưu ý và giả định
- Tài liệu viết tiếng Việt; code và commit viết tiếng Anh.
