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
