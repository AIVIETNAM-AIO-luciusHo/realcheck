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
| `evaluate.py` | Chuẩn bị protocol chờ duyệt, chấm GenImage test bằng probe đã khóa, lưu predictions/report; không train lại |
| `holdout.py` | Chọn test không trùng raw/pixel với các lịch sử train/val được cung cấp; không dự đoán |
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

`train` mặc định chỉ đánh giá validation. `--evaluate-test` chỉ dành cho CIFAKE chạy thử; GenImage phải dùng `models.evaluate` với model đã khóa, không chạy lại train/grid search khi mở test. `--binary-threshold 0.5` là lựa chọn công khai cho thí nghiệm ban đầu, chưa thay thế phê duyệt D08 của nhóm. C được chọn từ `[0.01, 0.1, 1, 10, 100]` bằng accuracy validation, hòa chọn C nhỏ hơn. Train không fit lên val/test.

Kiểm tra metadata hiện có vẫn là gate cứng; xem biên bản chạy trong [bàn giao ML](../docs/ml-handoff.md). QA độc lập của Lực vẫn cần trước nghiệm thu.

## Input / Output

- `extract_features`: CSV đủ `filepath,label,source,split,raw_path,norm_version`, đường dẫn tính từ gốc repo. GenImage processed 256×256, CIFAKE processed 32×32. Loader kiểm model/revision, version, Pillow, row order, hash CSV/ảnh/array và vector float32 L2. `filepath` và `raw_path` phải khác nhau giữa các dòng kể cả alias `a/../b`; không yêu cầu raw có sẵn trên máy chỉ nạp features. Đổi dữ liệu/model thì trích lại và train lại. Kiểm path/hash không thay QA near-duplicate hoặc lineage độc lập.
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

Endpoint `/v1/analyze` và inference service đã có trên main khi đồng bộ cập nhật lần này; phần HTTP, giới hạn upload và executor thuộc Quang. Kiểm parity local của ML không thay kiểm thử tích hợp HTTP.

## Kiểm chứng

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest --cov=app --cov-fail-under=70
```

Test CLIP dùng mock để CI không tải torch/trọng số. Kết quả với model/dữ liệu thật và giới hạn còn lại ghi riêng trong [bàn giao ML](../docs/ml-handoff.md).

Hai báo cáo train cũ có timestamp trùng và thiếu provenance; xem [giải trình, lệnh và commit tái lập](../docs/ml-reproducibility.md). CLI hiện ghi thông tin run tự động; `created_at` không được dùng làm định danh duy nhất. GenImage validation đã dùng chọn C; shortcut dung lượng file/độ mịn/dấu vết JPEG chưa loại trừ, T027 chưa có.

## KAN-44: chạy lại sau khi manifest được chốt

Chọn đường dẫn manifest do Loan/Lực xác nhận, rồi trích feature và train vào thư mục phiên bản mới. Ví dụ dưới chỉ là mẫu sau khi nhóm đã tạo `data/labels-release.csv`; không tự đổi tên/gán version cho manifest cũ để chạy:

Nếu chọn phương án giữ ảnh cũ, ghi riêng ảnh không dùng và giữ split cũ, tạo **bản ứng viên** bằng `scripts.prepare_data --split-from data/labels.csv` vào thư mục mới trước; lệnh đầy đủ và bằng chứng ở [ml-preserved-split.md](../docs/ml-preserved-split.md). Manifest 9.708 dòng này khác manifest 9.708 dòng từng train: giữ 0 thay đổi split so với các ảnh hợp lệ trong bản 10.000, nhưng đổi 1.702 split so với bản QA cũ. Không dùng lại features/model/report cũ cho manifest mới, không thay bản dùng tái lập báo cáo hiện tại. Đây chưa phải manifest phát hành đã được phê duyệt.

```bash
python -m models.extract_features --labels data/labels-release.csv --output-dir .cache/ml-release/features
python -m models.train --labels data/labels-release.csv --features .cache/ml-release/features --dataset genimage --output .cache/ml-release/clip_probe.joblib --report .cache/ml-release/validation.json --binary-threshold 0.5
```

Lệnh train/extract vẫn có thể thay file output đang tồn tại: dùng thư mục mới cho mỗi candidate, không trỏ vào artifact đã khóa. Hash labels/features trong model phải khớp chính xác với dữ liệu evaluate; nếu đổi split/ảnh/nhãn thì không tái sử dụng model cũ. Đây chưa phải lệnh đã chạy trên manifest phát hành.

## KAN-51: protocol và model-test

Kiệt đã chọn candidate giữ split cũ và ngưỡng 0.3/0.5/0.7; xem [quyết định triển khai và trạng thái review](../docs/decisions/ml-selection.md). Dùng `models.holdout` trước khi mở test để lọc lịch sử; trên cohort hiện tại còn 384/849 ảnh test đủ điều kiện theo lịch sử được cung cấp. Cần báo rõ subset, N từng source và giới hạn, không gọi đây là test của toàn bộ 849 ảnh.

Chuẩn bị protocol chỉ kiểm đầu vào/hashes, không gọi `predict_proba`, không mở điểm test:

```bash
python -m models.evaluate --labels data/labels-release.csv --features .cache/ml-release/features --model .cache/ml-release/clip_probe.joblib --history-labels .cache/ml-run/labels.csv --prepare-lock .cache/ml-release/protocol.json
```

File mới có `status: proposed`, `approved_by: []`, bốn tham chiếu `evidence` trống. Loan/Lực/Kiệt phải chốt manifest QA, metadata audit, lịch sử holdout và ngưỡng trước khi ghi reviewer/tham chiếu thật rồi chuyển `status` sang `approved`. Lệnh này chỉ ghi nhận xác nhận của nhóm, không tự kiểm thay audit hoặc chứng nhận người duyệt. Không điền thông tin giả để bỏ chặn.

Khi đã duyệt, chạy đúng model/manifest đó vào thư mục output chưa tồn tại:

```bash
python -m models.evaluate --labels data/labels-release.csv --features .cache/ml-release/features --model .cache/ml-release/clip_probe.joblib --history-labels .cache/ml-run/labels.csv --lock .cache/ml-release/protocol.json --output-dir .cache/ml-release/test-result
```

Đầu ra: `evaluation.json` có các trường báo cáo UI, `predictions.csv` có row_index/source/label/score/hash ảnh để dựng lại bảng mà không chấm test lại, và bản sao `protocol.json`. Accuracy nhị phân dùng toàn bộ N; vùng Chưa chắc lấy ngưỡng đã khóa, decided-only/coverage ghi riêng; AUROC source một lớp là null. Nếu không có ca đã kết luận thì decided_accuracy=null; adapter UI của Loan cần xử lý trường hợp này (validator UI hiện chưa nhận null). Accuracy dưới 0,90 vẫn lưu kết quả thật và CLI exit 1; chưa có đủ gate khác thì không coi quality pass là MVP release pass.

`protocol.json.used.json` được tạo độc quyền **trước** inference, kể cả lần lỗi; lần sau cùng protocol bị từ chối. Đây là chống chạy lại vô ý tại cùng đường dẫn, không phải registry toàn hệ thống. Không xóa marker hoặc copy protocol để lựa lần test đẹp hơn. Nếu lỗi kỹ thuật cần replay, giữ bằng chứng lần lỗi và xin reviewer thống nhất cách ghi nhận replay trước; không tune lại model/ngưỡng bằng test.

Ban đầu người dùng xác nhận chưa chốt manifest và chưa mở GenImage test. Cập nhật 05/11: Kiệt đã chọn candidate giữ split từ bản 10.000, cùng bảng ngưỡng đã ghi; QA/audit/holdout độc lập chưa được xác nhận đầy đủ. KAN-44 còn chờ xác nhận dữ liệu để tạo artifact mới, KAN-51 còn chờ protocol được duyệt và số đo thật. Xem [hồ sơ bốn task ML](../docs/ml-normalization-release.md).
