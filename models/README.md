# models/ – CLIP + Logistic Regression

Phụ trách: Kiệt

## Làm gì
CLIP ViT-B/32 (giữ nguyên) biến ảnh thành vector 512 số; Logistic Regression cho điểm 0–1 (càng gần 1 càng giống ảnh AI).

| File | Chức năng |
|---|---|
| `clip_probe.joblib` | Model đã train (không commit nếu nặng) |
| `score(image) -> float` | Hàm FastAPI gọi |

## Cách chạy
Huấn luyện từ `data/features/` và `data/labels.csv`; xuất `clip_probe.joblib` vào thư mục này.

## Input / Output
- Input: ảnh (CLIP tự đưa về 224×224).
- Output: điểm 0–1.

## Lưu ý và giả định
- Ngưỡng 0.3 / 0.7 chọn trên tập validation, không chọn trên tập test.
- Báo cáo Accuracy, Precision, Recall, confusion matrix.
