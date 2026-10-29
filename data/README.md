# data/ – Dữ liệu

Phụ trách: Loan

## Làm gì
Tải, chuẩn hóa và chia tập dữ liệu. Nhãn lấy theo thư mục (real = 0, ai = 1).

| Đường dẫn | Nội dung |
|---|---|
| `raw/` | Ảnh gốc tải về, không sửa |
| `processed/` | Ảnh đã làm sạch, cùng JPEG, cùng chất lượng và kích thước |
| `features/` | Kết quả CLIP (`.npy`) |
| `labels.csv` | `filepath, label, source, split` |

Nguồn: CIFAKE (Kaggle), GenImage (NeurIPS 2023), ảnh nhóm tự chụp/tạo, ảnh qua Zalo.

## Cách chạy
Dùng script trong `scripts/` để tải và chuẩn hóa (chạy lại được).

## Input / Output
- Input: dataset công khai và ảnh tự thu thập.
- Output: `processed/`, `features/`, `labels.csv`.

## Lưu ý và giả định
- Không commit ảnh và `.npy` (đã gitignore); chỉ commit `labels.csv` và README.
- Dữ liệu chỉ dùng cho học tập; trích dẫn GenImage, CIFAKE trong báo cáo.
- Tránh chụp mặt người lạ.
- Baseline chỉ dùng kích thước file phải gần 50%; cao hơn hẳn thì làm lại dữ liệu.
