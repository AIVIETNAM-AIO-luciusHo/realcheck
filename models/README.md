# models/ – CLIP + Logistic Regression

Phụ trách: Kiệt. Review chuẩn hóa: Loan; review bàn giao: Quang/Lực.

## Làm gì

Model nền đúng của nhóm là [`sentence-transformers/clip-ViT-B-32`](https://huggingface.co/sentence-transformers/clip-ViT-B-32), nạp bằng `SentenceTransformer`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`. CLIP đóng băng, không train lại. Ảnh → vector 512 chiều chuẩn hóa L2 → Logistic Regression → điểm lớp AI (`label=1`).

| File | Chức năng |
|---|---|
| `normalize.py` | EXIF orientation → RGB → `ImageOps.fit` BICUBIC 256×256 → JPEG 95 một lần → giải mã; version `1` |
| `clip_input.py` | Model/revision cố định; một hàm encode dùng chung train/serve, CLIP tự preprocessing 224×224 |
| `extract_features.py` | Đọc ảnh processed, không nén lại; lưu `features.npy` và manifest chống cache cũ |
| `train.py` | Fit trên train, chọn C trên validation, báo số đo và xuất bundle |
| `score.py` | Nạp/warmup model lúc startup; `score(PIL.Image) -> float` |
| `run_info.py` | Ghi UUID, lệnh CLI, commit, trạng thái dirty, Python và OS vào báo cáo train/verify |
| `clip_probe.joblib` + `.sha256` | Bundle GenImage và checksum, sinh cục bộ, không commit |
| `cifake_probe.joblib` + `.sha256` | Model chạy thử CIFAKE, không được dùng làm scorer Backend |

## Cách chạy

Từ gốc repo, dùng môi trường riêng. CI dùng Python 3.11; lần chạy local dùng Python 3.12.14. Chưa coi kiểm thử Windows là kiểm thử Docker/Linux.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt -r scripts/requirements-data.txt -r models/requirements-ml.txt
```

Cache local nằm trong `.cache/huggingface`. Đặt biến trước khi chạy để dùng lại trọng số:

```powershell
$env:HF_HOME = Join-Path (Get-Location) '.cache/huggingface'
# Chỉ bật sau khi đã tải model thành công:
$env:HF_HUB_OFFLINE = '1'
```

Linux tương ứng: `export HF_HOME="$PWD/.cache/huggingface"`; `export HF_HUB_OFFLINE=1` khi đã tải xong. Lần đầu cần mạng, không đặt `HF_HUB_OFFLINE`.

```bash
python -m scripts.download_data cifake
python -m scripts.download_data genimage
python -m scripts.prepare_data --output-dir .cache/ml-run/processed-v1 --labels .cache/ml-run/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-run/labels.csv
python -m models.extract_features --labels .cache/ml-run/labels.csv --output-dir data/features --batch-size 32
python -m models.train --labels .cache/ml-run/labels.csv --features data/features --dataset cifake --output models/cifake_probe.joblib --report docs/reports/ml-cifake.json --binary-threshold 0.5
python -m models.train --labels .cache/ml-run/labels.csv --features data/features --dataset genimage --output models/clip_probe.joblib --report docs/reports/ml-genimage.json --binary-threshold 0.5
python -m scripts.verify_ml --labels .cache/ml-run/labels.csv
```

Chuẩn hóa từ chối ghi đè manifest/ảnh đã có. Để chạy lại bước đó, chọn thư mục output và tên CSV mới; các bước sau truyền cùng CSV. `data/labels.csv` đang track là manifest cũ, chưa có `norm_version`, không tự gán version mới cho dữ liệu cũ. Các lệnh trên tạo bộ chạy riêng, giữ nguyên manifest của Loan. Nếu cần chuyển dữ liệu chính, Loan chụp baseline trước theo spec 001.

`train` mặc định chỉ đánh giá validation. Chỉ thêm `--evaluate-test` sau khi khóa protocol/model; không chọn lại C/ngưỡng theo kết quả test. `--binary-threshold 0.5` là lựa chọn công khai cho thí nghiệm ban đầu, chưa thay thế phê duyệt D08 của nhóm. C được chọn từ `[0.01, 0.1, 1, 10, 100]` bằng accuracy validation, hòa chọn C nhỏ hơn. Train không fit lên val/test.

Kiểm tra metadata hiện có vẫn là gate cứng; xem biên bản chạy trong [bàn giao ML](../docs/ml-handoff.md). QA độc lập của Lực vẫn cần trước nghiệm thu.

## Input / Output

- `extract_features`: CSV đủ `filepath,label,source,split,raw_path,norm_version`, đường dẫn tính từ gốc repo. GenImage processed 256×256, CIFAKE processed 32×32. Loader kiểm model/revision, version, Pillow, row order, hash CSV/ảnh/array. Đổi dữ liệu/model thì trích lại và train lại.
- `score`: **ảnh gốc đã giải mã**, còn EXIF, chưa resize/nén; cạnh ngắn ít nhất 256 px. `ImageTooSmall` giữ `width`, `height`; không nuốt lỗi hoặc trả điểm giả. CIFAKE chỉ được miễn ngưỡng ở bước chuẩn bị dữ liệu.
- Kết quả là `float` hữu hạn trong `[0,1]`; cột xác suất AI lấy theo `probe.classes_`. Score chưa phải xác suất đã hiệu chuẩn.
- Báo cáo gồm Accuracy, Precision, Recall, AUROC, confusion matrix `[real,ai]`, FPR, số/tỷ lệ Chưa chắc và kết quả theo source. Accuracy nhị phân dùng toàn bộ mẫu; AUROC của source chỉ có một lớp và accuracy khi không có ca đã kết luận được ghi `null`.

## Bàn giao Backend

Nạp và warmup **một lần mỗi worker trước ready**, không gọi loader trong route:

```python
from models.score import load_model, score

load_model()  # Kiểm checksum/metadata và warmup; lỗi thì không ready.
# API giải mã một lần, đọc EXIF, kiểm byte/pixel/format theo policy rồi gọi:
value = score(original_pil_image)
```

Hoặc `scorer = load_scorer(path)` rồi tiêm vào `create_app(scorer=scorer)`. Không đưa ảnh processed vào `score` vì sẽ nén lần thứ hai. API bắt `ImageTooSmall`, giữ ngưỡng 0.3/0.7 theo settings (hai biên là Chưa chắc). Loader chỉ nhận artifact GenImage đúng metadata. Joblib chỉ lấy từ nguồn nhóm tin cậy, không nhận upload làm artifact.

Kiểm tra trực tiếp: `python -m models.score data/raw/genimage/sd14/<ten-anh-goc>.png`.

Endpoint `/v1/analyze` chưa có trên main lúc đồng bộ; phần HTTP, giới hạn upload và executor thuộc Quang. Scorer sẵn để tích hợp, không đồng nghĩa endpoint đã hoàn thành.

## Kiểm chứng

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=app --cov-fail-under=70
```

Test CLIP dùng mock để CI không tải torch/trọng số. Kết quả với model/dữ liệu thật và giới hạn còn lại ghi riêng trong [bàn giao ML](../docs/ml-handoff.md).

Hai báo cáo train cũ có timestamp trùng và thiếu provenance; xem [giải trình, lệnh và commit tái lập](../docs/ml-reproducibility.md). CLI hiện ghi thông tin run tự động; `created_at` không được dùng làm định danh duy nhất. GenImage validation đã dùng chọn C; shortcut dung lượng file/độ mịn/dấu vết JPEG chưa loại trừ, T027 chưa có.
