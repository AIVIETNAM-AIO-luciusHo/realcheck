# docs/performance/ – SLO hiệu năng

Phụ trách: Lực

`slo.template.json` là **mẫu trống**. Repo cố ý không có `slo.json`: số SLO chỉ được điền từ số đo thật (baseline, T029) và chữ ký nhóm (T030). Chưa có `slo.json` duyệt thì mọi lệnh kiểm trả mã 2 "chỉ là baseline".

## Điền từ perf_report
1. Chạy baseline, rồi `python -m scripts.perf_report artifacts/baseline.jsonl --warmup-seconds N --output artifacts/baseline-report.json`.
2. Nhóm chọn ngưỡng dựa trên số đó (phương án thảo luận ở spec 000 D09/D10 chưa là gate), ghi lý do vào biên bản.
3. `cp slo.template.json slo.json`, điền:

| Trường | Ý nghĩa | Lấy từ |
|---|---|---|
| `p95_ms_max` | p95 của 200 đúng schema, ms, > 0 | `latency_200_ms.p95` |
| `rps200_min` | RPS 200 tối thiểu, >= 0 | `rps200` |
| `error_ratio_max` | ngân sách lỗi không tính 429, 0..1 | `error_ratio_excl_429` |
| `rss_growth_pct_max` | % RSS tăng sau warmup trong soak, >= 0 | theo dõi tài nguyên (Quang) |
| `recovery_criterion` | mô tả chữ tiêu chí phục hồi (chưa có số trong spec) | biên bản nhóm |
| `workload.*` | profile, mix payload, warmup, phần cứng tham chiếu | meta sidecar |
| `approved`, `approved_by`, `approved_date` | `true`, danh sách người ký, ngày | chữ ký nhóm |

4. Kiểm: `python -m scripts.check_performance --sidecar <jsonl> --slo docs/performance/slo.json --scope load|soak|recovery [--rss rss.json]`.

Scope `soak` đòi `--rss` dạng `{"rss_after_warmup_mb": <số>, "rss_end_mb": <số>}` (định dạng này là giả định, chờ Quang xác nhận). Scope `recovery` chỉ xét p95 và tỉ lệ lỗi.

## Chuẩn bị lượt đo lại G06–G09 (#132)

[Issue #132](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/132)
vẫn cần lượt đo chính thức trên server riêng, client **khác phần cứng vật lý**.
Hạn Lực cập nhật là **hết ngày 17/11/2026**, thay mốc dự kiến 20/11 trong mô tả issue.
Payload điện thoại Loan đã chuẩn bị không có nghĩa lượt đo đã chạy.

Trước lượt đo, ghi vào biên bản:

- Server Linux x86_64, ≥ 4 nhân, **≥ 3 GiB RAM trống tại lúc chuẩn bị**, Docker hoạt động;
  CPU/RAM tổng và khả dụng, đĩa trống, Engine/Compose, giới hạn container thực tế.
  VPS 2 nhân/1,9 GiB ở #42 có phạm vi nhóm duyệt là chức năng/rollback, không dùng
  cho lượt load/SLO/stress/soak/recovery nghiệm thu này.
- Máy client, cách kết nối gateway, xác nhận khác máy vật lý; nếu qua SSH tunnel,
  ghi overhead và việc limiter nhìn thấy cùng một IP. Không giả `X-Forwarded-For`.
- Commit/image/model/config hash, SLO đã duyệt và hash file trước khi chạy.
  SLO cũ: 2 user, p95 ≤ 400 ms, RPS 200 ≥ 0,6, lỗi không tính 429 ≤ 8%, RSS tăng ≤ 20%.
  Nếu cần SLO mới theo phần cứng, chờ duyệt **trước** lượt đo; không sửa theo kết quả.
- Đủ hai gói ZIP và checksum, hai manifest gốc và kết quả kiểm từng ảnh theo
  [hướng dẫn ghép payload](../../locust/README.md#ghép-payload-điện-thoại-cho-132).
  Ghi hash, số ảnh/byte mỗi nhóm và mix Lực chốt; `40/30/30` chưa là quyết định.

Trình tự: baseline/load → stress (ghi từng bậc) → recovery **sau stress trên cùng server**
theo [quy trình G09](#quy-trình-recovery-g09-130) → soak 2 user, 30 phút kèm
`scripts.soak_rss`. Mỗi lượt/bậc có sidecar, HTML/CSV Locust và mốc thời gian riêng;
không ghi đè lượt không đạt. Thu RSS từ server trong cửa sổ soak, không lấy RAM trống
của máy làm RSS container. Chạy `check_performance` từng scope `load`, `recovery`,
`soak` (kèm `--rss`); stress không có scope chấm SLO. Lưu exit code và output nguyên văn.

Báo cáo cần so với bản 14/11 (48 ảnh tổng hợp, cùng máy vật lý, không stress), và bản
GenImage 15/11 (200 ảnh gốc, gồm thật và AI, vẫn cùng máy và chưa stress). Ghi cả lượt không đạt,
ảnh hưởng đường truyền, giới hạn ảnh Photos xuất và định dạng lẫn nhãn. Chạy lại
`check_mvp_gates` trên bộ bằng chứng G06–G09 đầy đủ; nếu chưa có server hoặc chưa nhận
gói, ghi rõ **chưa làm / lý do / khi nào có thể tiếp tục**, giữ #132 mở.

[Lượt thăm dò riêng 16/11](../reports/vps-load-probe-20261116.md) chạy 2 user/60 s
trên VPS theo yêu cầu trực tiếp trong phiên làm việc, với ảnh tổng hợp và guard tài nguyên.
Ghi tách khỏi bằng chứng nghiệm thu; không thay phạm vi nhóm đã duyệt hoặc điều kiện #132.

## Quy trình recovery (G09, #130)

Mục đích: lượt recovery lặp lại được, và báo riêng phần gián đoạn. Không sửa ngưỡng SLO. Lượt 1 (không đạt, 23 mẫu sau warmup 70 s) và lượt 2 (đạt, 131 mẫu) ngày 14/11 giữ nguyên trong báo cáo; lượt theo quy trình này là **lượt 3**. Chạy từ máy đo, Compose ở gốc repo, cổng gateway `<gw>` (ví dụ `http://localhost`).

### 1. Cấu hình
`locust/recovery.conf` (1 user, kịch bản `recovery`) với **thời lượng tối thiểu 10 phút** (`-t 10m` ghi đè `run-time = 2m` của file conf). Giữ nguyên `slo.json`.

### 2. Thứ tự thao tác và file log
Mọi mốc ghi vào `artifacts/recovery-run3/timeline.log`, mỗi dòng gồm epoch (giây, 3 số lẻ) và giờ UTC+7:
```bash
mkdir -p artifacts/recovery-run3 && L=artifacts/recovery-run3/timeline.log
ts() { echo "$(date +%s.%3N) $(TZ=Asia/Ho_Chi_Minh date +%T.%3N) $*" | tee -a "$L"; }
CID=$(docker compose ps -aq api)
docker inspect -f 'StopTimeout={{.Config.StopTimeout}}' "$CID" | tee -a "$L"   # <no value> nghĩa là mặc định 10 s của Docker

T0=$(date -u +%Y-%m-%dT%H:%M:%SZ); ts "T0 bắt đầu Locust"
docker events --since "$T0" --format '{{json .}}' > artifacts/recovery-run3/events.jsonl &   # chạy suốt lượt, tắt cuối lượt
EV=$!
RC_PAYLOAD_DIR=<payload> RC_SIDECAR=artifacts/recovery-run3/recovery.jsonl \
  locust --config locust/recovery.conf -t 10m --host http://<gw> &
LP=$!

sleep 60
ts "lệnh docker compose stop api"; docker compose stop api; ts "stop api trả về"
docker inspect -f 'ExitCode={{.State.ExitCode}} FinishedAt={{.State.FinishedAt}}' "$CID" | tee -a "$L"
sleep 20                                  # giữ API tắt 20 s tính từ lúc stop trả về
ts "lệnh docker compose start api"; docker compose start api
until [ "$(curl -s -o /dev/null -w '%{http_code}' http://<gw>/health)" = 200 ]; do sleep 1; done
ts "/health 200 lần đầu"                  # giờ này là T_ok
wait $LP; kill $EV                        # đợi Locust hết 10 phút
```
Giờ container dừng thật là `FinishedAt` của `docker inspect` (và sự kiện `die` trong `events.jsonl`); mốc "stop api trả về" cho thấy lệnh mất bao lâu. Ghi cả `ExitCode` (143 = SIGTERM xử lý; 137 = bị SIGKILL sau hết `StopTimeout`).

### 3. Cửa sổ đo và `--warmup-seconds`
- **Cửa sổ đo** bắt đầu **60 s sau** `/health 200` lần đầu (T_ok + 60 s). Phần trước đó (gồm lúc gián đoạn) vẫn lưu trong sidecar và **báo riêng**: số 200, 502, 503, 504, other, và thời gian gián đoạn từ lệnh stop tới 200 đầu tiên của Locust.
- `perf_report` và `check_performance` tính warmup **từ request đầu của sidecar** (`start = request đầu`, bỏ request có `t < start + warmup_seconds`), nên đặt:
  `warmup_seconds = (T_ok + 60) - t_first`, với `t_first` là `t` của dòng `req` đầu tiên trong `recovery.jsonl` và `T_ok` là epoch ở dòng "/health 200" của `timeline.log`.
```bash
python - <<'PY'
import json
from scripts.perf_report import load_sidecar
_, recs = load_sidecar("artifacts/recovery-run3/recovery.jsonl")
t_first = min(r["t"] for r in recs)
t_ok = float(next(l.split()[0] for l in open("artifacts/recovery-run3/timeline.log") if "/health 200" in l))
print("warmup_seconds =", round(t_ok + 60 - t_first, 1))
PY
python -m scripts.perf_report artifacts/recovery-run3/recovery.jsonl --warmup-seconds <N> --output artifacts/recovery-run3/recovery-report.json
python -m scripts.check_performance --sidecar artifacts/recovery-run3/recovery.jsonl --slo docs/performance/slo.json --scope recovery --warmup-seconds <N>
```
Phần gián đoạn (trước cửa sổ đo): chạy lại `summarize` với `--warmup-seconds 0` trên bản lọc `t < T_ok + 60`:
```bash
python - <<'PY'
import json
from scripts.perf_report import load_sidecar, summarize
meta, recs = load_sidecar("artifacts/recovery-run3/recovery.jsonl")
t_ok = float(next(l.split()[0] for l in open("artifacts/recovery-run3/timeline.log") if "/health 200" in l))
print(json.dumps(summarize(meta, [r for r in recs if r["t"] < t_ok + 60], 0)["counts"]))
PY
```
Ghi giá trị `N` đã dùng vào báo cáo.

**`check_mvp_gates` không có cờ `--warmup-seconds`.** Nó (qua `check_performance.run`) đọc warmup từ **meta của sidecar gốc** (`warmup_seconds`, ghi lúc chạy Locust bằng `RC_WARMUP_SECONDS`, mặc định 0). `N` chỉ biết sau khi có `T_ok`, nên nếu Locust chạy với meta 0 thì `check_mvp_gates` tính **cả phần gián đoạn**: lượt 3 cho lỗi 0,0842 > 0,08 nên G09 "chưa đạt", trong khi `check_performance --warmup-seconds 171.4` đạt. Hai kết quả khác nhau do cách đọc warmup, không do số đo.

- **Bằng chứng cho G09 khi có gián đoạn:** dùng `check_performance --scope recovery --warmup-seconds N` (lệnh ở trên) và ghi rõ trong báo cáo rằng `check_mvp_gates` đọc sidecar gốc nên có thể báo khác.
- **Không sửa sidecar sau khi chạy** (kể cả chỉ dòng meta, kể cả giữ bản gốc): làm thay đổi bằng chứng.
- **Lần chạy sau:** đặt `RC_WARMUP_SECONDS` bằng giá trị biết trước khi chạy Locust (ví dụ ước lượng thời gian từ lệnh stop tới `/health` 200 cộng 60 s; ước lượng này tính từ request đầu, tức cộng cả 60 s trước khi stop), để meta đúng ngay từ đầu và `check_mvp_gates` đọc cùng cửa sổ. Vẫn tính `N` chính xác bằng quy trình trên để **kiểm tra** (không để thay meta); lệch nhiều thì báo cả hai.

### 4. Tiêu chí hợp lệ
- Cửa sổ đo phải có **tối thiểu 100 request 200** (`counts["200"]` của `perf_report` sau warmup). Ít hơn thì lượt **không hợp lệ**: ghi rõ "không hợp lệ", **không** tính đạt hay không đạt, rồi kéo dài `-t` và chạy lại. Với 1 user và think time 1 đến 3 s, 8 phút chỉ dư một chút so với 100 mẫu (xem ước lượng lúc chạy); thiếu mẫu thì kéo dài, đừng giảm yêu cầu.
- **Một lần mỗi lần công bố.** Không chọn lượt đẹp. Có chạy lại thì báo **cả hai** kết quả và nêu lý do (ví dụ lượt không hợp lệ vì thiếu mẫu).
- Kết quả không đạt vẫn ghi nguyên; không nới SLO để cho đạt.

### 5. Ghi vào báo cáo
Lượt 1 (không đạt) và lượt 2 (đạt) giữ nguyên; lượt 3 ghi thêm: `timeline.log`, `events.jsonl`, `FinishedAt` và `ExitCode`, thời gian từ lệnh stop tới 200 đầu tiên, `warmup_seconds` đã dùng, số 200 trong cửa sổ, hash SHA256 các file (xem [`docs/qa/gate-evidence.md`](../qa/gate-evidence.md)). Thời gian dừng container (20 s so với 4 s) nếu chưa có nguyên nhân thì ghi "chưa rõ" (Quang điều tra).
