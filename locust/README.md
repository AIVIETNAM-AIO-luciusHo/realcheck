# locust/ – Đo tải

Phụ trách: Lực

## Làm gì
Các kịch bản tách riêng, cho `POST /v1/analyze` qua cổng gateway:

- **baseline** (`baseline.conf`): rate thấp, đo p95/RPS của request 200 đúng schema.
- **rate-only** (`rate_only.conf`, file này ghim `rc-scenario = rate_only`): wait=0, một IP, chỉ quan sát 10 r/s/IP và 429. Không dùng số này công bố năng lực suy luận.

- **stress** (`stress.conf`, bậc đầu 10 user), **recovery** (`recovery.conf`, 1 user), **soak** (`soak.conf`, 2 user, không có thời lượng mặc định: bắt buộc `-t <thời lượng>`; D14 chốt cho MVP soak 30 phút, `-t 30m`). Số user của baseline và soak khớp SLO 14/11. Stress nhiều bậc: chạy lại với `-u 25 -r 5` rồi `-u 50 -r 5`, mỗi bậc một `RC_SIDECAR`. Wait của chúng theo `RC_WAIT_MIN/MAX` như baseline.

Locust không tự kết luận đạt/không đạt: lấy ngưỡng từ SLO đã duyệt bằng `python -m scripts.check_performance --scope load|soak|recovery` (soak cần `--rss`). Chưa có SLO duyệt thì chỉ là baseline. Stress không có ngưỡng số trong spec nên không có scope chấm. Không có Prometheus/Grafana.

## Cách chạy
```bash
pip install -r locust/requirements.txt          # từ máy đo, không phải server
RC_PAYLOAD_DIR=/đường/dẫn/payloads RC_SIDECAR=artifacts/run1.jsonl \
RC_COMMIT=<sha> RC_IMAGE=<digest> RC_MODEL=<hash> RC_PROFILE=<hash> RC_CONFIG_HASH=<hash> \
RC_CLIENT="<cpu/ram>" RC_SERVER="<cpu/ram>" \
  locust --config locust/baseline.conf --host http://<gateway>
python -m scripts.perf_report artifacts/run1.jsonl --warmup-seconds 30
python -m scripts.check_performance --sidecar artifacts/run1.jsonl --slo docs/performance/slo.json
```
`RC_PAYLOAD_DIR` có các thư mục con (ví dụ `jpeg/`, `png/`, `phone/`) chứa ảnh `.jpg/.png` thật, raw. Locustfile gửi nguyên byte, không resize, không model stub. Locust CLI (`-u -r -t`) ghi đè file conf.

## Payload GenImage (#123)

Tạo gói trên máy có raw GenImage bằng [script đóng gói](../scripts/README.md#gói-payload-locust-genimage-123).
Nhận `<goi>.zip` và `<goi>.zip.sha256` qua kênh nhóm; kiểm hash trước khi giải nén:

```bash
sha256sum -c <goi>.zip.sha256
unzip <goi>.zip -d payloads-genimage
mkdir -p .cache
RC_PAYLOAD_DIR=payloads-genimage RC_MIX=jpeg=50,png=50 RC_SIDECAR=.cache/baseline.jsonl locust --config locust/baseline.conf --host http://<gateway>
```

PowerShell: dùng `Get-FileHash <goi>.zip -Algorithm SHA256`, so với file checksum,
`Expand-Archive <goi>.zip payloads-genimage`, rồi đặt `$env:RC_PAYLOAD_DIR='payloads-genimage'`
và `$env:RC_MIX='jpeg=50,png=50'` trước lệnh `locust`.
`RC_PAYLOAD_DIR` trỏ tới thư mục có trực tiếp `jpeg/`, `png/`; không trỏ vào một nhóm con.
Manifest và README ở gốc không được Locust đưa vào pool.

Công cụ tạo gói cần Python 3.11+. `labels_sha256` băm byte CSV gốc, nên CRLF/LF làm
hash/ZIP khác; không thay checksum của gói cũ bằng gói tạo lại. Nhận đủ **ZIP và sidecar**,
không chỉ thư mục giải nén. Provenance mới lấy từ repo script, không từ cwd. Lỗi công bố
được rollback có kiểm ownership; nếu còn artifact, đọc cảnh báo cleanup trước khi xử lý.

Gói gồm 100 JPEG thật và 100 PNG AI từ GenImage train, giữ nguyên byte và kích thước gốc.
**Chỉ dùng đo tải, độ trễ và RPS; không dùng đánh giá độ chính xác.** Không có ảnh cá nhân/Zalo.
`payload-manifest.csv` cho phép đối chiếu tên payload trong sidecar với SHA256 và nguồn.
Baseline thật do QA chạy từ máy đo riêng, trên máy chủ đủ cấu hình; không đo tải trên VPS
dùng chung chỉ dành cho kiểm chức năng theo quyết định ở issue #42. Chưa có SLO được duyệt
thì kết quả chỉ là baseline. Kết quả gói/loader bằng test tổng hợp không phải số đo tải.

## Ghép payload điện thoại cho #132

Theo [bàn giao của Loan ngày 15/11](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/132#issuecomment-6898074933),
gói `payloads-phone-132-v2.zip` có **31 JPEG ảnh thật**. Gói giữ trên máy Loan,
chuyển trực tiếp cho người đo khi Lực chốt server; repo không chứa ảnh hoặc ZIP này.

1. Nhận ZIP, file `.zip.sha256` và manifest qua kênh nhóm. Kiểm trước khi giải nén
   bằng `shasum -a 256 -c payloads-phone-132-v2.zip.sha256` (Linux có thể dùng
   `sha256sum -c`). Hash ZIP phải là
   `69c1344f9dc9a882dd42f851606dbc98474158f15aad4bf0b8fa69ae400079b0`.
2. Giải nén vào thư mục riêng. SHA256 **byte gốc** của `payload-manifest.csv` phải là
   `b40fc46faf7a25b5d4156cca5cf6bc1294f812aa4a99bc0308d39a8f2471b128`.
   Không sửa CSV để ghép với manifest #123: giữ riêng cả hai manifest và giấy phép/ghi công.
3. Đối chiếu từng ảnh với manifest: SHA256, kích thước, đọc được ảnh; kiểm không thừa/thiếu.
   Hash ZIP/CSV đúng chưa thay cho bước này. Giữ nguyên 31 ảnh; không resize/nén lại.
4. Tạo thư mục payload mới có trực tiếp `jpeg/`, `png/` từ #123 và `phone/` từ gói Loan.
   Chỉ sao chép các nhóm ảnh vào đây; giữ manifest/README của mỗi gói ở thư mục nhận riêng,
   tránh ghi đè hai file cùng tên. Pool dự kiến: 100 JPEG + 100 PNG + 31 phone.
5. Đặt `RC_PAYLOAD_DIR` tới thư mục mới. `RC_MIX=jpeg=40,png=30,phone=30` chỉ là **ví dụ**;
   Lực chốt mix trước lượt đo, giữ cùng mix qua load/stress/recovery/soak.
   Trọng số là theo **nhóm**, không theo số ảnh; không đặt `RC_PAYLOAD_DIR` vào thư mục `phone/`.

Giữ giới hạn Loan đã nêu: 10 ảnh iPhone là bản Photos xuất 768×1024, nhẹ hơn ảnh gốc;
21 ảnh Commons cần giữ thông tin nguồn/tác giả/giấy phép trong manifest.
JPEG của GenImage đều thật, PNG đều AI nên định dạng còn lẫn với nhãn. Gói ghép
chỉ dùng đo tải; không dùng kết quả để kết luận accuracy hoặc đã hết shortcut định dạng.

Sidecar mới giữ `payload` (tên file cũ) và thêm `payload_path` tương đối với
`RC_PAYLOAD_DIR`, dùng dấu `/` (ví dụ `phone/same.jpg`), `payload_bytes`, `payload_sha256`.
Đối chiếu theo **đường dẫn nhóm + hash + kích thước** với manifest tương ứng, kể cả khi
hai nhóm trùng tên file. Hash được tính từ đúng byte gửi trong từng request, trước mốc
đo latency; chi phí đọc/hash vẫn nằm ở phía client và có thể ảnh hưởng RPS.
Đây là dấu vết truy xuất, không tự xác nhận giấy phép hoặc QA gói. Parser/gate vẫn đọc được
sidecar cũ. Chạy lại trong cùng tiến trình sẽ thay pool/trọng số bằng `RC_MIX` mới.

Chỉ chạy khi máy đủ điều kiện và được chốt theo
[chuẩn bị G06–G09](../docs/performance/README.md#chuẩn-bị-lượt-đo-lại-g06g09-132).

## Tham số

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `RC_PAYLOAD_DIR` | `payloads` | Thư mục payload |
| `RC_MIX` | đều giữa các thư mục | Trọng số theo tên thư mục con, ví dụ `jpeg=40,png=30,phone=30` |
| `RC_WAIT_MIN`/`RC_WAIT_MAX` | 1 / 3 | Think time (giây), dùng `wait_time` của Locust |
| `RC_WARMUP_SECONDS`/`RC_WARMUP_REQUESTS` | 0 / 0 | Ghi vào meta; parser bỏ phần warmup khỏi số đo (cờ `--warmup-*` ghi đè) |
| `RC_SIDECAR` | `sidecar.jsonl` | File JSONL đầu ra |
| `RC_COMMIT`, `RC_IMAGE`, `RC_MODEL`, `RC_PROFILE`, `RC_CONFIG_HASH`, `RC_CLIENT`, `RC_SERVER` | không | Ghi vào meta nếu có; không khai thì báo cáo ghi "thiếu" |

Kịch bản chọn bằng tham số Locust `--rc-scenario baseline|rate_only|stress|recovery|soak` (mặc định `baseline`), không dùng biến môi trường: mỗi file conf ghim sẵn kịch bản của nó, nên chạy `--config locust/rate_only.conf` luôn ra wait=0 và meta `scenario: rate_only`; không có cách quên đặt biến. Chạy tay không dùng conf mà muốn rate-only thì phải truyền `--rc-scenario rate_only`.

Users/spawn/thời lượng: `baseline.conf` mặc định **2 user, spawn 1/s, 5 phút** (warmup 30 s, đặt `RC_WARMUP_SECONDS=30`). Đây là D14 **cho MVP** theo SLO 14/11 (xem `docs/decisions/realcheck-baseline.md`, mục 15/11), đo trên máy chung phần cứng với client; số trên máy đạt cấu hình thuộc #132. Mix payload (40/30/30 hoặc 50/25/25) vẫn chưa chốt. Muốn đo mức khác thì truyền `-u N -r M` và ghi rõ trong báo cáo, không sửa SLO sau khi xem số.

## Input / Output
- Input: URL gateway, payload thật, biến môi trường trên.
- Output: sidecar JSONL. Dòng `meta` đầu, sau đó mỗi request một dòng: `t` (epoch bắt đầu), `outcome` (`200`, `invalid200`, `429`, `503`, `504`, `5xx`, `other`), `status`, `error_code` (envelope), `latency_ms`, `payload`, `payload_path`, `payload_bytes`, `payload_sha256`. CSV tổng của Locust không dùng để tính p95 riêng 200.

## Lưu ý và giới hạn
- Chạy từ máy khác, không trên chính server; không giả `X-Forwarded-For` để né limiter.
- Response 200 sai schema hoặc score ngoài [0,1]/không hữu hạn là failure (`invalid200`).
- 429/503/504 không bao giờ tính vào RPS thành công.
- Lượt đo không có SLO được duyệt chỉ là baseline; SLO 14/11 đã được duyệt cho MVP, file ký giữ ngoài repo.
- QA đã đo `/v1/analyze` ngày 14–15/11 trên máy chung phần cứng với client (xem #132); lượt trên server đủ cấu hình, có stress và client riêng vẫn chưa làm. Test mock không thay số đo thật.
- Quy trình recovery (thời lượng, giờ dừng/bật API, cửa sổ đo, `--warmup-seconds`, tiêu chí hợp lệ): xem [`docs/performance/README.md`](../docs/performance/README.md#quy-trình-recovery-g09-130).
- Schema SLO và cách điền: xem [`docs/performance/README.md`](../docs/performance/README.md). Sidecar phải có meta `scenario` khớp scope (load=baseline, soak, recovery), nếu không `check_performance` thoát 2. Chưa có percentile toàn traffic.
- Sidecar có latency âm hoặc `--warmup-*` âm bị từ chối (thoát 2).
- `RC_MIX` sai (nhóm lạ, trọng số âm/không hữu hạn, tổng bằng 0) làm Locust thoát với thông báo `RC_MIX`. Meta `wait` ghi đúng wait thật (rate_only là `[0, 0]`). Mốc `t` là `time.time()`; latency không gồm đọc file payload.
- Test liên quan locustfile (`test_locustfile_voi_locust_that`, `test_locust_kich_ban_moi_va_soak_can_run_time`) tự bỏ qua khi máy không có locust (CI nhẹ); cài `pip install -r locust/requirements.txt` để chạy.
