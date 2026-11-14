# Cách tạo bằng chứng cho từng cổng nghiệm thu G01 đến G09 (#133)

`python -m scripts.check_mvp_gates` đọc các file bằng chứng trong một thư mục (mặc định `artifacts/`) và chấm 9 cổng. Tài liệu này ghi lệnh tạo từng file. Mọi lệnh và cờ dưới đây có trong repo; chạy từ gốc repo, trong venv đã cài `requirements.txt` và `models/requirements-ml.txt`.

**Bằng chứng nằm ngoài Git.** Không commit `artifacts/` (số đo, log, `slo.json` chỉ có ý nghĩa với đúng lần chạy, commit và máy đã tạo ra chúng). Mỗi bộ bằng chứng lưu ở nơi người chạy chọn (ổ chia sẻ hoặc đính kèm báo cáo), kèm SHA256 từng file (mục "Ghi SHA256") và commit đã chạy (`git rev-parse HEAD`). Thiếu hoặc rỗng một file thì cổng đó là "thiếu bằng chứng", không bao giờ là "đạt".

## Bảng tổng

| Cổng | Nội dung | File trong `artifacts/` | Mục |
|---|---|---|---|
| G01 | ruff, pytest ≥ 15 ca, coverage `app/` ≥ 70% | `unit.xml`, `coverage.xml` | 1 |
| G02 | Audit metadata post: không rỗng và A_eff ≤ 0,55 | `metadata-audit.json` | 2 |
| G03 | Accuracy GenImage test ≥ 90% | `evaluation.json` | 3 |
| G04 | Gateway Nginx và phục hồi | `integration.xml` | 4 |
| G05 | UI qua gateway, phiên độc lập | `ui-gateway.xml` | 5 |
| G06 | SLO đã duyệt và ký | `docs/performance/slo.json` (đường dẫn qua `--slo`) | 6 |
| G07 | Tải đạt SLO | `load.jsonl` (+ SLO) | 7 |
| G08 | Soak đạt SLO và RSS | `soak.jsonl`, `soak-rss.json` (+ SLO) | 8 |
| G09 | Phục hồi đạt SLO | `recovery.jsonl` (+ SLO) | 9 |

```bash
mkdir -p artifacts
```

## 1. G01: unit test và coverage

```bash
python -m ruff check . && python -m ruff format --check .
python -m pytest --junitxml=artifacts/unit.xml --cov=app --cov-report=xml:artifacts/coverage.xml --cov-fail-under=70 -q -ra
```
Cổng đòi ≥ 15 testcase, không fail, không error, không skip (xfail không tính là skip) và `line-rate` ≥ 0,70. Một số test tự bỏ qua khi máy thiếu `locust`; cài `pip install -r locust/requirements.txt` rồi chạy lại, và xem `-ra` để biết test nào còn skip. Còn skip thì G01 vẫn là "chưa đạt".

## 2. G02: audit metadata

```bash
python scripts/metadata_audit.py                       # đọc data/labels.csv, ghi data/metadata_audit.json (cần ảnh trong data/processed)
cp data/metadata_audit.json artifacts/metadata-audit.json
python scripts/check_release_audit.py --fail-on-vacuous artifacts/metadata-audit.json
```
G02 dùng cùng logic với `check_release_audit.py --fail-on-vacuous` (không đọc cờ `gate.passed`). Báo cáo hiện có (13/13 đặc trưng post là hằng số) cho kết quả **chưa đạt**; chỉ đạt khi có probe có nghĩa và A_eff ≤ 0,55 (#134, #118).

## 3. G03: accuracy GenImage test

`evaluation.json` phải có `dataset.version == "genimage"`, số đo `test` (accuracy ≥ 0,90, n ≥ 1) và `quality.status == "pass"` (dạng `models.evaluate`) hoặc `accuracy_target.passed == true` (dạng `scripts.evaluate --split test`).

- `python -m scripts.evaluate --split val --output artifacts/evaluation-val.json` chỉ cho split val; không dùng làm bằng chứng G03.
- Báo cáo test thật do `models.evaluate` ghi, sau khi khóa protocol (cần dữ liệu, đặc trưng và history labels):
  ```bash
  python -m models.evaluate --labels data/labels.csv --features <thư mục đặc trưng> --model models/clip_probe_e571.joblib \
      --history-labels <labels cũ> --prepare-lock <lock.json> --output-dir <thư mục>
  python -m models.evaluate ... --lock <lock.json> --output-dir <thư mục>   # chấm; chỉ một lần
  ```
  Xem `models/evaluate.py` và [`docs/ml-final-experiment.md`](../ml-final-experiment.md) để biết các tệp lock và điều kiện phê duyệt.
- Quyết định 14/11 (xem [`realcheck-baseline.md`](../decisions/realcheck-baseline.md)): G03 dùng `docs/reports/ml-final-experiment.json` làm `evaluation.json`, kèm ghi rõ **chưa QA độc lập** (94,53% trên 384 ảnh đã lọc):
  ```bash
  cp docs/reports/ml-final-experiment.json artifacts/evaluation.json
  ```

## 4. G04: gateway và phục hồi (cần Compose + model thật)

```bash
docker compose up -d --build            # cổng 80 bận thì đặt REALCHECK_HTTP_PORT trong .env (xem nginx/README.md)
curl -s http://localhost/health         # đợi model_ready: true
python -m scripts.check_gateway --base-url http://localhost --fixture <ảnh hợp lệ> --rate 10 --burst 10 \
    --upstream prompt --junit artifacts/integration.xml --out artifacts/gateway-evidence.json
```
`--upstream prompt` dừng để bạn tắt/bật API tay (hoặc `--wait-seconds N`) cho các ca 502/504/phục hồi; `--upstream skip` bỏ các ca này nên không đủ cho G04. Cổng đòi JUnit không fail và không skip.

## 5. G05: UI qua gateway

Stack Compose của mục 4 đang chạy:
```bash
REALCHECK_GATEWAY_URL=http://localhost python -m pytest tests/integration --junitxml=artifacts/ui-gateway.xml
```
Không đặt `REALCHECK_GATEWAY_URL` thì thư mục này không được thu thập (không có test, không có file).

## 6. G06: SLO đã ký

```bash
cp docs/performance/slo.template.json docs/performance/slo.json   # điền số từ perf_report và chữ ký; xem docs/performance/README.md
```
`slo.json` cố ý không có trong repo và không commit. Chưa duyệt (`approved` không đúng) thì G06 và cả G07 đến G09 là "chưa đạt".

## 7. G07: tải

Từ máy đo (không phải server), cài `pip install -r locust/requirements.txt`:
```bash
RC_PAYLOAD_DIR=<thư mục payload> RC_SIDECAR=artifacts/load.jsonl RC_COMMIT=<sha> RC_MODEL=<hash> RC_CLIENT="<cpu/ram>" RC_SERVER="<cpu/ram>" \
  locust --config locust/baseline.conf --host http://<gateway>
python -m scripts.perf_report artifacts/load.jsonl --warmup-seconds 30 --output artifacts/load-report.json
python -m scripts.check_performance --sidecar artifacts/load.jsonl --slo docs/performance/slo.json --scope load
```
503 `SERVICE_BUSY` tính là lỗi trong `error_ratio_excl_429` (quyết định 14/11): đo với tải vừa phải và ghi rõ năng lực.

## 8. G08: soak và RSS

```bash
RC_PAYLOAD_DIR=<thư mục payload> RC_SIDECAR=artifacts/soak.jsonl locust --config locust/soak.conf -t 30m --host http://<gateway>
python -m scripts.soak_rss --container <tên container api> --duration-seconds 1800 --warmup-seconds 300 --output artifacts/soak-rss.json   # chạy song song, từ máy có docker
python -m scripts.check_performance --sidecar artifacts/soak.jsonl --slo docs/performance/slo.json --scope soak --rss artifacts/soak-rss.json
```
`soak.conf` không có thời lượng, bắt buộc `-t`. `soak_rss` đo bằng `docker stats` (cgroup, không phải VmRSS) và ghi đúng `rss_after_warmup_mb`, `rss_end_mb`. Soak 30 phút không chứng minh không rò bộ nhớ dài hạn.

## 9. G09: phục hồi

Chạy sau stress, cùng server (xem `locust/README.md`):
```bash
RC_PAYLOAD_DIR=<thư mục payload> RC_SIDECAR=artifacts/recovery.jsonl locust --config locust/recovery.conf --host http://<gateway>
python -m scripts.check_performance --sidecar artifacts/recovery.jsonl --slo docs/performance/slo.json --scope recovery
```
Sidecar phải có meta `scenario` đúng scope (load là `baseline`, `soak`, `recovery`); không khớp thì `check_performance` thoát 2.

## Ghi SHA256 và chạy cổng

```bash
(cd artifacts && sha256sum unit.xml coverage.xml metadata-audit.json evaluation.json integration.xml ui-gateway.xml load.jsonl soak.jsonl soak-rss.json recovery.jsonl > SHA256SUMS)
git rev-parse HEAD > artifacts/COMMIT.txt
python -m scripts.check_mvp_gates --artifacts artifacts --slo docs/performance/slo.json
```
Thoát 0 chỉ khi cả 9 cổng đạt, ngược lại 1. Dán đầu ra và `SHA256SUMS` vào báo cáo nghiệm thu, cùng commit, ngày, máy chạy và các giới hạn (xem `docs/qa/integration-report-template.md`).
