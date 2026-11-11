# ADV-09 — Kiểm tra độc lập bộ dữ liệu mở rộng (#54)

Người kiểm: Loan (Data & Evaluation). Bộ được kiểm: `realcheck_mixed_v3` do Kiệt tạo ở PR #61 ([biên bản](ml-data-expansion-20261110.md), [báo cáo JSON](reports/ml-data-expansion-20261110.json)). Người kiểm khác người làm dữ liệu, theo quy tắc trong `tests/README.md`.

**Trạng thái: chưa đạt.** Có một vấn đề rò rỉ cần xác nhận trước khi dùng bộ này cho bất kỳ kết luận nào. Số liệu dưới đây là số thực nhận đã ghi trong báo cáo của Kiệt, không phải số dự kiến. Phần kiểm bằng ảnh dùng **mẫu cùng nguồn do Loan tải**, không phải đúng các ảnh Kiệt chọn; manifest chi tiết của Kiệt (`labels.csv`, `selection.jsonl`) chưa có trên Git.

## Số thực nhận

Theo nguồn (sau lọc, trước khi tách validation mới):

| Nguồn | Thật | AI | Dự kiến tối đa | Thiếu |
|---|---:|---:|---|---|
| Tiny-GenImage (14 shard train) | 2.300 | 2.000 (ADM, GLIDE, Midjourney, SD1.5, Wukong × 400) | 2.300 / 2.000 | 0 |
| OpenFake core/train | 966 | 1.378 | 1.180 / 1.770 | 214 thật, 392 AI |
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
| Validation nguồn mới | 989 | ~15% mỗi nhóm nguồn ngoài Tiny; VISION giữ nguyên máy D06, D10, D13, D21, D32 |
| Validation GenImage (giữ nguyên) | 871 | Bộ A, để so với model e571 |
| OpenFake core/test (chỉ đánh giá) | 1.040 | 520 / 520 |
| OpenFake reddit (chỉ đánh giá) | 840 | 420 / 420 |

Lọc: 8.438 ảnh loại vì CLIP cho là không phải ảnh chụp; 262 vì metadata (anime, video, gắn cờ); 55 trùng hoặc gần trùng trong pool; 6 trùng tập đánh giá hoặc lịch sử; 3 gần validation/test lịch sử.

## Kết quả kiểm theo 5 ưu tiên

### 1. Cân bằng thật/AI
Tổng gần cân (51,5% thật), nhưng lệch trong từng nguồn: OpenFake 41% thật; COCO, VISION, FFHQ, Landscapes HQ 100% thật; Community Forensics 100% AI. Xem mục 5 về hệ quả.

### 2. Rò rỉ giữa train, validation, test
- **Tiny-GenImage dùng chung shard với validation và test của bộ A.** 1.500 ảnh GenImage val/test của bộ A (thật, GLIDE, Midjourney) lấy từ shard train 0–6 của Tiny-GenImage, trong khi bộ mới lấy train từ cả 14 shard train của cùng bộ này.
- **Kiểm trên mẫu của Loan** (4.345 ảnh lấy ngẫu nhiên từ 11 shard train Tiny-GenImage): **145 ảnh trùng validation và 130 ảnh trùng test của bộ A**, xác nhận cùng byte bằng SHA256 (716/716 cặp có đủ file). Tức lấy ngẫu nhiên mà không loại trừ thì khoảng 6% ảnh rơi vào val/test của bộ A.
- Báo cáo của Kiệt chỉ ghi loại 9 ảnh (6 trùng đánh giá hoặc lịch sử, 3 gần val/test). **Chưa xác định được** Kiệt đã loại các ảnh này từ trước khi chọn hay bộ mới đang chứa chúng. Nếu có rò rỉ, độ chính xác 86,45% trên validation GenImage của model mixed bị thổi phồng.
- OpenFake core/reddit chỉ dùng để đánh giá, không có trong train (theo báo cáo). Ảnh thật trùng giữa OpenFake core/train và core/test đã qua lọc dHash trong pool.
- Validation nguồn mới chia **theo từng ảnh** (15% đầu mỗi nhóm theo thứ tự xếp hạng), không theo `group_id`. Ảnh gần trùng đã bị dHash loại trước, nên rủi ro thấp nhưng chưa đúng yêu cầu chia theo nhóm (FR-D03, AC-18).

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
- **Nguồn gần như trùng nhãn.** Chỉ cần biết ảnh đến từ nguồn nào (đoán theo nhãn đa số của nguồn đó trong train): đúng **72,9%** trên toàn bộ dữ liệu, và **85,3% trên validation nguồn mới** (844/989). Model mixed chỉ đạt 81,9% trên tập này, **thấp hơn đoán theo nguồn**. Vậy validation nguồn mới không chứng minh được model học dấu vết AI; phải đọc kết quả theo từng nguồn, nhất là OpenFake (nguồn duy nhất có cả hai nhãn): ảnh thật 64,1%, ảnh AI 79,2%.
- **Shortcut dung lượng file** (trên mẫu của Loan, ảnh đã chuẩn hóa; AUROC chỉ dùng dung lượng, 0,5 là không phân biệt được): Tiny thật vs GLIDE **0,906**, vs Midjourney 0,731, vs ADM 0,663, vs Wukong 0,604, vs SD1.5 0,548; OpenFake thật vs AI 0,551; gộp nguồn mới 0,552. Shortcut GLIDE đã biết vẫn còn; nguồn mới không thêm shortcut dung lượng đáng kể.
- **Nhãn "thật" của LAION/Pexels** có thể lẫn ảnh AI. Bộ lọc dùng CLIP, Kiệt xem tay 92 ảnh; chưa có kiểm tay riêng cho nhãn thật.
- **COCO "trước 2019 nên là ảnh thật"** là giả định, chưa kiểm.
- **Bộ dữ liệu chưa tái lập được từ repo sạch:** lệnh tải cần catalogue và pool cũ trên máy Kiệt; `labels.csv` và `selection.jsonl` chưa có trên Git, nên QA chưa tự kiểm lại được.

## Danh sách vấn đề

| # | Vấn đề | Mức |
|---|---|---|
| 1 | Xác nhận Tiny-GenImage train không chứa ảnh val/test của bộ A: chạy `scripts.check_tiny_overlap` trên `labels.csv` của bộ mới | **Bắt buộc** |
| 2 | Đưa `labels.csv` và `selection.jsonl` (bỏ đường dẫn cá nhân; thêm `dhash`, `file_size`) lên Git để QA tái lập | **Bắt buộc** |
| 3 | Báo cáo kết quả theo từng nguồn, không dùng một con số validation nguồn mới làm bằng chứng (đoán theo nguồn đã đạt 85,3%) | **Bắt buộc** |
| 4 | Ghi giấy phép từng nguồn vào `data/README.md` (đã làm trong nhánh này; Landscapes HQ chưa xác nhận được) | **Bắt buộc** |
| 5 | Chia validation nguồn mới theo `group_id`, manifest có `sample_id`, hash, `group_id`, công cụ | Làm sau |
| 6 | Kiểm dHash bộ mới với validation 1.309 ảnh, bộ độc lập 1.603 ảnh và test kín | Làm sau (khi có `selection.jsonl`) |
| 7 | Kiểm tay mẫu ảnh thật LAION/Pexels; ghi COCO là giả định | Làm sau |
| 8 | Script tải tái lập được từ repo sạch | Làm sau |

## Lệnh tái lập

```bash
# Rò rỉ theo shard/dòng Tiny-GenImage (thoát 1 nếu có trùng); --verify-sha so byte khi có cả hai file
python -m scripts.check_tiny_overlap --protected data/labels.csv --candidates <labels.csv của bộ mới> --verify-sha
# Rò rỉ gần trùng giữa các split của một manifest (dHash)
python -m scripts.check_data --labels <labels.csv của bộ mới>
```

Con số "đoán theo nguồn" tính từ bảng số thực nhận: mỗi nguồn đoán theo nhãn đa số của nó trong train (Tiny → thật, OpenFake → AI, COCO/VISION/FFHQ/Landscapes → thật, Community Forensics AI → AI). Trên validation nguồn mới: 207 OpenFake AI + 349 ảnh thật cộng đồng + 288 Community AI = 844/989.

Mẫu kiểm của Loan: 4.345 ảnh Tiny-GenImage, 2.089 OpenFake, 590 VISION, 650 Community Forensics, cùng các bộ trên Hugging Face với PR #61 (chưa đối chiếu revision); ảnh và đặc trưng không nằm trong Git.
