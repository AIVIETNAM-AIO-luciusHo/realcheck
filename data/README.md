# data/ – Dữ liệu

Phụ trách: Loan

## Làm gì
Tải, chuẩn hóa và chia tập dữ liệu. Nhãn lấy theo thư mục (real = 0, ai = 1).

**Bộ dữ liệu chính (T023, normalization version 1):** `data/labels.csv` là bộ **9.708 ảnh** (4.000 CIFAKE + 5.708 GenImage) giữ split của manifest 10.000 ảnh cũ, loại 292 ảnh thật có cạnh ngắn dưới 256 px thay vì phóng to. Đây là bộ model phục vụ API (e571) đã dùng ([lựa chọn ML](../docs/decisions/ml-selection.md)): khác bản Kiệt chọn (SHA256 `4bf8e490…`) chỉ ở thư mục ảnh đã chuẩn hóa và kiểu xuống dòng, từng dòng còn lại giống hệt. Nhóm giữ bộ này theo constitution mục II; không thay bù ảnh nhỏ (KAN-34 đã bỏ ngày 09/11).

Tạo lại từ repo sạch (manifest 10.000 ảnh cũ nằm ở commit `58a21b5`):

```bash
python -m scripts.download_data cifake
python -m scripts.download_data genimage
git show 58a21b5:data/labels.csv > .cache/labels-10000.csv
python -m scripts.prepare_data --split-from .cache/labels-10000.csv --output-dir <thư mục mới> --labels <labels chưa có group> --workers 2
python -m scripts.add_group_ids --labels <labels chưa có group> --output <labels mới>
python -m scripts.check_data --labels <labels mới>
```

`prepare_data` từ chối ghi vào thư mục đã tồn tại (kể cả `data/processed/` vì có `.gitkeep`), nên luôn dùng đường dẫn mới; `--split-from` khớp theo raw identity, không chia lại. Xem [bản ứng viên giữ split](../docs/ml-preserved-split.md) về cảnh báo lịch sử holdout. `metadata_audit.json` và `baseline_filesize.json` bên dưới vẫn đo trên bộ 10.000 ảnh cũ, chưa đo lại cho bộ này.

Checker hiện yêu cầu manifest có bảy cột: sáu cột của `prepare_data` (`norm_version` đúng version hiện hành) rồi `group_id` do `add_group_ids` gắn; manifest cũ thiếu version sẽ FAIL, không tự nâng version. `prepare_data` ghi riêng ảnh quá nhỏ vào `rejected_small.csv`, ảnh hỏng/decompression bomb vào `rejected_invalid.csv` và ảnh trùng vào `rejected_duplicate.csv`, trong thư mục output. Cả ba danh sách giữ đường dẫn, source, kích thước, lý do và version để QA đối chiếu.

| Đường dẫn | Nội dung |
|---|---|
| `raw/` | Ảnh gốc tải về, không sửa |
| `processed/` | Ảnh đã làm sạch, cùng JPEG, cùng chất lượng và kích thước |
| `features/` | Kết quả CLIP (`.npy`) |
| `labels.csv` | `filepath, label, source, split, raw_path, norm_version, group_id` |
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
  - GenImage: tải 3.000 ảnh thật (ImageNet) + 1.000 ảnh mỗi nguồn Midjourney, GLIDE, SD v1.4; sau khi loại ảnh nhỏ còn 2.708 ảnh thật.
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
| `norm_version` | Phiên bản chuẩn hóa (`models.normalize.NORMALIZATION_VERSION`), hiện là `1` |
| `group_id` | Nhóm ảnh trùng hoặc gần trùng (`scripts.add_group_ids`, #99, D01): ảnh gốc trùng byte (SHA256) hoặc ảnh chuẩn hóa lệch dHash ≤ 4 bit cùng group; `g-` + 16 ký tự hex đầu SHA256 ảnh gốc nhỏ nhất trong group. Mỗi group một split, một nhãn. Bộ chính: 9.708 group (không có ảnh trùng hay gần trùng). Dùng làm `history` cho protocol ADV-08 |

SHA256 bộ chính: `78b8f36b…1148` (có `group_id`); bỏ cột `group_id` thì khớp từng byte bản trước `112aa115…4bdf` ([sổ quyết định](../docs/decisions/realcheck-baseline.md#manifest)). Thêm cột không đổi ảnh, nhãn, split hay `norm_version`, nhưng feature manifest trích từ bản cũ sẽ bị `load_features` từ chối vì khác hash.

Số ảnh theo split (bộ chính, sau `check_data`: 0 lỗi, 0 cảnh báo, 0 ảnh trùng hoặc gần trùng giữa train và val/test):

| Nguồn | Train | Val | Test |
|---|---:|---:|---:|
| `genimage_real` | 1.888 | 421 | 399 |
| `genimage_glide` | 700 | 150 | 150 |
| `genimage_midjourney` | 700 | 150 | 150 |
| `genimage_sd14` | 700 | 150 | 150 |
| `cifake_real` | 850 | 150 | 1.000 |
| `cifake_ai` | 850 | 150 | 1.000 |

Lọc theo `source`: chỉ dùng `genimage_*` cho mô hình chính; `cifake_*` chỉ để chạy thử.

## Thông số chuẩn hóa
| Thông số | Giá trị | Ghi chú |
|---|---|---|
| Kích thước | 256×256 | Resize cạnh ngắn rồi center-crop; CIFAKE giữ 32×32 |
| Định dạng | JPEG chất lượng 95, RGB, bỏ EXIF | Cao hơn các mức 90/70/50 của thí nghiệm nén |
| Chia tập GenImage | 70 / 15 / 15 | Phân tầng theo `source`, seed 42 |
| Chia tập CIFAKE | train gốc → 85% train / 15% val; test gốc → test | |
| Ảnh trùng | Bỏ ảnh trùng pixel sau chuẩn hóa; trùng khác nhãn thì bỏ cả hai | So sánh sau khi cắt về 256×256; ghi vào `rejected_duplicate.csv` và xóa JPEG của ảnh bị bỏ |

### Nén JPEG hai lần
Ảnh thật (ImageNet) vốn là JPEG nên khi lưu lại bị nén 2 lần, còn ảnh AI (PNG) chỉ nén 1 lần; mô hình có thể học dấu vết nén này thay vì dấu vết AI. Vì vậy `prepare_data.py` **crop/resize về 256×256 trước, rồi mới nén JPEG**: đổi kích thước làm lệch lưới khối 8×8 của lần nén cũ, giảm dấu vết nén trước đó.

| Ảnh thật gốc (3.000) | Số ảnh | Lưới nén cũ |
|---|---|---|
| Thu nhỏ (cạnh ngắn > 256) | 2.706 | Bị lệch |
| Cạnh ngắn < 256 | 292 | Bị loại (version 1), ghi vào `rejected_small.csv` |
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
- **292/3.000 ảnh thật có cạnh ngắn dưới 256px** bị loại thay vì phóng to (version 1), nên không còn ảnh thật mờ do phóng to. Đổi lại GenImage hơi lệch lớp (52–53% ảnh AI mỗi split); nhóm quyết định không thay bù (KAN-34 đã bỏ).

## Lưu ý và giả định
- Không commit ảnh và `.npy` (đã gitignore); chỉ commit `labels.csv` và README.
- Dữ liệu chỉ dùng cho học tập; trích dẫn GenImage, CIFAKE trong báo cáo. Tiny-GenImage có giấy phép CC BY-NC-SA 4.0.
- Giấy phép các nguồn của bộ mở rộng (PR #61, kiểm ở [ADV-09](../docs/data-review-adv09.md)); dùng chung thì theo điều kiện chặt nhất là **phi thương mại, chia sẻ cùng giấy phép**, không phát hành lại ảnh:

  | Nguồn | Giấy phép | Ghi chú |
  |---|---|---|
  | OpenFake | CC BY-NC 4.0 | Thẻ dataset trên Hugging Face |
  | Community Forensics-Small | CC BY-NC-SA 4.0 | Bản mirror dùng để lấy COCO, VISION, FFHQ, Landscapes HQ |
  | COCO | Chú thích CC BY 4.0; ảnh theo điều khoản Flickr của từng ảnh | Nhóm COCO không sở hữu bản quyền ảnh; người dùng tự chịu trách nhiệm |
  | FFHQ | Bộ dữ liệu CC BY-NC-SA 4.0 (NVIDIA); từng ảnh theo giấy phép Flickr riêng | Không dùng để phát triển nhận dạng khuôn mặt |
  | VISION | CC BY-SA 4.0 theo README của bộ | Phải trích dẫn bài báo EURASIP 2017 |
  | Landscapes HQ | **Chưa xác nhận** | Ảnh lấy từ Unsplash và Flickr; trang tổng hợp ghi "Other" |
- CIFAKE trên Hugging Face gán `0 = FAKE, 1 = REAL`; script đã đổi về quy ước của nhóm.
- Tránh chụp mặt người lạ.
- Gate dữ liệu là kiểm tra metadata (post `A_eff <= 0.55`), không phải dung lượng file. Gate đạt không chứng minh hết mọi shortcut trong pixel.

## Metadata bàn giao bộ mở rộng (#54)

[run-v2 của realcheck_mixed_v3](metadata/realcheck_mixed_v3/run-v2/README.md) có `labels.csv`, `selection.jsonl`, dHash và dung lượng byte của raw/ảnh chuẩn hóa để Loan audit không cần ảnh. Giữ nguyên mẫu/nhãn/split, bỏ prefix máy cá nhân; kèm checksum và trả lời phạm vi hai manifest lịch sử. Đây là metadata audit, không thay manifest huấn luyện/cache gốc và không tự chứng nhận hết leakage.
