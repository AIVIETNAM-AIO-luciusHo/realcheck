# ADV-09 — Kiểm tra độc lập bộ dữ liệu mở rộng (#54)

Người kiểm: Loan (Data & Evaluation). Bộ được kiểm: `realcheck_mixed_v3` do Kiệt tạo ở PR #61 ([biên bản](ml-data-expansion-20261110.md), [báo cáo JSON](reports/ml-data-expansion-20261110.json)), metadata bàn giao ở PR #85 ([`data/metadata/realcheck_mixed_v3/run-v2/`](../data/metadata/realcheck_mixed_v3/run-v2/README.md)). Người kiểm khác người làm dữ liệu, theo quy tắc trong `tests/README.md`.

**Trạng thái: đạt các mục bắt buộc về rò rỉ, còn 2 lưu ý khi dùng.** Kiểm trên đúng metadata của bộ (12.805 dòng `selection.jsonl`): **không có ảnh trùng hoặc gần trùng với validation/test của bộ A** (bộ chính, T023) và không rò rỉ giữa mọi cặp cohort của chính bộ mới. dHash Kiệt ghi được tính lại từ ảnh thật cho 1.438 ảnh Tiny-GenImage trong train và khớp 100%; phần còn lại dựa vào metadata (xem "Kiểm trên ảnh thật và kiểm chỉ trên metadata"). Hai lưu ý: kết quả trên validation nguồn mới không chứng minh model học dấu vết AI (mục 5), và không được chấm model mixed trên validation 1.309 ảnh của bộ B (mục 2). Giấy phép Landscapes HQ chưa xác nhận.

Lần kiểm đầu (PR #81) dùng mẫu cùng nguồn do Loan tải vì metadata chưa có; các số dưới đây đã thay bằng số trên đúng bộ của Kiệt, trừ chỗ ghi rõ là mẫu.

## Số thực nhận

Theo nguồn (sau lọc, trước khi tách validation mới):

| Nguồn | Thật | AI | Dự kiến tối đa | Thiếu |
|---|---:|---:|---|---|
| Tiny-GenImage (14 shard train) | 2.300 | 2.000 (ADM, GLIDE, Midjourney, SD1.5, Wukong × 400) | 2.300 / 2.000 | 0 |
| OpenFake core/train | 966 (571 Pexels, 395 LAION) | 1.378 | 1.180 / 1.770 | 214 thật, 392 AI |
| COCO | 885 | — | 885 | 0 |
| VISION (35 máy) | 590 | — | 590 | 0 |
| FFHQ | 470 | — | 470 | 0 |
| Landscapes HQ | 415 | — | 415 | 0 |
| Community Forensics AI | — | 1.921 (1.300 diffusion, 335 chân dung, 286 phong cảnh; 354 công cụ, tối đa 10 ảnh/công cụ) | 2.125 | 135 chân dung, 69 phong cảnh |
| **Tổng** | **5.626** | **5.299** | | |

Theo split:

| Tập | N | Ghi chú |
|---|---:|---|
| Train | 9.936 | 5.132 thật / 4.804 AI; Tiny-GenImage chỉ ở train |
| Validation nguồn mới | 989 | 494 thật / 495 AI; ~15% mỗi nhóm nguồn ngoài Tiny; VISION giữ nguyên máy D06, D10, D13, D21, D32 |
| Validation GenImage (giữ nguyên) | 871 | Validation của bộ A, để so với model e571 |
| OpenFake core/test (chỉ đánh giá) | 1.040 | 520 / 520 |
| OpenFake reddit (chỉ đánh giá) | 840 | 420 / 420 |

Theo nguồn, nhãn và split (từ `selection.jsonl`; validation GenImage 871 ảnh là validation của bộ A, không nằm trong bảng):

| Nguồn | Train thật | Train AI | Val mới thật | Val mới AI | Core thật | Core AI | Reddit thật | Reddit AI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tiny-GenImage | 2.300 | 2.000 | — | — | — | — | — | — |
| OpenFake | 821 | 1.171 | 145 | 207 | 520 | 520 | 420 | 420 |
| COCO | 752 | — | 133 | — | — | — | — | — |
| VISION | 506 | — | 84 | — | — | — | — | — |
| FFHQ | 400 | — | 70 | — | — | — | — | — |
| Landscapes HQ | 353 | — | 62 | — | — | — | — | — |
| Community Forensics AI | — | 1.633 | — | 288 | — | — | — | — |
| **Tổng** | **5.132** | **4.804** | **494** | **495** | **520** | **520** | **420** | **420** |

Lọc: 8.438 ảnh loại vì CLIP cho là không phải ảnh chụp; 262 vì metadata (anime, video, gắn cờ); 55 trùng hoặc gần trùng trong pool; 6 trùng tập đánh giá hoặc lịch sử; 3 gần validation/test lịch sử.

## Kết quả kiểm theo 5 ưu tiên

### 1. Cân bằng thật/AI
Tổng gần cân (51,5% thật), nhưng lệch trong từng nguồn: OpenFake 41% thật; COCO, VISION, FFHQ, Landscapes HQ 100% thật; Community Forensics 100% AI. Xem mục 5 về hệ quả.

### 2. Rò rỉ giữa train, validation, test
`scripts.check_mixed_leakage`, so `raw_sha256` (trùng byte) và dHash ảnh chuẩn hóa ≤ 4 (gần trùng) của từng cohort với bộ A (`data/labels.csv`, 5.708 ảnh GenImage):

| Cohort bộ mới | N | val bộ A | test bộ A | train bộ A |
|---|---:|---|---|---|
| Train | 9.936 | 0 / 0 | 0 / 0 | 749 / 751 |
| Validation nguồn mới | 989 | 0 / 0 | 0 / 0 | 0 / 1 |
| OpenFake core | 1.040 | 0 / 0 | 0 / 0 | 0 / 0 |
| OpenFake reddit | 840 | 0 / 0 | 0 / 0 | 0 / 0 |

(trùng byte / gần trùng). Trong chính bộ mới, mọi cặp cohort đều **0 trùng byte và 0 gần trùng**: train với validation nguồn mới, OpenFake core, reddit; validation nguồn mới với core và với reddit; core với reddit. Không có ảnh trùng byte trong cùng một cohort.

- **Không rò rỉ vào val/test bộ A.** Validation và test GenImage của bộ A lấy từ shard train 0–6 của Tiny-GenImage, cùng shard với train bộ mới; bộ chọn của Kiệt đã loại các ảnh đó (đối chiếu hash điểm ảnh và dHash với val/test của hai manifest lịch sử, theo README bàn giao). 749 ảnh train trùng byte với train bộ A là bình thường (train trùng train) và cho thấy phép so hash bắt được ảnh trùng khi có.
- **Mẫu không lọc thì có rò rỉ:** trên 4.345 ảnh Tiny-GenImage Loan lấy ngẫu nhiên, 145 ảnh trùng val và 130 ảnh trùng test của bộ A (`scripts.check_tiny_overlap`). Mọi lần lấy thêm ảnh Tiny-GenImage phải lọc theo bộ A như bộ chọn của Kiệt.
- **Validation 1.309 ảnh (bộ B, chưa dùng chính thức):** 221 ảnh train của bộ mới gần trùng (khoảng 17% bộ này), vì bộ B lấy validation từ shard train 2, 7, 12 của Tiny-GenImage. Không ai đang dùng bộ này để chấm model mixed; **không được dùng** nó để đánh giá model train trên bộ mới.
- **Bộ độc lập 1.603 ảnh** (shard validation 0 của Tiny-GenImage): 1 ảnh train gần trùng; không đáng kể.
- Validation nguồn mới chia **theo từng ảnh** (15% đầu mỗi nhóm theo thứ tự xếp hạng), không theo `group_id`. Kết quả 0 gần trùng giữa train và validation cho thấy rủi ro thấp, nhưng chưa đúng yêu cầu chia theo nhóm (FR-D03, AC-18).

#### Kiểm trên ảnh thật và kiểm chỉ trên metadata

Phía bộ mới, phép so dùng `raw_sha256` và `dhash` do Kiệt ghi trong `selection.jsonl`. Để không chỉ tin các giá trị này, Loan tính lại từ ảnh thật đang có trên máy cho **1.438/4.300 ảnh Tiny-GenImage trong train** (33%): 749 ảnh trùng byte với ảnh gốc của bộ A và 852 ảnh trùng byte với mẫu Tiny của Loan (hai nhóm giao nhau một phần). Kết quả: **dHash khớp 1.438/1.438**, và 852/852 ảnh chuẩn hóa giống hệt từng byte (`normalized_sha256`).

| Phép kiểm | Bộ chính (A) | Bộ mới (mixed-v3) | Val 1.309 / độc lập 1.603 |
|---|---|---|---|
| Trùng byte | Hash tính từ ảnh gốc | `raw_sha256` đã ghi | — |
| Gần trùng (dHash ≤ 4) | dHash tính từ ảnh chuẩn hóa | `dhash` đã ghi; tính lại từ ảnh thật cho 1.438 ảnh Tiny, khớp 100% | dHash tính từ ảnh |
| Giữa các cohort của bộ mới | — | Chỉ metadata | — |
| Baseline nguồn và dung lượng | — | Chỉ metadata (`stratum`, `file_size`) | — |

Chưa tính lại từ ảnh cho ảnh OpenFake và Community Forensics của bộ mới, vì không có ảnh trên máy; với các nguồn này kết luận dựa vào metadata.

### 3. Đa dạng nguồn và công cụ AI
Tốt hơn bộ A rõ rệt: ảnh AI từ 5 công cụ Tiny-GenImage, các công cụ OpenFake đời mới và 354 công cụ Community Forensics; ảnh thật có ảnh điện thoại (35 máy), cảnh đời thường, mặt người, phong cảnh.

### 4. Tổng quát hóa
Trên validation và hai tập chỉ-đánh-giá, model mixed (LR) so với model e571, cùng tập (số của Kiệt):

| Tập | N | e571 | mixed |
|---|---:|---:|---:|
| Validation GenImage | 871 | 97,24% | 86,45% |
| Validation nguồn mới | 989 | 57,94% | 81,90% |
| OpenFake core/test | 1.040 | 84,13% | 80,38% |
| OpenFake reddit | 840 | 56,67% | 75,95% |

Cải thiện rõ trên ảnh thật đời mới (OpenFake reddit, ảnh thật nguồn mới) nhưng giảm trên GenImage và OpenFake core. Chưa có số trên test GenImage chưa mở, nên chưa nói được gì về AC-25.

### 5. Rủi ro trong cách lấy mẫu
- **Nguồn gần như trùng nhãn.** Đoán theo nhãn đa số của nguồn gốc ảnh (Tiny-GenImage, OpenFake, COCO, VISION, FFHQ, Landscapes HQ, Community Forensics AI) trong train: đúng 71,6% trên train và **85,3% trên validation nguồn mới** (844/989), cao hơn model mixed (81,9%). Vậy validation nguồn mới không chứng minh được model học dấu vết AI. **OpenFake core và reddit cân bằng nhãn trong cùng một nguồn, đoán theo nguồn chỉ được 50%**, nên đây là hai tập đo đáng tin; báo kết quả theo từng nguồn, nhất là OpenFake (ảnh thật 64,1%, ảnh AI 79,2% trên validation).
- **Shortcut dung lượng file** (cột `file_size`, ảnh đã chuẩn hóa; AUROC chỉ dùng dung lượng, 0,5 là không phân biệt được): trong train, Tiny thật vs GLIDE **0,892**, vs Midjourney 0,716, vs ADM 0,666, vs Wukong 0,578, vs SD1.5 0,534; OpenFake train 0,522; toàn bộ train 0,536. Trên tập đánh giá: validation nguồn mới 0,509, OpenFake core 0,505, reddit 0,602. Shortcut GLIDE đã biết vẫn còn; nguồn mới không thêm shortcut đáng kể, reddit hơi lệch.
- **Nhãn "thật" của LAION/Pexels** có thể lẫn ảnh AI. Bộ lọc dùng CLIP, Kiệt xem tay 92 ảnh; chưa có kiểm tay riêng cho nhãn thật.
- **COCO "trước 2019 nên là ảnh thật"** là giả định, chưa kiểm.
- **Tái lập:** metadata đã có trên Git (PR #85), đủ để QA kiểm lại phần rò rỉ và baseline không cần ảnh của bộ mới; tải lại ảnh từ repo sạch vẫn cần catalogue và pool cũ trên máy Kiệt.

## Danh sách vấn đề

| # | Vấn đề | Mức | Trạng thái |
|---|---|---|---|
| 1 | Xác nhận train bộ mới không chứa ảnh val/test của bộ A | Bắt buộc | **Xong:** 0 trùng, 0 gần trùng |
| 2 | Đưa `labels.csv`, `selection.jsonl` (có `dhash`, `file_size`) lên Git | Bắt buộc | **Xong:** PR #85 |
| 3 | Báo kết quả model theo từng nguồn; dùng OpenFake core/reddit làm tập đo chính, không dùng một con số validation nguồn mới | Bắt buộc khi báo kết quả | Áp dụng cho mọi báo cáo model trên bộ này |
| 4 | Giấy phép từng nguồn trong `data/README.md` | Bắt buộc | **Xong**, trừ Landscapes HQ chưa xác nhận |
| 5 | Không đánh giá model train trên bộ mới bằng validation 1.309 ảnh của bộ B | Bắt buộc khi dùng bộ B | Mới, ghi ở mục 2 |
| 6 | Chia validation nguồn mới theo `group_id`; manifest đã có `uid` (dùng như `sample_id`), hash, nguồn, công cụ, `norm_version`, còn thiếu `group_id` | Làm sau | Chưa (Kiệt không tự đặt khi chưa chốt lineage) |
| 7a | Chạy `scripts.check_data` và metadata audit trên ảnh của bộ mới | Làm sau | Chưa: cần ảnh và schema 6 cột; đã thay bằng kiểm trên metadata (mục 2), cần QA chấp nhận |
| 7 | Kiểm tay mẫu ảnh thật LAION/Pexels; ghi COCO là giả định | Làm sau | Chưa |
| 8 | Script tải tái lập được từ repo sạch | Làm sau | Chưa |

## Lệnh tái lập

```bash
# Rò rỉ của bộ mới vào bộ chính (trùng byte và dHash <= 4) và giữa các cohort của bộ mới.
# Cần ảnh của bộ chính (data/processed, data/raw: python -m scripts.download_data rồi prepare_data theo data/README.md).
python -m scripts.check_mixed_leakage --selection data/metadata/realcheck_mixed_v3/run-v2/selection.jsonl --protected data/labels.csv
# Mẫu lấy theo tên file shard/dòng Tiny-GenImage (như mẫu của Loan)
python -m scripts.check_tiny_overlap --protected data/labels.csv --candidates <labels.csv của mẫu> --verify-sha
```

`check_tiny_overlap` chỉ dùng được khi tên file theo dạng `{nguồn}_{shard}_{dòng}`. Bộ mới đặt tên bằng mã băm nên script đó luôn báo "0 trùng" dù có trùng hay không (âm tính giả); với bộ mới phải dùng `check_mixed_leakage`.

Baseline "đoán theo nguồn" và dung lượng file tính trực tiếp từ `selection.jsonl` (cột `stratum`, `label`, `cohort`, `file_size`). Kiểm với validation 1.309 ảnh và bộ độc lập 1.603 ảnh dùng dHash của ảnh chuẩn hóa từ hai bộ đó (ảnh không nằm trong Git).
