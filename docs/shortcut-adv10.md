# ADV-10 — đối chứng JPEG và resample GLIDE (#59)

Trạng thái ban đầu: công cụ/fixture đang chuẩn bị; chưa có số đo ADV-10. Kiệt thực hiện, Lực review độc lập. Xem [issue #59](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/59). Báo cáo validation này không đổi model API hoặc nghiệm thu model-test.

## Thiết kế khóa trước khi xem score

Model reference [#39](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/releases/tag/api-model-reference-e571-20261110): SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494`; normalization v1, CLIP `sentence-transformers/clip-ViT-B-32`, revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`. Binary 0.5, uncertain gồm cả 0.3/0.7. Không train lại model, chỉnh ngưỡng hoặc đọc ảnh test.

Manifest nguồn SHA256 `4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad`. Chỉ GenImage: train 3.988 (1.888 real và 700 mỗi nguồn AI), validation 871 (421 real và 150 mỗi GLIDE/Midjourney/SD1.4). Train chỉ fit probe chẩn đoán; inference e571 chỉ validation. Validation đã dùng chọn C/model, không phải holdout độc lập. Raw/pixel/group được kiểm trước inference; near-duplicate hoặc lịch sử không được cung cấp chưa được chứng nhận.

| Nhánh | Real | GLIDE | Midjourney / SD1.4 |
|---|---|---|---|
| B | gốc → N | gốc → N | gốc → N |
| J | như B | JPEG bổ sung → N | JPEG bổ sung → N |
| R | như B | 512×512 BICUBIC → N | như B |
| JR | như B | 512×512 → JPEG bổ sung → N | như J |

N dùng nguyên `normalize_image`: EXIF transpose, RGB, fit 256×256 BICUBIC, JPEG q95 rồi decode. JPEG bổ sung q95, subsampling=2, progressive=false, optimize=false, không EXIF/ICC. R chỉ chạy nếu toàn bộ GLIDE train/val là 256×256. JR resample trước JPEG. PNG trung gian của R chỉ lưu lossless, dung lượng không dùng so ngang với JPEG để kết luận shortcut.

`prepare` tạo một JPEG post cho mỗi effective arm, alias các nhánh không thay đổi. `run` decode đúng JPEG đó, gọi `encode_images`/`Scorer.predict_features`; không đưa post trở lại scorer. Parity một validation/source với scorer chuẩn phải ≤1e-5 trước main inference. Warmup/parity được đếm riêng. Cùng post hash tái sử dụng prediction; không coi các alias là mẫu độc lập.

## Công cụ và hợp đồng

`scripts.shortcut_controls` có ba subcommand. `prepare --protocol proposed.json --output <new-dir>` kiểm hash model/labels/history, runtime, clean commit, counts; kiểm raw/pixel/group, kích thước, tạo ảnh/metadata và `protocol.json` locked với hash manifest trước scoring. Không deserialize model ở prepare. `run --protocol <prepared>/protocol.json --prepared <prepared> --output <new-dir>` kiểm lại ảnh/lock, bundle thresholds, fit probes và chạy validation. `summarize --run <run-dir> --output <new.json>` chỉ đọc predictions đã lưu, kiểm checksum/IDs/lineage và tính lại metric/CI; không load encoder/model.

Exit 0: hoàn tất, còn chờ review; exit 1: summary partial có prediction lỗi; exit 2: đầu vào/lock/IO không hợp lệ. Không ghi đè thư mục/file đã tồn tại. Lượt lỗi giữ nguyên preflight/log/run-start, không tạo bằng chứng hoàn tất giả. Inference lỗi từng ảnh được lưu CSV status=error, score/verdict trống; log chi tiết local không công bố đường dẫn máy cá nhân.

Mẫu protocol: [shortcut-adv10.protocol.example.json](shortcut-adv10.protocol.example.json). Mẫu `proposed`, có placeholder commit/path/history; thay bằng bằng chứng thật trước prepare. Đường dẫn protocol tương đối với chính file protocol; `raw_path` trong labels tương đối với `dataset_root`. `prepare` sinh lock mới, không sửa file nguồn. Không tự ghi reviewer đã approved.

## Probe và thống kê

- Dung lượng: chỉ `log(size_bytes/1024)`, LR C=1/solver lbfgs/max_iter1000/class_weight balanced; tree depth3/balanced/seed42. Không grid search.
- Metadata: extractor 13 cột hiện có, HistGradientBoostingClassifier seed42. Category khóa bằng train, giá trị lạ thành missing. Numeric hoàn toàn missing ở train giữ cột hằng 0 ở mọi split (không mang thông tin); tránh lỗi binning all-NaN của sklearn1.9.1. Không thêm source/path/label/dung lượng làm feature.
- Raw có probe riêng. Post báo cả fixed (fit B/train, đo mọi arm) và refit (fit train từng arm); không refit e571. Controls metadata dùng nhãn lộ chủ động và nhãn hoán vị nguyên group độc lập trong train/val; chỉ chẩn đoán, không phê duyệt gate D03/D04.
- Model: accuracy toàn bộ (gồm uncertain), balanced accuracy, precision/recall và mẫu số/defined, confusion matrix, AUROC, FPR/FNR, uncertain. Báo từng source và ba cặp real–AI; không accuracy gộp mọi variant.
- Pair theo ID trên giao prediction hợp lệ. Flip là verdict ba trạng thái đổi; degradation = accuracy B − intervention, số dương nghĩa xấu đi. Delta khác = intervention − B. Transition matrix hàng B/cột intervention theo likely_real, uncertain, likely_ai.
- Bootstrap group 2.000 lần, seed42, phân tầng source/label. Group nhiều source giữ nguyên trong stratum composite. B/child dùng chung weights. CI percentile 2.5/97.5; <2 group hoặc metric/replicate undefined: CI null, n_boot_valid và lý do. CI probe điều kiện theo probe đã fit, không bao gồm biến thiên fit. Singleton strata có thể tạo CI hẹp.

## Tái lập

Provision raw, model và HF cache trước; cài `requirements.txt` + `models/requirements-ml.txt` đúng gói bàn giao (Python3.12.14/Pillow13.0.0). Giữ model cùng raw `.joblib.sha256` sidecar. Protocol ghi cả phiên bản numpy/pandas/sklearn/joblib/torch/transformers/sentence-transformers thực dùng.

Từ checkout sạch tại commit được ghi trong protocol:

```powershell
$env:PYTHONUTF8 = '1'
$env:HF_HOME = '<HF-cache-root>'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:OMP_NUM_THREADS = '4'
$env:OPENBLAS_NUM_THREADS = '4'
python -m scripts.shortcut_controls prepare --protocol .cache/adv10/proposed.json --output .cache/adv10/prepared
python -m scripts.shortcut_controls run --protocol .cache/adv10/prepared/protocol.json --prepared .cache/adv10/prepared --output .cache/adv10/run
python -m scripts.shortcut_controls summarize --run .cache/adv10/run --output .cache/adv10/shortcut-adv10.json
```

Giữ đúng analysis commit để tái lập; không sửa protocol sau khi xem score. Nếu chạy lại, tạo output mới. Kiểm SHA model/labels/history/raw/variant trước và sau run. Lệnh summarize có thể chạy lại với output mới mà không inference lại.

```text
python -m ruff check .
python -m ruff format --check .
python -m pytest tests/test_shortcut_controls.py tests/test_evaluate.py tests/test_normalize.py tests/test_score_normalization.py -q
python -m pytest --cov=app --cov-fail-under=70 -q -rs
```

## Bằng chứng và diễn giải

Evidence local: inventory/preflight, samples/variants manifests, locked protocol, run-start/complete, audit predictions/diagnostics, predictions CSV, parity và lỗi. Ảnh/model/HF cache nằm trong `.cache/` được ignore; chỉ code/tests/docs/report đã kiểm nội dung được commit. Gói bàn giao GitHub chứa evidence tái tính; QA cần provision raw/model để tự chạy prepare/inference. Không commit Jira CSV.

Số 84,54% trong issue thuộc test cũ/cohort khác, không gắn vào validation mới. Metadata post hằng/A_eff0.5 là giới hạn phép kiểm. JPEG bổ sung không tái tạo lịch sử nén thật, resample không tái tạo quá trình thu ảnh; thay đổi metric không chứng minh nhân quả. Dung lượng phân biệt tốt không chứng minh CLIP đọc trực tiếp byte length. Không kết luận shortcut đã loại trừ hoặc mô hình nhận ra dấu vết AI tổng quát chỉ từ thí nghiệm này.

JPEG ghost/KAN-46/T027 deferred theo [#53](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/53). Độc lập #51/#52, không thay việc Loan bàn giao cohort/runner. Chưa QA độc lập hoặc duyệt release: `independent_qa_approved=false`, `release_approved=false`; Lực review rồi mới xem xét trạng thái #59.
