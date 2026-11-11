# ADV-10 — đối chứng JPEG và resample GLIDE (#59)

Trạng thái: đã chạy đối chứng validation, chờ Lực review độc lập; số đo/evidence ở cuối tài liệu. Kiệt thực hiện, Lực review độc lập. Xem [issue #59](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/59). Báo cáo validation này không đổi model API hoặc nghiệm thu model-test.

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

## Kết quả thật — 11/11/2026

Đã chạy, chờ Lực review độc lập. Code/run/analysis commit `6d1dfb3c08677e2a8e1435bed9e7d6acce546b31`, `dirty=false`. [JSON đầy đủ](reports/shortcut-adv10.json), [evidence ZIP và checksum](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/releases/tag/adv10-shortcut-e571-20261111). Tất cả bảng là validation đã tiếp xúc, đơn vị phần trăm với CI95%; degradation dùng điểm phần trăm.

Preflight: 4.859 ảnh/group, 0 lỗi; train3.988, val871. GLIDE850/850 PNG256×256; real2.309/2.309 JPEG cần resize/crop (2.282 không vuông); Midjourney850 PNG1024×1024; SD1.4 850 PNG512×512. Không có group giao train/val theo exact raw/pixel và lineage được cấp. CSV lịch sử có390/871 validation hiện tại từng là train cũ,399 từng val cũ,82 từng test cũ. Đây là đối chiếu đường dẫn, không chứng nhận near-duplicate/lịch sử chưa cung cấp.

Inference: 3.484 dòng ảnh/nhánh,1.621 post hash riêng được chấm,0 lỗi; warmup1 và parity4 ngoài số này. Parity bốn source sai khác0. Thời gian inference156,33s CPU, không gồm prepare/audit/hash. Model và input hashes khớp sau run. Không chấm train hoặc test bằng CLIP.

### Baseline dung lượng

Mỗi cặp N=571 (421 real +150 AI), group571; train2.588. Raw/post có probe riêng. Fixed post fit B/train; refit fit train từng arm. Không chọn probe theo validation.

| Cặp real–AI | Raw LR BA [CI95] | Raw tree BA [CI95] |
|---|---|---|
| genimage_glide | 69.90 [65.59; 74.14] | 77.53 [73.78; 81.39] |
| genimage_midjourney | 98.19 [96.74; 99.43] | 97.86 [96.26; 99.22] |
| genimage_sd14 | 98.26 [96.98; 99.29] | 97.95 [96.38; 99.19] |

| Cặp | Arm | Post LR fixed [CI95] | Post LR refit [CI95] | Post tree fixed [CI95] | Post tree refit [CI95] |
|---|---|---|---|---|---|
| genimage_glide | B | 81.43 [77.67; 85.09] | 81.43 [77.67; 85.09] | 81.78 [78.00; 85.47] | 81.78 [78.00; 85.47] |
| genimage_glide | J | 81.43 [77.67; 85.09] | 81.54 [77.74; 85.16] | 81.78 [78.00; 85.47] | 81.90 [78.17; 85.55] |
| genimage_glide | R | 81.76 [78.00; 85.30] | 82.71 [79.00; 86.21] | 82.12 [78.36; 85.61] | 82.61 [78.92; 86.07] |
| genimage_glide | JR | 81.76 [78.00; 85.30] | 82.71 [79.00; 86.21] | 82.12 [78.36; 85.61] | 82.95 [79.28; 86.35] |
| genimage_midjourney | B | 67.27 [62.54; 71.89] | 67.27 [62.54; 71.89] | 66.87 [63.04; 70.65] | 66.87 [63.04; 70.65] |
| genimage_midjourney | J | 67.61 [62.87; 72.22] | 67.61 [62.87; 72.22] | 66.87 [63.04; 70.65] | 66.99 [63.14; 70.77] |
| genimage_midjourney | R | 67.27 [62.54; 71.89] | 67.27 [62.54; 71.89] | 66.87 [63.04; 70.65] | 66.87 [63.04; 70.65] |
| genimage_midjourney | JR | 67.61 [62.87; 72.22] | 67.61 [62.87; 72.22] | 66.87 [63.04; 70.65] | 66.99 [63.14; 70.77] |
| genimage_sd14 | B | 54.06 [49.13; 58.55] | 54.06 [49.13; 58.55] | 53.35 [48.66; 57.82] | 53.35 [48.66; 57.82] |
| genimage_sd14 | J | 54.06 [49.13; 58.55] | 54.17 [49.27; 58.70] | 53.68 [48.82; 58.15] | 53.80 [48.94; 58.25] |
| genimage_sd14 | R | 54.06 [49.13; 58.55] | 54.06 [49.13; 58.55] | 53.35 [48.66; 57.82] | 53.35 [48.66; 57.82] |
| genimage_sd14 | JR | 54.06 [49.13; 58.55] | 54.17 [49.27; 58.70] | 53.68 [48.82; 58.15] | 53.80 [48.94; 58.25] |

### Model khóa và tác động trên cùng cặp

| Cặp | Arm | N | Accuracy [CI95] | Flip verdict [CI95] | Degradation B−arm [CI95], pp |
|---|---|---|---|---|---|
| genimage_glide | B | 571 | 97.72 [96.50; 98.77] | 0.00 [0.00; 0.00] | -0.00 [-0.00; 0.00] |
| genimage_glide | J | 571 | 97.72 [96.50; 98.77] | 0.53 [0.00; 1.23] | -0.00 [-0.00; 0.00] |
| genimage_glide | R | 571 | 98.07 [96.85; 99.12] | 0.53 [0.00; 1.23] | -0.35 [-0.88; 0.00] |
| genimage_glide | JR | 571 | 97.90 [96.67; 98.95] | 0.53 [0.00; 1.23] | -0.18 [-0.53; 0.00] |
| genimage_midjourney | B | 571 | 97.20 [95.80; 98.60] | 0.00 [0.00; 0.00] | -0.00 [-0.00; 0.00] |
| genimage_midjourney | J | 571 | 96.85 [95.45; 98.25] | 0.35 [0.00; 0.88] | 0.35 [-0.35; 1.05] |
| genimage_midjourney | R | 571 | 97.20 [95.80; 98.60] | 0.00 [0.00; 0.00] | -0.00 [-0.00; 0.00] |
| genimage_midjourney | JR | 571 | 96.85 [95.45; 98.25] | 0.35 [0.00; 0.88] | 0.35 [-0.35; 1.05] |
| genimage_sd14 | B | 571 | 97.72 [96.50; 98.77] | 0.00 [0.00; 0.00] | -0.00 [-0.00; 0.00] |
| genimage_sd14 | J | 571 | 97.90 [96.67; 98.95] | 0.18 [0.00; 0.53] | -0.18 [-0.53; 0.00] |
| genimage_sd14 | R | 571 | 97.72 [96.50; 98.77] | 0.00 [0.00; 0.00] | -0.00 [-0.00; 0.00] |
| genimage_sd14 | JR | 571 | 97.90 [96.67; 98.95] | 0.18 [0.00; 0.53] | -0.18 [-0.53; 0.00] |

Real không bị can thiệp, FPR9/421=2,14% giống nhau theo thiết kế; không coi đây là chứng minh robustness của real. Pair flip có mẫu số571 gồm421 real giữ nguyên; bảng AI riêng giúp thấy tác động không bị loãng. Precision/recall/FPR/FNR/confusion/transition matrices và CI mọi source/cặp có trong JSON.

| AI source | Arm | N | Recall AI [CI95] | Uncertain [CI95] | Flip AI [CI95] |
|---|---|---|---|---|---|
| genimage_glide | B | 150 | 97.33 [94.67; 99.33] | 5.33 [2.00; 9.33] | 0.00 [0.00; 0.00] |
| genimage_glide | J | 150 | 97.33 [94.67; 99.33] | 7.33 [3.33; 12.00] | 2.00 [0.00; 4.67] |
| genimage_glide | R | 150 | 98.67 [96.67; 100.00] | 6.00 [2.67; 10.00] | 2.00 [0.00; 4.67] |
| genimage_glide | JR | 150 | 98.00 [95.33; 100.00] | 6.00 [2.67; 10.00] | 2.00 [0.00; 4.67] |
| genimage_midjourney | B | 150 | 95.33 [92.00; 98.67] | 11.33 [6.00; 16.67] | 0.00 [0.00; 0.00] |
| genimage_midjourney | J | 150 | 94.00 [90.00; 97.33] | 12.67 [7.33; 18.00] | 1.33 [0.00; 3.33] |
| genimage_midjourney | R | 150 | 95.33 [92.00; 98.67] | 11.33 [6.00; 16.67] | 0.00 [0.00; 0.00] |
| genimage_midjourney | JR | 150 | 94.00 [90.00; 97.33] | 12.67 [7.33; 18.00] | 1.33 [0.00; 3.33] |
| genimage_sd14 | B | 150 | 97.33 [94.67; 99.33] | 2.00 [0.00; 4.67] | 0.00 [0.00; 0.00] |
| genimage_sd14 | J | 150 | 98.00 [95.33; 100.00] | 1.33 [0.00; 3.33] | 0.67 [0.00; 2.00] |
| genimage_sd14 | R | 150 | 97.33 [94.67; 99.33] | 2.00 [0.00; 4.67] | 0.00 [0.00; 0.00] |
| genimage_sd14 | JR | 150 | 98.00 [95.33; 100.00] | 1.33 [0.00; 3.33] | 0.67 [0.00; 2.00] |

### Metadata và controls

| Cặp | Raw A_eff [CI95] | Post mọi arm A_eff [CI95] | Raw negative control | Positive raw/post |
|---|---|---|---|---|
| genimage_glide | 100.00 [100.00; 100.00] | 50.00 [50.00; 50.00] | 52.29 | 100 / 100 |
| genimage_midjourney | 100.00 [100.00; 100.00] | 50.00 [50.00; 50.00] | 54.97 | 100 / 100 |
| genimage_sd14 | 100.00 [100.00; 100.00] | 50.00 [50.00; 50.00] | 50.52 | 100 / 100 |

Cả13 metadata post đều hằng, mọi source/arm. A_eff0,5 [0,5;0,5] là phép kiểm suy biến, không chứng minh dữ liệu sạch shortcut. Control nhãn lộ chủ động chỉ kiểm probe; negative control chỉ chẩn đoán. Không thay gate D03/D04.

### Phân tích và hạn chế

1. Khác biệt kích thước/định dạng được xác nhận ở mức mô tả: GLIDE256 PNG, real JPEG cần fit/crop. Chưa xác nhận resize là nguyên nhân phân loại của CLIP.

2. JPEG bổ sung không giảm LR fixed real–GLIDE (81,43%→81,43%). Resample/refit vẫn82,71%. **Chưa loại trừ shortcut nén kép/GLIDE**; không kết luận model đã học dấu vết AI tổng quát.

3. Midjourney post LR fixed67,27%→67,61% sau J. SD1.4 54,06%→54,06%, CI gồm50%. Probe không phát hiện tín hiệu không chứng minh mọi tín hiệu đều vắng mặt. Tree và các mode/arm đều được báo.

4. Model pair GLIDE B/J97,72%, R98,07%; Midjourney B97,20%→J96,85%, degradation+0,35pp, CI[-0,35;+1,05]pp; SD1.4 B97,72%→J97,90%. Biến thiên nhỏ trên validation đã tiếp xúc không chứng minh khả năng tổng quát hoặc hết shortcut.

5. Flip AI cao nhất3/150=2% ở GLIDE J/R/JR; uncertain GLIDE J tăng8/150→11/150. Midjourney J recall143/150→141/150. Đọc cùng CI/transition matrix, không suy nhân quả từ ít mẫu.

6. Không cộng ba lần sử dụng cùng real/biến thể thành mẫu độc lập. Không dùng test lịch sử84,54% làm baseline mới, không mở lại384 test, không tune/thay model API. JPEG ghost deferred; near-duplicate và QA độc lập còn thiếu.

### Kiểm chứng và bàn giao

Ruff check qua; format115file. Full suite code cuối: **676 passed,0 failed,2 skipped,1 xfailed**, app coverage98,52%,271,60s; targeted72passed. Skip Locust tùy chọn và strict xfail thread có sẵn trên main. CI lint/test/ci-ok đã qua trên commitcode; các commit sau chỉ tài liệu/JSON, không đổi Python.

Đã đối chiếu CSV:28 ô model,81 ô audit,3.484 outcomes; confusion/accuracy/BA/AUROC/flip/degradation khớp; không NaN/Infinity/đường dẫn cá nhân. ZIP CRC/SHA khớp, giải nén rồi summarize không model/ảnh cho số đo/provenance giống hệt, chỉ analysis UUID/time mới. Đã tải lại GitHub asset, checksum ZIP khớp. Đây là kiểm nội bộ phía gửi, không QA độc lập.

```text
Protocol SHA256: a760c99e64390c00acb861e82f9e26879db4734cd197c2c1c0e6133f6d03cca8
Report SHA256:   063216f4fb753d49cce0560ab3fa7ecc9e570dba4d1faff1be187721ad251a5b
Evidence ZIP:    04c60fe5b5c1ac6690e3b25f47bdef80ed4789a9a7da4fb7bf6f932b4518983c
```

Gói4.218.718bytes chứa protocol/manifests/predictions/log/checksum/report/hướng dẫn; không ảnh, weights, cache hoặc CSV Jira. [GitHub evidence](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/releases/tag/adv10-shortcut-e571-20261111). #59 đã chạy, chờ Lực review; không tự đóng issue.
