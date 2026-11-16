# Nháp chờ Lực khóa: protocol G02 H4, control dương và âm cho probe pixel

**Nháp chờ Lực khóa. Không đổi G02 của lượt nghiệm thu 17/11 (chưa đạt). ADV-06 chỉ là số tham khảo, không dùng chọn hay xếp hạng. Chưa chạy thí nghiệm nào.**

**Trạng thái:** `proposed`, bản 2.1 sau phản biện độc lập của Tester. Lực đã quyết (16/11): bước 0 tái lập trên test; mọi control và ngưỡng trên validation; ADV-06 không dùng xếp hạng hay chọn. Mã gốc của probe: `scripts/metadata_audit.py`.

## 0. Kiểm lại phản biện với dữ liệu thật (người soạn tự đo, chưa ai tính lại)
| Điểm | Kết quả kiểm | Ý kiến |
|---|---|---|
| A1 null theo n | Mô phỏng lại (điểm ngẫu nhiên độc lập nhãn, 4000 lần): p99 của null: 75/75 = 0,623; 150/150 = 0,586; 210/211 = 0,572; 225/225 = 0,572; 421/450 = 0,549; 421/150 = 0,574; test 399/450 = 0,550; 399/150 = 0,572; 1000/1000 = 0,534. Khớp T-24b (20.000 lần) ±0,003. **Số đếm hiện hành từ `data/labels.csv` (tôi đếm lại):** validation: ảnh thật GenImage 421, mỗi nguồn AI (glide, midjourney, sd14) 150, CIFAKE 150 thật + 150 AI; test: ảnh thật GenImage 399, mỗi nguồn AI 150, CIFAKE 1000/1000. (Số 450/450 trong `metadata_audit.json` đã commit là của bản labels cũ, không dùng.) | **Đồng ý.** Ngưỡng 0,55 nằm dưới p99 của null ở hầu hết lát cắt |
| A2 định dạng = nhãn | `docs/reports/ml-filesize-baseline.json` `raw_stats`: ảnh thật 100% JPEG (2708/2708), GLIDE, Midjourney, SD1.4 đều 100% PNG (1000/1000) | **Đồng ý.** Bước "xáo trong nhóm cùng định dạng" vô hiệu; bỏ |
| A5 split | `scripts/metadata_audit.py::evaluate` đo trên `split == "test"` (dòng 113) | **Đồng ý một phần:** G02 theo định nghĩa đo trên test và 0,72–0,97 cũng vậy, nên tái lập số cũ **phải** trên test. Nhưng "không dùng test" của protocol ADV-12 là về *chọn* model/ngưỡng; H4 không chọn gì. Đề xuất ở mục 2: bước 0 tái lập trên test chỉ để so, mọi control chạy trên validation; Lực quyết |
| A8 | Probe pixel được phép tách ảnh thật/AI một cách chính đáng | Đồng ý, thêm điều cấm ở mục 6 |
Các điểm còn lại (A3, A4, A6, A7, A9, A10) là lỗi thiết kế, tôi không có dữ liệu để kiểm thêm; sửa ở các mục dưới.

## 1. Giả thuyết
A_eff của probe 4 đặc trưng pixel (`bytes_per_px`, `blockiness`, `hf_energy`, `noise_std`) có thể đo (a) tín hiệu thật giữa hai phân phối, hoặc (b) lỗi thiết kế probe/chia dữ liệu/nhiễu mẫu nhỏ. H4 chỉ trả lời "probe có tự bịa tín hiệu không và có nhạy với nén không", **không** nói đó là đường tắt hay dấu vết chính đáng.

## 2. Bước (theo thứ tự, mọi tham số khóa trước)
0. **Tái lập (không phải thí nghiệm mới):** chạy lại probe gốc (mã `metadata_audit.py` ở commit `6ce2c455`, cùng seed và phụ thuộc) trên **test** và so **SHA256 của báo cáo** với báo cáo Kiệt/Loan đã tái lập (`bb6265ce…eda3`, #147). **Tái lập = SHA256 trùng từng byte**; khác ⇒ dừng và báo, không dùng dung sai số. Ghi là tái lập, không dùng để chọn hay chỉnh gì; test không được dùng ở bước 2–5 (ngoài việc phát hiện trùng ở bước 5). Ghi thêm null theo cỡ test (hoán vị nhãn, 399/450, 399/150, 1000/1000: p99 ≈ 0,550, 0,572, 0,533) để đặt 0,72–0,97 cạnh đúng n của chúng.
1. **Khóa đầu vào:** `labels.csv` (SHA256), split theo `group_id`, danh sách lát cắt kèm **số ảnh mỗi lớp trong validation**, 4 đặc trưng và tham số probe, seed, Python 3.12.14, Pillow 13.0.0, `pip freeze`, commit sạch.
2. **Tính ngưỡng null (đây KHÔNG phải control, không có "đạt/hỏng"):** với mỗi lát cắt validation, hoán vị nhãn **theo group** 1000 lần (train và validation), fit trên train, đo A_eff trên validation. **Ngưỡng của lát cắt = phân vị 99 của null đó.** Bước này chỉ cho ngưỡng dùng ở bước 3. Tính null cho **cả 5 lát cắt thật và 3 lát cắt giả G1–G3**; null theo mô phỏng điểm ngẫu nhiên (p95 / p99): G1 210/211 = 0,555 / 0,572; G2 225/225 = 0,553 / 0,571; G3 150/150 = 0,566 / 0,586; 75/75 = 0,593 / 0,619 (không hợp lệ). Khi tính lại bằng hoán vị thật thì dùng số của hoán vị, các số này chỉ để ước lượng trước.
3. **Control âm thật (nền giả-lớp):** chia ngẫu nhiên theo group thành hai nửa giả "A" và "B" **trong cùng một lớp**, nhãn giả theo nửa **gán cả ở train lẫn validation** (cùng cách chia theo group), fit trên train và đo A_eff trên validation. **Ba lát cắt giả, khóa trước:** (G1) ảnh thật GenImage 421 → 210/211; (G2) AI GenImage gộp 450 → 225/225; (G3) CIFAKE gộp thật + AI 300 → 150/150 (nhãn thật bị trộn ngẫu nhiên vào hai nửa; null p99 0,586). Từng nguồn AI (150 → 75/75) và CIFAKE thật riêng (150 → 75/75) **không hợp lệ** (dưới 100/lớp, null p99 > 0,62): báo thông tin, **không tính** vào kết luận. **Một lát cắt giả vượt p99 của chính null ⇒ "Âm hỏng"** (mục 4), không có đường "ghi lại, không kết luận".
4. **Control dương trên nền ở bước 3:** áp một phép nén lại đã biết lên **mọi ảnh của nửa giả "B"**, ba mức chất lượng JPEG d1 < d2 < d3 theo độ mạnh tăng dần, do Lực chọn **trước khi xem** (ghi giờ khóa), mỗi mức một lượt, trên ba lát cắt giả G1–G3. Với mỗi mức ước lượng ΔA_eff = A_eff(sau nén) − A_eff(nền bước 3) bằng **bootstrap ghép cặp theo group** (cùng ảnh trước/sau nén, 2000 lần, seed 42). **Đạt** khi, ở mỗi lát cắt giả: (i) cận dưới CI 95% của Δ(d3) > 0; và (ii) với k = 1, 2: cận dưới CI 95% của [Δ(d_{k+1}) − Δ(d_k)] ≥ −0,02 (ĐỀ XUẤT, Lực chốt số này: "không giảm theo liều" nghĩa là không có mức mạnh hơn nào kém hẳn mức nhẹ hơn quá 0,02).
   - **Giai đoạn gắn nén (khóa trước, báo cả hai):** (P1, chính) trên ảnh gốc, trước chuẩn hóa, rồi chuẩn hóa thật (JPEG95 một lần), rồi probe; (P2, phụ) gắn nén sau chuẩn hóa. P1 phản ánh pipeline thật nhưng chuẩn hóa có thể làm giảm dấu nén; chênh lệch P1–P2 là thông tin, không phải lỗi. Kết luận dùng P1.
5. **Kiểm gần-trùng xuyên split** (test chỉ được dùng ở đây để phát hiện trùng, không dùng chọn gì): đếm cặp train/validation/test có dHash ≤ 4 trên ảnh đã chuẩn hóa (cùng tiêu chí `group_id`), và khoảng cách gần nhất trong không gian 4 đặc trưng giữa validation và train. **Kết cục viết trước:** có > 0 cặp dHash ≤ 4 xuyên split ⇒ ghi "rò rỉ gần-trùng", loại các group đó khỏi mọi lát cắt và **lặp lại bước 2–4 một lần** theo quy tắc này (không thêm quy tắc khác); sau khi loại group, **kiểm lại tính hợp lệ của từng lát cắt** (≥ 100/lớp và null p99 ≤ 0,60, tính lại theo cỡ mới); lát cắt không còn hợp lệ thì loại và áp quy tắc "ít hơn 3 lát cắt hợp lệ" ở mục 3; không có cặp nào ⇒ ghi "không thấy gần-trùng bằng dHash". Khoảng cách trong không gian đặc trưng **chỉ báo, không có ngưỡng**. **Giới hạn đã biết:** cặp "cùng prompt" của máy sinh ảnh không bắt được bằng hash; không khẳng định "không rò rỉ".
6. **Báo cáo theo từng đặc trưng và từng lát cắt** (không chỉ tổng); báo cỡ mẫu, phân vị null, CI.

## 3. Quy tắc tổng hợp lát cắt (viết trước)
- Lát cắt **hợp lệ** khi mỗi lớp trong validation ≥ 100 (`MIN_PER_CLASS`) **và** null p99 ≤ 0,60. Bước 3/4 dùng đúng **3 lát cắt giả** G1–G3 ở trên (cả ba hợp lệ theo số đếm hiện hành; nếu labels khóa khác thì tính lại và ghi). Bước 2 (ngưỡng) tính cho 5 lát cắt thật: GenImage all, `real_vs_glide`, `real_vs_midjourney`, `real_vs_sd14`, CIFAKE.
- Ít hơn 3 lát cắt hợp lệ (cho từng bước) ⇒ "không đủ sức để kết luận", không sang H1.
- **Control âm "đạt"** khi cả ba G1–G3 ≤ p99 của null của chính chúng. **Control dương "đạt"** khi cả ba đạt (i) và (ii) ở bước 4 với P1.
- **Đa phép kiểm:** α = 1% cho mỗi phép (ba lát cắt giả × một control âm, ba lát cắt giả × ba mức nén). Không hiệu chỉnh chung cho toàn nhóm; các lát cắt chồng lấn nên không độc lập. Ghi như giới hạn: tỉ lệ báo động giả chung không được kiểm soát chặt, nên một lần "hỏng" lẻ loi cần đọc cùng cỡ mẫu và CI, không chỉ cờ.

## 4. Kết cục được phép (viết trước)
| Kết quả | Điều kiện | Kết luận được phép |
|---|---|---|
| Âm đạt, dương đạt | theo mục 3 | probe không tự bịa tín hiệu ở các lát cắt hợp lệ và nhạy với nén. **Không** gọi A_eff cao là shortcut hay là dấu vết chính đáng; chỉ sang H1 |
| Âm hỏng | một lát cắt giả (G1–G3) vượt p99 của chính null ở bước 3 | probe hoặc chia dữ liệu tự sinh tín hiệu trong cùng một lớp: số 0,72–0,97 không đáng tin; ghi "chưa đạt, probe chưa đáng tin"; protocol mới để sửa |
| Dương hỏng | (i) hoặc (ii) ở bước 4 không thỏa | probe mù với nén ở mức đã thử: A_eff thấp không có nghĩa là sạch; ghi giới hạn |
| Không đủ sức | mục 3 | không kết luận; không dùng như "đạt" |
Kết quả nào cũng không làm G02 đạt và không đổi 0,55.

## 5. Điều không được làm
Không hạ 0,55, không đổi đặc trưng/split/seed/tham số/mức nén sau khi thấy số; không dùng test hay ADV-06 để chọn (bước 0 chỉ tái lập); không chạy lại để "được xanh" (lượt hỏng giữ và báo); không bỏ lát cắt vì kết quả xấu (chỉ loại theo quy tắc hợp lệ mục 3, tính trước khi chạy); không tuyên bố G02 đạt hay model "sạch shortcut"; không gọi A_eff cao là shortcut khi chưa tách nguyên nhân; không ghi QA độc lập khi chưa ai tính lại.

## 6. Người chạy và người tính lại
Khác nhau, do Lực chỉ định. Người tính lại **tự viết lại** phần hoán vị, chia nửa giả và gắn nén (không chạy lại cùng script), từ labels đã khóa; nếu không thì ghi "chạy lại cùng mã, chưa độc lập". Ghi giờ khóa protocol, số lần hoán vị (đề xuất 1000) và ba mức chất lượng.

## 7. Hạn chế
Control dương tổng hợp không đại diện mọi shortcut; probe chỉ 4 đặc trưng; nén lại ở P1 có thể bị chuẩn hóa JPEG95 làm giảm; số đếm theo lát cắt phải lấy từ labels khóa (số trong audit đã commit có thể cũ).

## 8. Cần Lực quyết trước khi khóa
(1) Đã quyết (16/11): bước 0 tái lập trên test; control và ngưỡng trên validation. (2) Ngưỡng null p99, null p99 ≤ 0,60, tối thiểu 3 lát cắt hợp lệ, dung sai −0,02 ở bước 4(ii); dung sai +0,02 của H1 (đơn điệu M1→M2). (3) Ba mức chất lượng JPEG (Lực chọn trước khi xem). (4) Người chạy, người tính lại.
