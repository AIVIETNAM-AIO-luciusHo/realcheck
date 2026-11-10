# Bổ sung D02, D12 và hợp đồng score — GitHub #39

Ngày: 2026-11-10. Người ghi phần ML: Kiệt. **Trạng thái: proposed cho phê duyệt chung; hiện trạng implementation đã kiểm.** Chờ Quang/Lực review; không tự ghi thay phê duyệt của nhóm. Không thay mã `models/` hoặc normalization version trong PR này.

## D02: hành vi version 1 hiện có

Nguồn: `models/normalize.py` tại main `274f869ada646400d00f832b0aa3723c219d7742`; quan sát tổng hợp trong [report bàn giao](../reports/ml-api-handoff-20261110.json), Pillow13.0.0, JPEG library8.0.

- EXIF transpose → `convert("RGB")` → `ImageOps.fit` BICUBIC 256×256 → một lần JPEG quality95 → decode cho CLIP.
- **Alpha:** bỏ kênh alpha, giữ RGB ẩn; không composite nền trắng/đen. RGBA `(200,30,10,0)` cho RGB trước JPEG `(200,30,10)`, sau JPEG `(201,30,10)` do nén mất dữ liệu.
- **ICC:** không gọi ImageCms để chuyển màu về sRGB, không nhúng ICC vào JPEG đầu ra. Không mô tả “RGB” như một bước quản lý màu đã được thực hiện.
- **Subsampling:** normalizer không truyền `subsampling`; dùng mặc định Pillow. Quan sát với môi trường đã ghim là sampling code2, **4:2:0**. Không khẳng định có tham số explicit hoặc hành vi luôn giống mọi phiên bản Pillow.

Đề nghị giữ nguyên v1 để khớp dữ liệu/features/model đã khóa. Nếu muốn composite alpha, chuyển ICC hoặc đổi profile JPEG, cần quyết định riêng, tăng `NORMALIZATION_VERSION`, trích lại features/train lại và kiểm parity. Tài liệu này không âm thầm thay preprocessing.

## Hợp đồng score: xác nhận kỹ thuật ML

Kiệt ghi xác nhận phía ML: `score(PIL.Image gốc đã giải mã, còn EXIF) -> float` hữu hạn `[0,1]`; normalizer chỉ được gọi một lần bên trong scorer. API giải mã một lần, không resize/nén; loader/warmup chạy lúc startup. Ảnh nhỏ phát `ImageTooSmall`, lỗi model truyền ra để API xử lý theo D05. [Bằng chứng API/CLI](../ml-api-model-handoff.md) có real model và 4 nguồn validation; ảnh bytes sai không gọi scorer.

Hợp đồng vẫn `proposed` ở sổ quyết định chung cho đến khi reviewer Quang/Lực xác nhận. Không dùng xác nhận kỹ thuật này để tự đánh dấu QA/release approved.

## D12 và FR-A06: trả lời câu hỏi PR #36

Giữ quyết định tạm hiện tại **1 worker, 1 slot**. Chưa chứng nhận thread safety của shared Scorer; frozen/eval không đủ. Không tăng `inference_slots > 1` bằng PR này.

Gói bàn giao có `profile_stages.py` đo normalize/JPEG, CLIP, LR offline. Median 5 lượt tuần tự trên một ảnh validation: 2,75 / 102,13 / 0,50 ms; total105,46 ms. Có so score trong tolerance `1e-5`. Không phải p95, không phải đo tải, không thêm per-request telemetry cho API; **FR-A06 còn cần Backend instrumentation**.

## Model và phê duyệt còn chờ

Kiệt chọn e571 cho reference API local/lab; manifest labels/hash, commit sạch, seed, versions, cache mount và file tải nằm trong [hồ sơ bàn giao](../ml-api-model-handoff.md). Lựa chọn phục vụ local không thay xác nhận manifest/dữ liệu của Loan hoặc QA của Lực. Quang vẫn cần báo kết quả checksum/CLI trên máy đích trước khi đóng #39.
