# Nháp chờ Lực khóa: protocol G02 H1, nén lại để tách tác động nén

**Nháp chờ Lực khóa. Không đổi G02 của lượt nghiệm thu 17/11 (chưa đạt). ADV-06 chỉ là số tham khảo, không dùng chọn hay xếp hạng. Chưa chạy thí nghiệm nào.**

**Trạng thái:** `proposed`. Chỉ chạy khi H4 v2.1 có **cả hai control đạt** ([`g02-h4-protocol.md`](g02-h4-protocol.md)). Không đổi G02 của 17/11, không đổi 0,55, đặc trưng hay split. Thiết kế lập sau khi đã thấy A_eff 0,72–0,97 và sau T-24/T-24b. ADV-06 không dùng (chỉ là số tham khảo ngoài protocol này). Khóa riêng, mỗi protocol một lần.

## 1. Câu hỏi và điều KHÔNG kết luận
Câu hỏi: A_eff của probe 4 đặc trưng đổi bao nhiêu khi nén lại **cả hai lớp cùng mức**, so với một phép nén gần vô hại. **Không** kết luận "nén là nguyên nhân": nén mạnh cũng xóa dấu vết sinh ảnh chính đáng, nên giảm A_eff không phân biệt được hai khả năng.

## 2. Thiết kế
- **Lát cắt (validation, khóa trước):** 5 lát cắt thật của H4 (GenImage all, `real_vs_glide`, `real_vs_midjourney`, `real_vs_sd14`, CIFAKE); hợp lệ khi ≥ 100/lớp và null p99 ≤ 0,60 (số đếm hiện hành: 421 thật; mỗi nguồn AI 150; CIFAKE 150/150). Ít hơn 3 hợp lệ ⇒ "không đủ sức".
- **Phép thao tác (áp lên mọi ảnh, cả hai lớp, ảnh gốc trước chuẩn hóa rồi chuẩn hóa thật; báo thêm biến thể gắn sau chuẩn hóa):** (R) đối chứng gần vô hại: JPEG chất lượng 98, không đổi kích thước; (M1, M2) hai mức nén mạnh dần do Lực chọn trước khi xem (ghi giờ). Không đổi kích thước ở cả ba.
- **Đo:** AUC **có dấu** (AUC của lớp AI so với lớp thật, không lấy max) cạnh A_eff = max(AUC, 1 − AUC) vì A_eff che đảo chiều (một phép nén đảo dấu tín hiệu vẫn cho A_eff cao); báo cả hai. A_eff mỗi lát cắt cho: gốc (O), R, M1, M2; **từng đặc trưng riêng** (`bytes_per_px`, `blockiness`, `hf_energy`, `noise_std`) và cả bộ bốn. Bootstrap ghép cặp theo group (2000 lần, seed 42) cho ΔM = A_eff(M) − A_eff(O) và ΔR; so ΔM − ΔR **cho cả M1 và M2**; kiểm đơn điệu theo liều: ΔM2 − ΔM1 có cận trên CI 95% ≤ +0,02 khi kết luận "giảm" (ĐỀ XUẤT, Lực chốt) — tức mức mạnh hơn không được kém giảm hẳn so với mức nhẹ; kết cục ở mục 3 vẫn dựa trên M2, M1 dùng để kiểm đơn điệu.
- `bytes_per_px` bị chính phép nén ở chất lượng cố định chi phối (gần như bão hòa): **báo riêng, loại khỏi mọi kết luận về mức giảm của bộ**; báo "bộ ba còn lại" cùng bộ bốn.

## 2b. Độc lập và sức
- 5 lát cắt thật **dùng chung 421 ảnh thật** (và CIFAKE thật riêng) nên không độc lập: "≥ 2/3 lát cắt" đọc kèm điều này, không tính như ba phép kiểm độc lập.
- **Ước lượng sức (tự đo, điểm chuẩn hóa N(0,1)+d·nhãn, ngưỡng = p99 của null, 500 lần mỗi dòng, chưa ai tính lại):** để A_eff vượt p99 của null với xác suất ≥ 80% cần d ≈ 0,25 (AUC ≈ 0,57) ở 421/450; d ≈ 0,4 (AUC ≈ 0,61) ở 421/150; d ≈ 0,45 (AUC ≈ 0,62) ở 150/150. Hiệu nhỏ hơn thì không phát hiện được: ghi "không đủ sức" là kết cục hợp lệ. Đây là sức của một phép kiểm A_eff, không phải của ΔM − ΔR (sức của hiệu ghép cặp phải mô phỏng riêng trước khi khóa).

## 3. Kết cục viết trước (theo lát cắt hợp lệ, trên bộ ba không có `bytes_per_px`)
| Kết quả | Điều kiện | Ghi được |
|---|---|---|
| Giảm vượt đối chứng | cận trên CI 95% của (ΔM2 − ΔR) < 0 ở ≥ 2/3 số lát cắt hợp lệ | "A_eff giảm thêm so với nén gần vô hại khi nén ở M2"; không nêu nguyên nhân |
| Không phân biệt | CI của (ΔM2 − ΔR) chứa 0 | "không thấy khác biệt với đối chứng ở mức M2"; G02 vẫn chưa đạt (không kết cục nào của H1 làm G02 đạt) |
| Tăng | cận dưới CI 95% của ΔM2 > 0 | ghi nguyên văn, không giải thích |
| Đối chứng đã giảm mạnh | ΔR < −0,05 (ĐỀ XUẤT) | phép R không còn "vô hại": ghi, không kết luận thêm |
| Không đủ sức | < 3 lát cắt hợp lệ | không kết luận |
Mọi kết cục không làm G02 đạt, không đổi 0,55.

## 4. Điều không được làm
Không đổi mức nén, đặc trưng, lát cắt, seed sau khi thấy số; không dùng test hay ADV-06 để chọn; không chạy lại để "được xanh"; không loại lát cắt vì kết quả (chỉ theo quy tắc hợp lệ); không gọi A_eff cao là shortcut; không ghi "nén là nguyên nhân".

## 5. Người chạy, người tính lại, hạn chế
Khác nhau, người tính lại tự viết lại phần nén và bootstrap. Hạn chế: chuẩn hóa JPEG95 làm giảm dấu nén của M1/M2; không tách được dấu vết sinh ảnh chính đáng khỏi nén; nhiều phép kiểm (3 phép × lát cắt × đặc trưng) không hiệu chỉnh chung; cùng nhãn và split với H4 nên chịu cùng nhiễu mẫu.

## 6. Cần Lực quyết
Hai mức M1/M2 (trước khi xem), ngưỡng −0,05 của đối chứng, số lát cắt tối thiểu, người chạy và người tính lại.
