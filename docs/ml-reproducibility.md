# Truy vết và tái lập thí nghiệm ML

Phạm vi: [spec 001](../specs/001-unified-image-normalization/spec.md), [tasks](../specs/001-unified-image-normalization/tasks.md), KAN-16 đến KAN-20 và review [PR #15](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/pull/15).

## Hai timestamp cũ trùng nhau

Ở commit đã push ban đầu `0c446c097880e0c348c6759b7ed551271a049a16`, `ml-cifake.json` và `ml-genimage.json` cùng có `created_at=2026-11-04T11:52:01.449152+00:00`. Không coi giá trị này là bằng chứng hai lần train độc lập có thời điểm hoàn thành khác nhau.

Log thực thi cũ ghi hai lệnh riêng dưới đây, được khởi chạy song song bằng `Promise.allSettled`, mỗi lệnh là một process Python. Cả hai exit 0; output CIFAKE là C=100, validation accuracy=0,9133333333, test accuracy=0,93; output GenImage là C=10, validation accuracy=0,9567757009 và test=null.

```powershell
.venv/Scripts/python.exe -m models.train --labels .cache/ml-run/labels.csv --features data/features --dataset cifake --output models/cifake_probe.joblib --report docs/reports/ml-cifake.json --binary-threshold 0.5 --evaluate-test
.venv/Scripts/python.exe -m models.train --labels .cache/ml-run/labels.csv --features data/features --dataset genimage --output models/clip_probe.joblib --report docs/reports/ml-genimage.json --binary-threshold 0.5
```

`models.train` tự tính metrics, gọi `datetime.now(UTC).isoformat()` và ghi JSON. Log đã kiểm tra không có bước gán tay chung `created_at` hoặc sửa tay metrics của hai báo cáo. Tuy vậy, **chưa xác định được nguyên nhân đồng hồ cho timestamp trùng đến micro-giây**; chạy song song tự nó không giải thích được điều này. Báo cáo cũ không ghi command, commit hay runtime. Lúc thí nghiệm, phần ML còn là thay đổi chưa commit trên nền `24bd0a6`; `0c446c0` là commit bàn giao sau đó, không phải một commit đã được ghi vào báo cáo lúc train.

Vì thiếu provenance, không dùng timestamp cũ để chứng nhận nguồn gốc. Hai báo cáo được chạy lại tuần tự từ một commit code cố định; bản JSON mới ghi `run.id` (UUID), `run.command`, `run.git_commit`, `run.git_dirty`, `run.started_at`, `run.finished_at`, thời lượng, Python và OS. Mỗi báo cáo vẫn giữ hash labels, features và model. Không chỉnh timestamp chỉ để làm hai giá trị khác nhau. `created_at` là thời gian do đồng hồ máy cung cấp; UUID và hash được dùng để đối chiếu run/artifact.

## Lệnh tái lập từ commit cố định

Lần chạy lại đã hoàn tất từ commit **`58e45e9db8ce8ed5057af7e428e67eff02514e00`**, cả ba báo cáo ghi `git_dirty=false`. Hai lần train mới khớp hoàn toàn model hash, lựa chọn C và metrics của báo cáo cũ; không sửa số đo thủ công.

| Run | UUID | Thời gian tạo báo cáo UTC |
|---|---|---|
| CIFAKE | `3b1d9e71-28d5-48cd-8bec-68ad56ff7519` | `2026-11-04T21:48:33.187527+00:00` |
| GenImage | `e78a1407-39e0-468b-b417-91b96263934b` | `2026-11-04T21:48:36.821981+00:00` |
| Verify model thật | `f440860e-4d6a-441a-b0f9-afc009aca01c` | `2026-11-04T21:49:35.387519+00:00` |

Các thời điểm trên tương ứng rạng sáng **05/11/2026 UTC+7**. `check_data --labels .cache/ml-run/labels.csv` sau sửa cũng đã chạy trên 9.708 ảnh thật: 0 lỗi, 0 cảnh báo. Verify mới khớp tensor từng phần tử; sai khác score tối đa `3,3527612686157227e-7`, dưới `1e-5`.

Commit nguồn chính xác nằm trong `run.git_commit` của [CIFAKE](reports/ml-cifake.json), [GenImage](reports/ml-genimage.json) và [integration](reports/ml-integration.json). Checkout commit đó trong bản sao riêng, cài dependencies đã pin, rồi đặt dữ liệu/cache theo đường dẫn trong manifest. Lần chạy báo cáo phải bắt đầu khi working tree sạch; output report tạm ở ngoài repo để việc ghi báo cáo thứ nhất không làm lần thứ hai dirty.

```powershell
python -m pip install -r requirements.txt -r scripts/requirements-data.txt -r models/requirements-ml.txt
$env:HF_HOME = Join-Path (Get-Location) '.cache/huggingface'
# Chỉ đặt OFFLINE khi đã có cache đúng revision CLIP.
$env:HF_HUB_OFFLINE = '1'
python -m models.train --labels .cache/ml-run/labels.csv --features data/features --dataset cifake --output models/cifake_probe.joblib --report ../outputs/realcheck-pr15-review/reports/ml-cifake.json --binary-threshold 0.5 --evaluate-test
python -m models.train --labels .cache/ml-run/labels.csv --features data/features --dataset genimage --output models/clip_probe.joblib --report ../outputs/realcheck-pr15-review/reports/ml-genimage.json --binary-threshold 0.5
python -m scripts.verify_ml --labels .cache/ml-run/labels.csv --features data/features --model models/clip_probe.joblib --report ../outputs/realcheck-pr15-review/reports/ml-integration.json
```

Chạy tuần tự ba lệnh; kiểm exit code từng lệnh. CLI ghi provenance tự động, không nhập tay commit. Sau khi thành công mới chép nguyên nội dung ba JSON vào `docs/reports/` để review. Nếu cần dựng lại features, chạy `python -m models.extract_features --labels .cache/ml-run/labels.csv --output-dir data/features --batch-size 32` sau khi có đủ ảnh processed đúng manifest. Thay dữ liệu/normalization thì cần lần thí nghiệm mới, không dùng cache cũ.

CIFAKE test được chạy lại để đối chiếu số đo đã công bố, không dùng để chỉnh C/ngưỡng. GenImage test vẫn không được đánh giá. Bộ đã chọn dùng 9.708 ảnh gồm 4.000 CIFAKE và 5.708 GenImage. Các số đo validation chưa loại trừ shortcut dung lượng file/độ mịn/dấu vết JPEG; T027 chưa có.

## Môi trường và gói bàn giao cho Lực

Lần verify ban đầu chạy trên Windows, Python 3.12.14, CLIP trên CPU với 4 luồng. Dependency thực của lần train nằm trong các báo cáo: NumPy 2.4.6, Pillow 13.0.0, scikit-learn 1.9.1, joblib 1.6.0, torch 2.15.0, transformers 5.22.1, sentence-transformers 6.2.0. Lần verify mới ghi thêm Python/OS/executable/command/commit vào `run`; CI Linux/Python 3.11 chỉ kiểm regression với mock CLIP.

Gói local gửi kèm bàn giao gồm `models/clip_probe.joblib`, `.sha256`, `.cache/ml-run/labels.csv`, `data/features/features.npy`, `manifest.json`, toàn bộ JPEG processed được hash trong manifest và các raw validation được verify sử dụng. CLIP weights tải/cache riêng đúng `sentence-transformers/clip-ViT-B-32` revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`. Gói có danh sách SHA256 để kiểm sau khi giải nén; không đưa ảnh, features hoặc joblib vào Git.

Tên gói: `realcheck-qa-58e45e9.zip`, 191.794.046 bytes, 9.723 file; SHA256 `177e4f669abe1c8034da1954c75043891a930f25321c2e254f24ff31c4bcfdaf`. Gói được bàn giao ngoài Git cùng `QA_HANDOFF.md` và `SHA256SUMS.txt` bên trong, không phải attachment đã tự gửi tới tài khoản của Lực. CRC của toàn bộ ZIP đã được kiểm tra.

Chỉ ba file joblib/checksum/labels không đủ cho `verify_ml.py`: loader còn đối chiếu toàn bộ processed/features, rồi so raw validation với processed. Gói này dành cho tái chạy ML, không phải toàn bộ raw data hoặc baseline của Loan để nghiệm thu T012/T013. Giải nén vào bản sao repo riêng, chạy lệnh verify ở trên; Lực ghi kết quả độc lập. Kiệt không tự đánh dấu T030 hoàn tất.

## Phạm vi phối hợp

Các sửa `prepare_data.py`/`check_data.py` là adapter cần cho bộ ML chạy riêng dùng normalization version 1, có chồng lấn phần Loan. Test do Kiệt viết là regression cho phần code đã thay đổi, có chồng lấn bộ test của Lực. Cần Loan/Lực review trước merge; giữ nguyên owner và trạng thái chưa nghiệm thu baseline/QA trong tasks.md. Chi tiết ở [bàn giao ML](ml-handoff.md).

## Kiểm tra code sau review

Ngày 05/11/2026, Windows/Python 3.12.14: `python -m pytest --cov=app --cov-fail-under=70` chạy **100 test đạt**, coverage `app/` **98,31%**. Ruff check/format đạt. Test script dùng ảnh tổng hợp và worker thật; test verify dùng encoder mock để kiểm hành vi của script. Đây là regression của tác giả PR, không phải QA độc lập T030. Kết quả model thật và commit nguồn được ghi riêng trong JSON `run`.

Đã kiểm thử đột biến riêng trong bộ nhớ: ép `Scorer.ai_column=0` sau constructor khiến case `classes_=[0,1]` thất bại (trả 0,8 thay vì 0,2); case `[1,0]` vẫn qua. Đột biến không được ghi vào source. Test hiện phát hiện đúng lỗi reviewer nêu.
