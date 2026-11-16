# Protocol ADV-12 (#161): bản 2, sửa 16/11/2026 trước khi chạy thí nghiệm nào

**Trạng thái:** bản 1 do Lực khóa ngày 16/11/2026 (PR #171). **Bản 2 (PR này) sửa bốn điểm chặn C1 đến C4 của Tester (T-24, 16/11) khi chưa chạy thí nghiệm nào và chưa có số**; không ai đã thấy kết quả của bản này nên sửa không làm lệch kết luận. Lực chọn đúng các đề xuất ở mục 4 (2 điểm accuracy, 5 điểm recall, tiêu chí chọn model E0..E3) và đồng ý sửa. Từ khi bản 2 được merge, mọi thay đổi tiếp theo là protocol mới. Các mục còn mở ở mục 8 vẫn chờ Lực. Công cụ và lệnh từng thí nghiệm ở [`adv12-experiment-plan.md`](adv12-experiment-plan.md); file này chỉ ghi **luật chơi** để không chỉnh sau khi thấy kết quả. Câu hỏi: giảm ảnh thật (ảnh điện thoại, Zalo) bị gọi "Ảnh AI" mà không làm tụt GenImage.

## 1. Cohort và vai trò từng tập

| Tập | Vai trò | Được dùng để | Không được dùng để |
|---|---|---|---|
| train (theo `group_id`) | huấn luyện E1..E3, E5 | fit, tăng cường | chọn model |
| validation GenImage | **chọn** model, đặc trưng, C, hiệu chuẩn, ngưỡng | mọi lựa chọn | báo kết quả cuối |
| ADV-06 (`cohorts-adv06.md`) | **chỉ tập phát triển**: đã dùng so sánh nên không còn độc lập | xem hướng, kiểm ngưỡng chuyển miền | kết quả cuối, chọn model một mình |
| bộ 40 ảnh mới (#116, 38 ảnh dùng được) | đánh giá cuối ảnh thật ngoài GenImage | chấm **một lần cho mỗi model**; **E0 (e571) đã được chấm ngày 15/11** (29 gọi "Ảnh AI", 8 "Chưa chắc", 1 thật; Loan), nên số E0 là số đã thấy, không phải số mới | chỉnh bất cứ thứ gì; không có ảnh AI nên không đo recall |
| test GenImage | đánh giá cuối GenImage (đã mở một lần cho e571, 94,53%/384) | chấm một lần theo protocol; không dùng chọn | chọn model, ngưỡng |

Không ảnh nào có `group_id` ở hai tập (`adv12_run` chặn). Ảnh nhóm tự thu giữ trên máy, chỉ lưu hash và manifest.

## 2. Thí nghiệm
E0 (đối chứng e571, hash `e5718345…9494`), E1 (tăng cường), E2 (nhiều lớp), E3 (ViT-L/14), E4 (hiệu chuẩn, ngưỡng), E5 (ghép). Mỗi mã là **một protocol riêng**, chạy **một lần**. Lượt hỏng giữ lại và báo; chạy lại là protocol mới. Không thêm thí nghiệm sau khi đã thấy số.

## 3. Metric (khai báo trước)
Trên mỗi miền, ghi cỡ mẫu và CI bootstrap theo group (seed 42, 2000 replicate, `compare_models`):
1. **Miền ảnh thật:** tỉ lệ ảnh thật bị gọi AI (`score > 0,7`, mức "Ảnh AI" của sản phẩm), tỉ lệ vào "Chưa chắc" (0,3 đến 0,7), recall ảnh AI nếu cohort có.
2. **Miền GenImage:** accuracy, AUROC, recall ảnh AI theo SD1.4, Midjourney, GLIDE.
3. Hiệu A − B (so E0) kèm CI. Hiệu chuẩn (E4): ECE, Brier, NLL trước và sau.
4. #116 không có ảnh AI nên ADV-12 **không đo recall ở miền điện thoại cho #116**; ADV-06 (46 ảnh AI) là tập phát triển nên chỉ báo số tham khảo.

## 4. Tiêu chí "có cải thiện" (viết trước khi chạy)
Một thí nghiệm Ex được ghi **"cải thiện"** chỉ khi đủ cả ba, tính trên **validation** khi chọn và trên tập cuối khi báo:
1. Tỉ lệ ảnh thật bị gọi AI của Ex thấp hơn E0 và CI của hiệu không chứa 0.
2. Trên GenImage, accuracy của Ex không thấp hơn E0 quá **ĐỀ XUẤT: 2 điểm phần trăm** (Lực quyết số này trước khi khóa; nêu mức tụt thật dù nhỏ) và AUROC không tụt có CI loại 0.
3. Không có nguồn AI nào (SD1.4, Midjourney, GLIDE) mà recall tụt quá **ĐỀ XUẤT: 5 điểm phần trăm**.

**Điểm vận hành cố định (C4):** khi so Ex với E0, giữ nguyên ngưỡng của E0 (0,3 / 0,5 / 0,7) hoặc so ở cùng FPR GenImage đã khóa trước khi chạy; không so một model ở ngưỡng đã dịch với E0 ở ngưỡng cũ. **E4 (hiệu chuẩn, ngưỡng) chỉ là dịch điểm vận hành, không phải model tốt hơn** (không đổi thứ tự điểm, AUROC giữ nguyên); E4 không được ghi "cải thiện" theo mục này, chỉ ghi "đổi điểm vận hành" kèm mức tụt recall và accuracy. Báo kèm số recall AI từng nguồn GenImage và (ADV-06) recall ảnh AI như số tham khảo, không chỉ "không tụt quá 5 điểm".

**Sức mạnh thống kê ở miền ảnh điện thoại (C2):** #116 chỉ có 38 ảnh thật (Wilson 95% của tỉ lệ gọi AI ở E0: 60,8% đến 87,0%). Với n = 38 hiệu hai model chỉ phân biệt được khi rất lớn; mỗi báo cáo ghi mức hiệu tối thiểu phát hiện được (tính từ bootstrap theo nhóm của chính cohort) và **"không đủ sức để kết luận" là kết cục hợp lệ** cho mọi Ex ở miền điện thoại, không bị coi là thất bại của thí nghiệm.

Không đủ ba điều thì ghi "chưa phân biệt được" hoặc "không cải thiện" kèm số. Không dựa vào ADV-06 để tuyên bố cải thiện. Không ghi "đạt 90%" cho ảnh điện thoại. Cải thiện trên mẫu nhỏ chỉ là gợi ý, không đổi model phục vụ API (đổi model là PR riêng kèm QA độc lập, #59).

**Chọn "model tốt nhất của E0..E3" cho E4 và E5:** ĐỀ XUẤT: model thỏa tiêu chí 2 và 3 trên validation có tỉ lệ ảnh thật bị gọi AI thấp nhất; hòa trong CI thì chọn model có số đặc trưng nhỏ hơn. Lực chốt trước khi chạy E0..E3.

## 5. Quy tắc validation-only
- Chọn model, đặc trưng, C, tăng cường, hiệu chuẩn và ngưỡng (0,5; vùng 0,3 đến 0,7 hoặc ngưỡng theo `target_fpr`) **chỉ trên validation**, rồi khóa.
- Platt và temperature scaling đơn điệu nên không đổi thứ tự điểm (xem lưu ý E4 ở kế hoạch); ngưỡng từ GenImage chưa chắc đúng cho ảnh điện thoại, ghi như giới hạn.
- Tập cuối chấm một lần bằng lệnh đã ghi trong protocol, không đổi gì sau đó. Số không đạt vẫn báo.
- Thiết kế này lập **sau khi đã thấy** kết quả ADV-06 (64/76 ảnh thật bị gọi AI) **và kết quả E0 trên #116 (29/38)**, và ghi rõ như vậy trong báo cáo.
- **Giới hạn của miền đích (C1):** mọi lựa chọn trên validation GenImage đo tỉ lệ ảnh thật bị gọi AI của **ảnh ImageNet trong GenImage**, không phải của ảnh điện thoại. ADV-12 vì vậy **không tối ưu được trực tiếp cho miền đích**: ADV-06 chỉ dùng để quyết "có thể là hướng đúng" (kiểm chuyển miền, ghi số), không để chọn model một mình và không để tuyên bố cải thiện; mọi cải thiện ở miền điện thoại chỉ ghi nhận, không chứng minh.

## 6. Môi trường (ghi trong mỗi protocol JSON)
Python 3.12.14, Pillow 13.0.0, venv mới; `python -m models.run_info` (trường `environment`, PR #135) và `pip freeze` lưu cùng kết quả; commit sạch (`git status` rỗng); model, labels, đặc trưng, tập từng split ghi SHA256; CLIP revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f` offline (`HF_HUB_OFFLINE=1`); E3 ghim thêm revision và hash ViT-L/14. Máy, hệ điều hành, giờ UTC+7. Người **viết**, người **chạy**, người **tính lại** ghi riêng; số tự đo ghi là tự đo.

## 7. Khóa và báo cáo
Mẫu protocol JSON ở mục 5 của kế hoạch (`status` `proposed` đến `locked` khi Lực kiểm hash). `independent_qa_approved` giữ `false` tới khi người khác tính lại. Báo cáo cuối: bảng theo mục 3, kết luận theo mục 4, các hạn chế (mẫu ảnh điện thoại nhỏ, chủ yếu iPhone 11; shortcut JPEG/dung lượng ADV-10 chưa loại trừ; không kết luận "nhận ra dấu vết AI tổng quát").

## 8. Cần Lực quyết trước khi khóa
1. ~~Hai số ĐỀ XUẤT ở mục 4 (2 điểm, 5 điểm) và tiêu chí chọn model.~~ **Đã chốt 16/11** theo đề xuất; chữ ĐỀ XUẤT ở mục 4 giữ lại làm dấu vết lịch sử.
2. Có chấm test GenImage lần hai cho model mới không (test đã mở một lần cho e571).
3. Cohort #116 đã sẵn sàng chưa (ảnh cá nhân nằm trên máy Loan, #160) và ai chạy.
4. Người tính lại độc lập.
