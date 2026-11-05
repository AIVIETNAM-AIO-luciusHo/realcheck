# KAN-41: đối chiếu chuẩn hóa trên dữ liệu tải lại

Kiệt thực hiện thay phần chạy QA của Lực theo đề nghị nhóm ngày 05/11/2026. Phạm vi: T013/T016/T022, spec 001. Checker của Lực đã có trên main qua PR #18; nhánh này bổ sung kiểm đầu vào và chạy dữ liệu thật. Lực/Loan vẫn cần review kết quả; Kiệt là người tham gia triển khai ML nên lần chạy này không được mô tả là nghiệm thu bởi người kiểm độc lập.

## Trạng thái

**Chưa có baseline T012 của Loan.** Đã kiểm lịch sử tất cả nhánh đã fetch đối với `data/processed_baseline.sha256` và các thư mục dự án/bằng chứng hiện có, chưa thấy file này. Theo chỉ dẫn tiếp tục làm và bổ sung sau, đã tái dựng một bộ tham chiếu bằng code cũ, đặt tên `legacy-reconstructed.sha256`. Đây không phải baseline chụp trên máy Loan trước migration và không thay thế T012.

| Task | Bằng chứng đã có | Phần còn lại |
|---|---|---|
| T013 | Tải lại raw, chạy nguyên script cũ, tái tạo manifest 10.000 dòng khớp main và lưu SHA256 | Đối chiếu với baseline T012 thật và commit/Pillow mà Loan ghi kèm |
| T016 | Chuẩn hóa lại toàn bộ 9.708 ảnh giữ lại từ raw tải mới: 9.708 hash khớp tham chiếu code cũ | Chạy lại với baseline chính thức khi nhận được |
| T022 | 10.000 raw = 9.708 kept + 292 rejected; không thất lạc, không chồng lặp | Lực/Loan review, xác nhận manifest dùng chung; chưa tự phê duyệt manifest |

KAN-44/KAN-51 vẫn chờ manifest và các xác nhận QA/audit/holdout/ngưỡng. Lần chạy này không train model, không tạo embeddings, không tính điểm model trên GenImage test. Việc đọc ảnh để kiểm byte/kiểm kê không tạo số đo chất lượng model.

## Nguồn code và môi trường

- Base main: `c63a521`, đã gồm PR #18/#19/#20.
- Code trước migration: `43caa160921c8927f33b22fe72e9d443c5d8134f`; dùng `git archive`, không viết lại thuật toán cũ trong test. Chạy nguyên `scripts.download_data` và `scripts.prepare_data` trong bản archive riêng.
- Checker và pipeline hiện tại: `56159e29f0a78b2634d77b822dec570632fdfb6a`, working tree sạch khi chạy dữ liệu thật (`dirty=false`).
- Windows, Python 3.12.14, Pillow 13.0.0, NumPy 2.4.6, pandas 3.1.0, pyarrow 26.0.0, huggingface-hub 2.4.0; seed 42 trong script cũ và hiện tại.
- Tải lại qua cache HF riêng, không lấy raw cũ làm đầu vào lần tái lập. Raw tải mới có SHA256 khớp 10.000/10.000 ảnh với raw cục bộ trước đó.
- Revision dataset thực tế và hash các manifest nằm trong [báo cáo JSON](reports/kan41-normalization-qa.json). Script tải cũ không ghim revision; khi tái lập sau này phải kiểm đúng revision/hash, không mặc định `main` của dataset luôn giữ nguyên.

## Kết quả thật

| Source | Raw/code cũ | Giữ lại | Loại nhỏ | Đổi split trong số giữ lại |
|---|---:|---:|---:|---:|
| CIFAKE AI | 2.000 | 2.000 | 0 | 0 |
| CIFAKE real | 2.000 | 2.000 | 0 | 0 |
| GenImage GLIDE | 1.000 | 1.000 | 0 | 0 |
| GenImage Midjourney | 1.000 | 1.000 | 0 | 0 |
| GenImage real | 3.000 | 2.708 | 292 | 1.238 |
| GenImage SD1.4 | 1.000 | 1.000 | 0 | 464 |
| **Tổng** | **10.000** | **9.708** | **292** | **1.702** |

- Manifest do code cũ tái tạo khớp toàn bộ các trường/dòng của `data/labels.csv` trên main, SHA256 `7a83b1c7c5be7f09463e34cc02254db1c4eeb8b4efbacbb2ca1c7783beabe3ee`.
- Checker: `Baseline: compared 9708 of 9708 label row(s)`; `Inventory: 10000 raw, 9708 kept, 292 rejected`; `OK`, exit 0. Không có ảnh thiếu, hash lệch hoặc ảnh hỏng được phát hiện.
- Đối chiếu thêm chính 9.708 file JPEG output trên đĩa với hash file legacy: 9.708 khớp, 0 lệch. Không chỉ so hai kết quả trong bộ nhớ.
- `check_data`: 0 lỗi, 0 cảnh báo; kiểm ảnh, nhãn, split và trùng ảnh đạt.
- `rejected_small.csv`: 292 ảnh, toàn bộ GenImage real; `rejected_invalid.csv`: 0. Pipeline báo loại 0 ảnh trùng, nên không cần bản ghi duplicate cho cohort này. Lỗi pipeline chưa ghi `rejected_duplicate.csv` khi thực sự có dedup vẫn thuộc task dữ liệu, chưa được sửa ở PR này; checker sẽ báo Lost nếu xảy ra.
- So theo raw identity, 9.708 dòng có label/source/split/norm_version khớp candidate QA cũ. Hash toàn file CSV khác vì đường dẫn raw/processed khác; không được dùng sự trùng nội dung này để tự chốt manifest.
- 1.702 thay đổi split so với manifest 10.000 là do loại ảnh nhỏ và chuỗi RNG dùng chung giữa source. Cần nhóm kiểm lịch sử holdout trước khi train/đánh giá phát hành.

## Kiểm thử code

```text
python -m ruff check .                              -> All checks passed
python -m ruff format --check .                     -> 71 files already formatted
python -m pytest tests/test_check_normalization.py -q -> 35 passed
python -m pytest --cov=app --cov-fail-under=70 -q      -> 170 passed; app 98.31%
```

Không failed/skipped/xfail. Đã tái hiện 12 ca fail trước khi sửa; bổ sung tổng cộng 16 regression case cho bản checker mới. Full suite chạy trước commit code, nội dung Python giữ nguyên khi commit và chạy audit. Coverage trên là của `app`, không phải coverage toàn dự án. Đây là kết quả local Windows; chưa có CI Linux của nhánh tại thời điểm ghi biên bản.

Checker nay từ chối labels/baseline trùng, CSV thiếu/dư ô hoặc sai version, raw path vượt thư mục và file rejection được chỉ định nhưng bị thiếu. Các kiểm tra ảnh/hash/kiểm kê của Lực được giữ lại. Test dùng fixture riêng, không phụ thuộc raw thật hoặc model.

## Tái lập trong thư mục QA riêng

Dùng clean checkout tại commit checker ở trên và môi trường đã cài cả `requirements.txt` lẫn `scripts/requirements-data.txt`. Các lệnh PowerShell sau chạy từ gốc repo. Chọn một `$qaRoot` chưa tồn tại, ngoài repo; không dùng thư mục dữ liệu đang phục vụ ML.

```powershell
$repoRoot = (Get-Location).Path
$qaRoot = Join-Path (Split-Path $repoRoot) 'outputs/realcheck-kan41-replay'
$pythonExe = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (Test-Path -LiteralPath $qaRoot) { throw 'Chọn thư mục QA mới' }
New-Item -ItemType Directory -Path $qaRoot
git archive --format=zip --output="$qaRoot/legacy-source.zip" 43caa160921c8927f33b22fe72e9d443c5d8134f
Expand-Archive -LiteralPath "$qaRoot/legacy-source.zip" -DestinationPath "$qaRoot/legacy"
$env:HF_HOME = Join-Path $qaRoot 'hf-cache'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location "$qaRoot/legacy"
& $pythonExe -m scripts.download_data cifake
& $pythonExe -m scripts.download_data genimage
& $pythonExe -m scripts.prepare_data
```

Chụp hash **file output của code cũ** trước khi chạy code mới (lưu đoạn Python sau thành `$qaRoot/capture_reference.py`, rồi chạy từ `$qaRoot/legacy` bằng môi trường trên):

```python
import csv
import hashlib
from pathlib import Path
from PIL import __version__

with Path('data/labels.csv').open(encoding='utf-8-sig', newline='') as stream:
    rows = list(csv.DictReader(stream))
lines = ['# Reconstructed QA reference; NOT Loan T012 baseline',
         '# legacy_commit 43caa160921c8927f33b22fe72e9d443c5d8134f',
         '# Pillow ' + __version__]
for row in sorted(rows, key=lambda item: item['filepath']):
    digest = hashlib.sha256(Path(row['filepath']).read_bytes()).hexdigest()
    lines.append(digest + '  ' + row['filepath'])
with Path('../legacy-reconstructed.sha256').open('x', encoding='utf-8', newline='\n') as stream:
    stream.write('\n'.join(lines) + '\n')
```

Sau đó chạy pipeline mới và checker trong thư mục trống, cùng raw vừa tải:

```powershell
& $pythonExe ../capture_reference.py
New-Item -ItemType Directory -Path "$qaRoot/current"
Set-Location "$qaRoot/current"
$env:PYTHONPATH = $repoRoot
& $pythonExe -m scripts.prepare_data --raw-dir ../legacy/data/raw --workers 2
& $pythonExe -m scripts.check_normalization --raw-dir ../legacy/data/raw --labels data/labels.csv --baseline ../legacy-reconstructed.sha256 --rejected-dir data/processed
& $pythonExe -m scripts.check_data --labels data/labels.csv
Set-Location $repoRoot
```

Kiểm exit code từng lệnh; nếu lệnh lỗi thì dừng và giữ log. So hash baseline tái dựng với `baseline_sha256` trong báo cáo JSON trước khi diễn giải kết quả. Gói bằng chứng cục bộ giữ raw hash manifest, manifest cũ/mới, rejected CSV, logs và script tổng hợp; ảnh/model không đưa vào Git.

## Khi Loan gửi baseline T012

1. Giữ nguyên bản tái dựng và log hiện tại. Lưu baseline của Loan thành file riêng, ghi SHA256 và commit/Pillow trong header.
2. Dựng đúng commit và môi trường mà Loan ghi, đối chiếu từng file trong baseline với output legacy. Báo đủ số OK/FAILED/thiếu, không thay expected hash bằng hash mới nếu lệch.
3. Chạy lại checker trên raw tải độc lập với `--baseline <file-của-Loan>`. Nếu đường dẫn baseline hoặc manifest khác cấu trúc, ghi rõ ánh xạ trước khi đối chiếu.
4. Loan/Lực review kết quả, chốt manifest/split/holdout. Chỉ lúc đó mới cập nhật nghiệm thu T013/T016 và mở các bước phụ thuộc của KAN-44/KAN-51 theo xác nhận riêng.
