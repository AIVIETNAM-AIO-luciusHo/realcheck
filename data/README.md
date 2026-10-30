# data/ – Dữ liệu

Phụ trách: Loan

## Làm gì
Tải, chuẩn hóa và chia tập dữ liệu. Nhãn lấy theo thư mục (real = 0, ai = 1).

| Đường dẫn | Nội dung |
|---|---|
| `raw/` | Ảnh gốc tải về, không sửa |
| `processed/` | Ảnh đã làm sạch, cùng JPEG, cùng chất lượng và kích thước |
| `features/` | Kết quả CLIP (`.npy`) |
| `labels.csv` | `filepath, label, source, split, raw_path` |
| `baseline_filesize.json` | Kết quả baseline dung lượng file (D4) |

Nguồn: CIFAKE (Kaggle), GenImage (NeurIPS 2023), ảnh nhóm tự chụp/tạo, ảnh qua Zalo.

## Cách chạy
Từ thư mục gốc repo:
```bash
pip install -r scripts/requirements-data.txt
python scripts/download_data.py cifake     # D1: ~16MB
python scripts/download_data.py genimage   # D2: tải ~4GB từng phần, giữ lại ~1.5GB
python scripts/prepare_data.py             # D3: processed/ + labels.csv
python scripts/check_data.py               # tự kiểm tra; lỗi thì thoát mã 1
python scripts/baseline_filesize.py        # D4: baseline_filesize.json
```
Chạy lại cho cùng kết quả (seed 42). `download_data.py genimage` chạy tiếp được nếu bị ngắt.

## Input / Output
- Input: dataset công khai trên Hugging Face và ảnh tự thu thập.
  - CIFAKE: [`dragonintelligence/CIFAKE-image-dataset`](https://huggingface.co/datasets/dragonintelligence/CIFAKE-image-dataset), lấy 1.000 ảnh mỗi lớp ở mỗi split train/test.
  - GenImage: 3.000 ảnh thật (ImageNet) + 1.000 ảnh mỗi nguồn Midjourney, GLIDE, SD v1.4.
    - Ảnh thật, Midjourney, GLIDE: [`TheKernel01/Tiny-GenImage`](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage) (bản thu nhỏ của GenImage).
    - SD v1.4: Tiny-GenImage không có, lấy từ split test của [`nebula/GenImage-arrow`](https://huggingface.co/datasets/nebula/GenImage-arrow) (shard `data-00004`, toàn ảnh AI).
- Output: `processed/`, `labels.csv`, `baseline_filesize.json`.

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

## Lưu ý và giả định
- Không commit ảnh và `.npy` (đã gitignore); chỉ commit `labels.csv` và README.
- Dữ liệu chỉ dùng cho học tập; trích dẫn GenImage, CIFAKE trong báo cáo. Tiny-GenImage có giấy phép CC BY-NC-SA 4.0.
- CIFAKE trên Hugging Face gán `0 = FAKE, 1 = REAL`; script đã đổi về quy ước của nhóm.
- Tránh chụp mặt người lạ.
- Baseline chỉ dùng kích thước file phải gần 50%; cao hơn hẳn thì làm lại dữ liệu. Script cảnh báo khi test accuracy trên ảnh đã chuẩn hóa vượt 60% (ngưỡng tạm, nhóm chưa chốt).
