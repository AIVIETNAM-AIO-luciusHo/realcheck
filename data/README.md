# data/ – Dữ liệu

Phụ trách: Loan

## Làm gì
Tải, chuẩn hóa và chia tập dữ liệu. Nhãn lấy theo thư mục (real = 0, ai = 1).

**Luồng ML mới (normalization version 1):** dùng chung `models.normalize`; loại ảnh GenImage cạnh ngắn <256 thay vì phóng to, CIFAKE vẫn giữ 32×32. Manifest mới thêm `norm_version`. Để không ghi đè dữ liệu/manifest cũ đang được nhóm review:

```bash
python -m scripts.prepare_data --output-dir .cache/ml-run/processed-v1 --labels .cache/ml-run/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-run/labels.csv
```

Output đã tồn tại thì chọn đường dẫn mới. `data/labels.csv` và số đo cũ bên dưới giữ làm tham chiếu, không phải kết quả sau loại ảnh nhỏ. Lần chạy mới có 9.708 ảnh (4.000 CIFAKE + 5.708 GenImage), loại 292 ảnh thật quá nhỏ; chi tiết trong [`models/README.md`](../models/README.md), [`docs/ml-handoff.md`](../docs/ml-handoff.md). Chưa đối chiếu baseline trên máy Loan; không đánh dấu T012/T013 hoàn thành.

Checker hiện yêu cầu manifest có sáu cột với `norm_version` ở cuối và đúng version hiện hành; manifest cũ thiếu version sẽ FAIL, không tự nâng version. `prepare_data` ghi riêng ảnh quá nhỏ vào `rejected_small.csv` và ảnh hỏng/decompression bomb vào `rejected_invalid.csv`, cạnh thư mục output. Cả hai danh sách giữ đường dẫn, source, kích thước, lý do và version để QA đối chiếu.

| Đường dẫn | Nội dung |
|---|---|
| `raw/` | Ảnh gốc tải về, không sửa |
| `processed/` | Ảnh đã làm sạch, cùng JPEG, cùng chất lượng và kích thước |
| `features/` | Kết quả CLIP (`.npy`) |
| `labels.csv` | `filepath, label, source, split, raw_path` |
| `metadata_audit.json` | Kết quả kiểm tra rò rỉ metadata (gate) |
| `processed_baseline.sha256` | Metadata mã băm của dữ liệu chuẩn hóa trước khi đổi pipeline (T012), chỉ gồm sha256, **không chứa ảnh** |
| `baseline_filesize.json` | Dung lượng file theo nguồn (chỉ tham khảo độ chi tiết ảnh) |

Nguồn: CIFAKE (Kaggle), GenImage (NeurIPS 2023), ảnh nhóm tự chụp/tạo, ảnh qua Zalo.

## Cách chạy
Từ thư mục gốc repo:
```bash
pip install -r scripts/requirements-data.txt
python -m scripts.download_data cifake     # D1: ~16MB
python -m scripts.download_data genimage   # D2: tải ~4GB từng phần, giữ lại ~1.5GB
# Chuẩn hóa và kiểm tra: dùng bộ đường dẫn riêng ở đầu README này.
# Lệnh audit/baseline cho bộ mới: xem docs/ml-handoff.md.
```
Chạy lại cho cùng kết quả (seed 42). `download_data.py genimage` chạy tiếp được nếu bị ngắt.

## Input / Output
- Input: dataset công khai trên Hugging Face và ảnh tự thu thập.
  - CIFAKE: [`dragonintelligence/CIFAKE-image-dataset`](https://huggingface.co/datasets/dragonintelligence/CIFAKE-image-dataset), lấy 1.000 ảnh mỗi lớp ở mỗi split train/test.
  - GenImage: 3.000 ảnh thật (ImageNet) + 1.000 ảnh mỗi nguồn Midjourney, GLIDE, SD v1.4.
    - Ảnh thật, Midjourney, GLIDE: [`TheKernel01/Tiny-GenImage`](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage) (bản thu nhỏ của GenImage).
    - SD v1.4: Tiny-GenImage không có, lấy từ split test của [`nebula/GenImage-arrow`](https://huggingface.co/datasets/nebula/GenImage-arrow) (shard `data-00004`, toàn ảnh AI).
- Output: `processed/`, `labels.csv`, `metadata_audit.json`, `baseline_filesize.json`.

### labels.csv
| Cột | Ý nghĩa |
|---|---|
| `filepath` | Ảnh đã chuẩn hóa, tính từ gốc repo, ví dụ `data/processed/genimage/sd14/sd14_00012.jpg` |
| `label` | 0 = ảnh thật, 1 = ảnh AI |
| `source` | `genimage_real`, `genimage_sd14`, `genimage_midjourney`, `genimage_glide`, `cifake_real`, `cifake_ai` |
| `split` | `train`, `val`, `test` |
| `raw_path` | Ảnh gốc tương ứng trong `raw/` |

Lọc theo `source`: chỉ dùng `genimage_*` cho mô hình chính; `cifake_*` chỉ để chạy thử.

## Thông số chuẩn hóa
| Thông số | Giá trị | Ghi chú |
|---|---|---|
| Kích thước | 256×256 | Resize cạnh ngắn rồi center-crop; CIFAKE giữ 32×32 |
| Định dạng | JPEG chất lượng 95, RGB, bỏ EXIF | Cao hơn các mức 90/70/50 của thí nghiệm nén |
| Chia tập GenImage | 70 / 15 / 15 | Phân tầng theo `source`, seed 42 |
| Chia tập CIFAKE | train gốc → 85% train / 15% val; test gốc → test | |
| Ảnh trùng | Bỏ ảnh trùng pixel sau chuẩn hóa; trùng khác nhãn thì bỏ cả hai | |

### Nén JPEG hai lần
Ảnh thật (ImageNet) vốn là JPEG nên khi lưu lại bị nén 2 lần, còn ảnh AI (PNG) chỉ nén 1 lần; mô hình có thể học dấu vết nén này thay vì dấu vết AI. Vì vậy `prepare_data.py` **crop/resize về 256×256 trước, rồi mới nén JPEG**: đổi kích thước làm lệch lưới khối 8×8 của lần nén cũ, giảm dấu vết nén trước đó.

| Ảnh thật gốc (3.000) | Số ảnh | Lưới nén cũ |
|---|---|---|
| Thu nhỏ (cạnh ngắn > 256) | 2.706 | Bị lệch |
| Phóng to (cạnh ngắn < 256) | 292 | Bị lệch, nhưng ảnh mờ (xem Hạn chế) |
| Chỉ crop, không đổi kích thước (= 256) | 2 | Có thể còn; 1 ảnh lưới cũ trùng lưới mới |

Cách này **giảm thiểu**, không chứng minh xóa hết dấu vết nén 2 lần.

## Kiểm tra rò rỉ metadata (gate)
Probe chỉ đọc metadata (định dạng, kích thước, mode, EXIF, ICC, bảng lượng tử và subsampling JPEG), không dùng pixel, dung lượng file, đường dẫn hay nguồn. Gate áp cho ảnh đã chuẩn hóa: `A_eff = max(AUROC, 1-AUROC) <= 0.55`. Chi tiết: `metadata_audit.json`.

| GenImage (test) | Ảnh gốc | Đã chuẩn hóa |
|---|---|---|
| Tất cả nguồn | 1.00 | 0.50 |
| Thật vs SD v1.4 | 1.00 | 0.50 |
| Thật vs Midjourney | 1.00 | 0.50 |
| Thật vs GLIDE | 1.00 | 0.50 |

Ảnh gốc lộ nhãn hoàn toàn (thật là JPEG nhiều kích thước, AI là PNG kích thước cố định); sau chuẩn hóa mọi metadata giống nhau. Control dương 1.00, control âm 0.51. Probe, protocol và cỡ mẫu tối thiểu (D03/D04) đang dùng giá trị tạm.

### Dung lượng file (chỉ tham khảo)
Sau khi nén cùng chất lượng, dung lượng file phản ánh **độ chi tiết của ảnh** (tương quan Spearman 0.94 với mật độ cạnh), không phải rò rỉ định dạng, nên không dùng làm gate. Trung vị sau chuẩn hóa: thật 31KB, SD v1.4 32KB, Midjourney 24KB, GLIDE 18KB.

### Hạn chế đã biết
- **Ảnh AI mịn hơn ảnh thật**, rõ nhất ở GLIDE (ảnh gốc 256×256, ít chi tiết), rồi đến Midjourney. Đây là khác biệt nội dung, metadata đã sạch. Rủi ro: mô hình học "ảnh mịn = AI" và gọi oan ảnh thật ít chi tiết; khi đánh giá cần báo accuracy **theo từng `source`** và tỷ lệ gọi oan trên ảnh thật mịn.
- **292/3.000 ảnh thật có cạnh ngắn dưới 256px** nên bị phóng to khi chuẩn hóa và mờ hơn các ảnh khác; ảnh AI không có trường hợp này. Rủi ro: mô hình học "ảnh mờ = ảnh thật". Tạm giữ, sẽ thay bằng ảnh thật có cạnh ngắn ≥ 256px.

## Lưu ý và giả định
- Không commit ảnh và `.npy` (đã gitignore); chỉ commit `labels.csv` và README.
- Dữ liệu chỉ dùng cho học tập; trích dẫn GenImage, CIFAKE trong báo cáo. Tiny-GenImage có giấy phép CC BY-NC-SA 4.0.
- CIFAKE trên Hugging Face gán `0 = FAKE, 1 = REAL`; script đã đổi về quy ước của nhóm.
- Tránh chụp mặt người lạ.
- Gate dữ liệu là kiểm tra metadata (post `A_eff <= 0.55`), không phải dung lượng file. Gate đạt không chứng minh hết mọi shortcut trong pixel.
