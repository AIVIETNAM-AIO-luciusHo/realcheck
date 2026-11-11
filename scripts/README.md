# scripts/ – Script tiện ích

Phụ trách: Lực (review chéo), người viết ghi tên vào PR

## Làm gì
Script đánh giá (Accuracy, Precision, Recall, confusion matrix, % "Chưa chắc") và script tải/chuẩn hóa dữ liệu.

## Cách chạy
`python -m scripts.<tên_script>` từ thư mục gốc repo.

| Script | Người viết | Làm gì |
|---|---|---|
| `download_data.py` | Loan | Tải CIFAKE, GenImage về `data/raw/` |
| `prepare_data.py` | Loan | Chuẩn hóa ảnh, chia tập, xuất `data/labels.csv` |
| `check_data.py` | Loan | Kiểm tra `labels.csv` và ảnh đã chuẩn hóa; lỗi thì thoát mã 1 |
| `check_normalization.py` | Lực | `python -m scripts.check_normalization --raw-dir <dữ liệu thô>`: so sha256 của `jpeg` chuẩn hóa lại với `data/processed_baseline.sha256`, kiểm kê ảnh thô (labels hoặc `rejected_small/invalid/duplicate.csv`, tham số `--rejected-dir`, `--rejected-small/-invalid/-duplicate`). Thoát 0 đạt, 1 lỗi kiểm tra, 2 thiếu đầu vào, 3 ảnh thô hỏng. `rejected_duplicate.csv` tùy chọn để đọc được output cũ chưa có file này; `prepare_data` hiện luôn ghi file này |
| `check_raw_baseline.py` | Lực | T013: `python -m scripts.check_raw_baseline --raw-dir <data/raw của bản sao T013> [--rejected-small f.csv]`. Độc lập với `models.normalize`: dùng lại công thức `prepare_data` cũ (exif, RGB, fit 256 chỉ genimage, JPEG q95) cho MỌI dòng baseline, so sha256, in số OK/FAILED/thiếu; kiểm header baseline (commit, Pillow, sha `labels.csv`), `norm_version`, và (có `--rejected-small`) ảnh genimage <256px phải bị loại; thiếu `--rejected-small` thì in WARNING rõ ràng rằng kiểm ảnh nhỏ bị bỏ qua (OK không gồm kiểm này); khi sha lệch và Pillow khác header, WARNING Pillow được in lại cạnh dòng FAILED. Thoát 0 đạt, 1 lệch/thiếu/sai phiên bản, 2 thiếu đầu vào (kèm hướng dẫn dựng dữ liệu), 3 ảnh thô hỏng. Chưa chạy trên raw thật |
| `jpeg_trace_check.py` | Lực | **Chưa có** (T027, KAN-46): chờ nhóm xác nhận phương pháp JPEG ghost; chưa dùng được |
| `perf_report.py` | Lực | `python -m scripts.perf_report <sidecar.jsonl> [--warmup-seconds N] [--warmup-requests N] [--output f.json]`: p50/p95/p99 chỉ của 200, offered RPS, RPS 200, đếm 429/503/504/5xx/other, tỉ lệ lỗi không tính 429; số đo thiếu ghi "thiếu". Thoát 2 nếu sidecar thiếu/rỗng/hỏng. Thuần stdlib |
| `check_performance.py` | Lực | `python -m scripts.check_performance --sidecar <jsonl> --slo docs/performance/slo.json [--scope load\|soak\|recovery] [--rss rss.json]`: thoát 0 đạt, 1 không đạt, 2 thiếu/hỏng/chưa duyệt SLO, scenario sidecar lệch scope hoặc sidecar hỏng (in "chỉ là baseline, không kết luận đạt SLA"). Schema SLO và mẫu: [`docs/performance/`](../docs/performance/README.md). `soak` thêm kiểm RSS tăng, `recovery` chỉ xét p95 và lỗi. |
| `check_mvp_gates.py` | Lực | `python -m scripts.check_mvp_gates [--artifacts artifacts] [--slo docs/performance/slo.json]`: bảng 9 gate nghiệm thu core (nguồn spec 000 SC/AC và DoD T021-T031), file bằng chứng, trạng thái đạt / chưa đạt / thiếu bằng chứng. File thiếu hoặc rỗng không bao giờ là đạt. Thoát 0 chỉ khi mọi gate đạt, ngược lại 1. |
| `make_fixtures.py` | Lực | `python -m scripts.make_fixtures --out .cache/smoke-fixtures` (mặc định; `.cache/` đã gitignore): ảnh mẫu tổng hợp, tất định, cho smoke API (4000x3000 có/không EXIF, Orientation=6, quá nhỏ/biên, 0 byte, text giả, cắt cụt, APNG/GIF, đúng 5.242.880 và +1 byte bằng JPEG hợp lệ đệm byte 0 sau EOI, 6000x6000 và cạnh 10001 đơn sắc để thử D07) |
| `smoke_api.py` | Lực | `python -m scripts.smoke_api --base-url http://localhost:8000 --fixtures <thư mục> [--real ảnh] [--ai ảnh] [--out json]`: kiểm `/health`, `/docs`, `/openapi.json`, schema `/v1/analyze` và mã lỗi D05 qua HTTP thật (không import `app/`). Thoát 0 đạt, 1 có ca lỗi, 2 không kết nối, timeout (dừng ngay ở request đầu tiên quá `--timeout`, mặc định 60 s, dài hơn timeout model 10 s của D11; Nginx/UI cũng phải dài hơn 10 s) hoặc thiếu fixture. `--real/--ai` chỉ ghi nhận verdict/score. `X-Request-ID` phải là UUID (theo `app/logging.py`) và khác nhau giữa các request. `--delay 0.15` nghỉ giữa hai request, bắt buộc khi chạy qua Nginx (10 r/s, burst 10), nếu không các ca cuối nhận 429; gọi thẳng API không cần. `--no-docs` bỏ `/docs`, `/openapi.json` (bảng ghi `bỏ qua`, không phải `đạt`; mặc định vẫn kiểm vì AC1 của KAN-29 cần `/docs`). Ca `Đúng 5.242.880 byte (cần xác nhận)` dùng JPEG đệm byte 0 sau EOI: D06 nói tối đa, bằng thì phải qua, nhưng API/gateway chặt hơn có thể từ chối; ca lỗi thì kiểm cách API tính dung lượng và overhead multipart trước khi kết luận API sai; `--skip-size-boundary` bỏ ca này. JSON bằng chứng ẩn `user:pass@` trong `base_url` Mẫu biên bản: `docs/qa/integration-report-template.md` |
| `check_gateway.py` | Lực | `python -m scripts.check_gateway --base-url http://localhost --fixture <ảnh> --rate <r/s> --burst <n> --upstream prompt\|skip [--wait-seconds N] [--cooldown s] [--only under rate body boundary] [--poll-interval s] [--require-retry-after] [--out json]`: kiểm gateway chỉ bằng HTTP (KAN-54): dưới giới hạn 200, vượt giới hạn 429 (không 5xx, không đặt X-Forwarded-For), 413 body vượt 5.242.880 B, X-Request-ID, upstream tắt/chậm trả 502/503/504 envelope không lộ nội bộ rồi phục hồi (người chạy tự tắt/bật upstream, script chỉ hỏi/chờ). `--rate`, `--burst` bắt buộc (D13 chưa chốt, script không tự đặt). Ca biên đúng 5.242.880 B (AC-09) chỉ kiểm gateway không chặn 413/429/5xx. Quét rò rỉ ở 429, 413, 502/503/504 theo FR-N03 (chỉ cấm traceback và chi tiết nội bộ, không cấm tên phần mềm): body (cả bản đã giải mã JSON) chứa traceback, `File "`, tên upstream; header `Server` chỉ lỗi khi có SỐ PHIÊN BẢN (`nginx/1.25.3`; `Server: nginx` thì xanh); `X-Powered-By` có mặt là lỗi. Thêm ca biên +1 B (413). Không gắn `X-Forwarded-For`. Timeout hoặc ngắt kết nối sau khi đã có phản hồi là ca lỗi (thoát 1, vẫn in kết quả và ghi `--out`). Thoát 0 đạt, 1 có ca lỗi, 2 thiếu tham số/fixture, không tới được gateway hoặc stdin đóng khi `--upstream prompt` (kết quả đã có vẫn in). Mẫu biên bản: `docs/qa/gateway-report-template.md` `--junit artifacts/integration.xml` ghi JUnit cho gate G04 của `check_mvp_gates`: mỗi ca là một testcase, ca lỗi là `failure`; `--upstream skip` thêm testcase `skipped` và chạy dở thêm `error`, nên G04 chỉ đạt khi đã kiểm cả tắt/bật upstream. |
| `baseline_filesize.py` | Loan | Dung lượng file theo nguồn, chỉ tham khảo độ chi tiết ảnh (không phải gate) |
| `metadata_audit.py` | Loan | Đoán thật/AI chỉ từ metadata, raw và post; gate post `A_eff <= 0.55`, không đạt thì thoát mã 1 (bản nháp T007) |
| `evaluate.py` | Loan | `python -m scripts.evaluate --split val --output <file>`: báo cáo validation theo source, ngưỡng lấy từ model, không ghi đè output. GenImage test dùng `models.evaluate` với protocol đã duyệt và lịch sử holdout; `--split test` ở script này chỉ dùng cho CIFAKE smoke test. `--robustness`: chấm manifest robustness, xem mục Robustness bên dưới |
| `robustness_manifest.py` | Loan | ADV-07/ADV-06: tạo biến thể từ ảnh test cha và liệt kê cohort điện thoại, AI mới, Zalo thành manifest JSONL; xem mục Robustness |
| `verify_ml.py` | Kiệt | Model thật: parity tensor train/serve, score từ raw so feature cache, ảnh lớn/mode ảnh/ảnh nhỏ; chỉ lấy mẫu validation |

Thư viện cho các script dữ liệu: `pip install -r scripts/requirements-data.txt`. Thứ tự chạy xem [`data/README.md`](../data/README.md).

Chuẩn hóa mới dùng chung `models.normalize` với ML, không cần torch. Để giữ nguyên dữ liệu/manifest cũ:

```bash
python -m scripts.prepare_data --output-dir .cache/ml-run/processed-v1 --labels .cache/ml-run/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-run/labels.csv
```

`prepare_data` từ chối ghi đè output đã có; dùng đường dẫn mới khi chạy lại. `rejected_small.csv` chỉ chứa ảnh quá nhỏ; ảnh hỏng và `DecompressionBombError` vào `rejected_invalid.csv` riêng, ảnh trùng vào `rejected_duplicate.csv`, cùng các cột `raw_path,source,width,height,reason,norm_version` (kích thước là 0 nếu chưa đọc được). Lỗi ghi output phải làm lần chạy thất bại, không được coi là ảnh hỏng. `--workers` mặc định 2 để tránh tạo quá nhiều process trên Windows. Trước khi thay dữ liệu chuẩn chính của Loan vẫn cần baseline theo spec 001.

Để giữ split cũ cho các ảnh còn hợp lệ, dùng manifest tham chiếu thay vì chia lại:

```bash
python -m scripts.prepare_data --split-from data/labels.csv --output-dir .cache/ml-preserve/processed --labels .cache/ml-preserve/labels.csv --workers 2
python -m scripts.check_data --labels .cache/ml-preserve/labels.csv
```

`--split-from` ghép theo `raw_path` tương đối với `data/raw` hoặc `--raw-dir`, không theo thứ tự dòng. Manifest phải có `raw_path,label,source,split` cho đúng toàn bộ raw đang quét, kể cả ảnh sau đó bị loại; thiếu/trùng/khác cohort, sai nhãn/source/split hoặc chuyển ảnh CIFAKE qua test gốc đều bị từ chối trước khi ghi output. Hỗ trợ đường dẫn Windows, UTF-8 BOM và manifest cũ chưa có norm_version. Hash file tham chiếu được in vào log; nếu file đổi trong lúc xử lý thì không xuất labels mới. Không truyền cờ này thì vẫn chia theo seed 42 như trước. Script không sửa ảnh raw hoặc manifest tham chiếu; ảnh không dùng nằm trong các rejection CSV của output mới. Xem [bản ứng viên giữ split cũ](../docs/ml-preserved-split.md).

`check_data` yêu cầu đủ sáu cột, bao gồm `norm_version` ở cuối và đúng version hiện hành. Manifest cũ thiếu version là lỗi (exit 1), không còn chỉ cảnh báo; không tự thêm version vào dữ liệu cũ. Ảnh processed hỏng hoặc decompression bomb được ghi FAIL, lần kiểm tra thoát mã 1. Lệnh train xem [`models/README.md`](../models/README.md).

`verify_ml` chỉ lấy mẫu validation, từ chối nếu thiếu nguồn GenImage/ảnh validation, tensor lệch, score lệch, encoder chưa frozen hoặc ảnh nhỏ vẫn được chấp nhận. Báo cáo có UUID, lệnh gọi, commit, trạng thái dirty, Python và OS; test mock không thay thế lần chạy model thật. Xem [truy vết và tái lập](../docs/ml-reproducibility.md).

## Robustness (ADV-06, ADV-07)
Chỉ để đánh giá model đã khóa (#39); không chọn model hay ngưỡng bằng các cohort này. Output và ảnh để trong `.cache/`, không đưa vào Git.

1. Biến thể từ ảnh test cha. `parents.csv` có cột `path` (tính từ file CSV), `label`, `source`, `group_id` lấy từ manifest lineage đã chốt:
   ```bash
   python -m scripts.robustness_manifest variants --parents parents.csv --output .cache/robustness/variants.jsonl
   ```
   Mỗi ảnh cha sinh 7 ảnh con giữ `group_id`, `label`, `source` của cha (AC-18): `jpeg90/70/50` (chỉ đổi chất lượng JPEG), `rotate` 90° ngược chiều kim đồng hồ, `crop` giữ 80% ở giữa, `downscale` 0,5, `brightness` ×1,3. `crop` và `downscale` không làm cạnh ngắn dưới 256 px, nên ảnh cha 256 px gần như không đổi kích thước. Ảnh hình học và độ sáng lưu PNG để chỉ có đúng một thay đổi. Ảnh cha trùng byte phải cùng group và chỉ liệt kê một lần. Mọi ảnh cha được kiểm trước khi ghi: thiếu cột, sai nhãn, không có file, không giải mã được hoặc cạnh ngắn dưới 256 px đều bị liệt kê hết và không ghi gì. Lỗi khi đang ghi thì xóa thư mục ảnh con vừa tạo.
2. Cohort thực tế: mỗi thư mục có `sources.csv` với cột `file`, `source` (thiết bị hoặc công cụ AI), `label`; Zalo thêm `parent_file` (tên file trong cohort điện thoại) nếu là bản gửi lại của ảnh đó, khi đó ảnh Zalo giữ group và source của ảnh gốc:
   ```bash
   python -m scripts.robustness_manifest cohort --name phone --dir <thư mục> --output .cache/robustness/phone.jsonl
   python -m scripts.robustness_manifest cohort --name zalo --dir <thư mục> --parent-manifest .cache/robustness/phone.jsonl --output .cache/robustness/zalo.jsonl
   ```
   `phone` phải nhãn 0, `ai_new` nhãn 1. Từ chối và liệt kê mọi ảnh thiếu nguồn/nhãn, không giải mã được, có vị trí GPS trong EXIF, trùng, hoặc có trong CSV mà không có file. Việc loại ảnh có người hay thông tin riêng tư vẫn phải làm bằng mắt trước khi lưu. Lỗi đầu vào của cả hai lệnh thoát mã 2, không in traceback.
3. Gộp manifest: đường dẫn ảnh tính từ file manifest, nên chỉ gộp bằng `cat variants.jsonl phone.jsonl ... > manifest.jsonl` khi các manifest nằm **cùng thư mục** (như các lệnh trên). Khóa protocol ADV-08 (`docs/robustness-adv08.md` của #64) với SHA256 của model, model manifest và manifest này, rồi chấm:
   ```bash
   python -m scripts.evaluate --robustness --manifest .cache/robustness/manifest.jsonl --model <model.joblib> --model-manifest <manifest.json> --protocol <protocol.json> --output .cache/robustness/predictions.csv
   ```
   Cổng chặn tập test, kiểm hết **trước khi nạp CLIP**: protocol phải là JSON `schema_version` 1, `status` `locked`, có `manifest_lock_ref`, `split_review_ref`, đúng profile và ngưỡng của model, `artifacts.{model,model_manifest,manifest}.sha256` khớp đúng các file truyền vào, và mọi cohort trong manifest được đăng ký `present` với cùng `transform`. Manifest phải đủ cột, nhãn là số nguyên 0/1, `split=test`, `sample_id` không trùng, ảnh trùng byte cùng group. Mỗi protocol chỉ chấm một lần: `<protocol>.used.json` được ghi trước ảnh đầu tiên và không được xóa để chạy lại. Lỗi đầu vào thoát mã 2 với thông báo rõ.

   Mỗi ảnh chấm qua đúng đường API (`app.uploads.analyze_image`, `app.verdict.decide_verdict`), một dòng `sample_id,group_id,parent_id,label,status,score,verdict,error_code,model_sha256,manifest_sha256,protocol_sha256`. Ảnh lỗi ghi `status=error` với mã lỗi API. Không ghi đè `<output>`, `<output>.partial` hay `<output>.run.json`. Dòng ghi dần vào `<output>.partial`, chỉ đổi tên khi chạy xong và hash đầu vào không đổi; ảnh đổi byte giữa chừng dừng lần chạy (thoát 1) và giữ file partial. Log chạy ở `<output>.run.json`. Metrics và flip rate do `scripts.analyze_robustness` (ADV-08) tính từ file này.

## Input / Output
- Input: `data/labels.csv`, `models/clip_probe.joblib`.
- Output: bảng số đo, `labels.csv`.

## Lưu ý và giả định
- Script phải chạy lại được và cho cùng kết quả.

## ADV-10 (#59)

`python -m scripts.shortcut_controls {prepare,run,summarize}`: đối chứng JPEG/resample GLIDE, probe fit train và model khóa đánh giá validation. [Lệnh và giới hạn](../docs/shortcut-adv10.md). Không dùng CLI audit cũ để mở test.

## Mở rộng dữ liệu và train mixed

`download_expansion.py` tải mẫu có revision cố định, tái sử dụng pool/catalogue local và giữ provenance/resume journal. `train_expansion.py` screen ảnh, chống trùng lịch sử, chia validation theo nguồn/thiết bị, fit mixed probe rồi khóa model trước đánh giá OpenFake. Dùng `--prepare-only` để kiểm manifest trước fit. Artifact, lệnh thực tế và giới hạn lấy mẫu nằm trong [biên bản 10/11/2026](../docs/ml-data-expansion-20261110.md); cần giữ used marker và dữ liệu cũ để truy vết.
