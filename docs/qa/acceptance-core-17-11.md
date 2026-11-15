# Biên bản nghiệm thu core (M2), mục tiêu 17/11/2026: MẪU, CHƯA ĐIỀN SỐ

Sao chép thành `docs/qa/acceptance-core-<ngày>.md` rồi điền khi đã có số. **Mọi ô `___` trong file này là chưa điền; không suy ra từ báo cáo cũ.** Lệnh từng cổng nằm ở [`gate-evidence.md`](gate-evidence.md), mẫu biên bản tích hợp ở [`integration-report-template.md`](integration-report-template.md), SLO và quy trình recovery ở [`../performance/README.md`](../performance/README.md); file này không nhắc lại. Bằng chứng nằm ngoài Git (ổ chia sẻ hoặc release); biên bản trong Git chỉ có bảng và hash.

## 1. Thông tin chung

| Mục | Giá trị |
|---|---|
| Commit chốt `C` (hash đầy đủ, `git rev-parse origin/main`) | ___ |
| Worktree sạch (`git status` rỗng) | ___ |
| Ngày giờ bắt đầu, kết thúc (UTC+7) | ___ |
| Python, Pillow, `pip freeze`, `python -m models.run_info` | ___ |
| Model: tệp, SHA256 | ___ |
| `slo.json` ngoài Git: SHA256, `approved_by`, `approved_date` | ___ |
| Người chạy tổng (`check_mvp_gates`) | ___ |
| Nơi lưu bằng chứng, `SHA256SUMS`, `COMMIT.txt` | ___ |

Phân biệt người **viết**, người **chạy**, người **tính lại**; số tự đo ghi là tự đo.

## 2. Bảng 9 cổng

Kết quả chỉ ghi "Đạt", "Chưa đạt" hoặc "Thiếu bằng chứng" theo đầu ra của `check_mvp_gates`. Bằng chứng lấy từ commit khác `C` thì ghi hash đó ở cột commit, không gọi là "tất cả trên một commit".

| Cổng | Kết quả | Số đo | File bằng chứng + SHA256 | Commit / máy | Người chạy | Giới hạn |
|---|---|---|---|---|---|---|
| G01 unit, coverage | ___ | ___ test, ___ skip, coverage `app/` ___% | `unit.xml`, `coverage.xml`: ___ | ___ | ___ | ___ |
| G02 audit metadata | ___ | A_eff ___ ; số đặc trưng hằng số ___ | `metadata-audit.json`: ___ | ___ | ___ | ___ |
| G03 accuracy GenImage test | ___ | accuracy ___ trên n = ___ | `evaluation.json`: ___ | ___ | ___ | QA độc lập: có / chưa (___) |
| G04 gateway, phục hồi | ___ | ___ ca đạt / ___ | `integration.xml`: ___ | ___ | ___ | ___ |
| G05 UI qua gateway | ___ | ___ ca đạt / ___ | `ui-gateway.xml`: ___ | ___ | ___ | ___ |
| G06 SLO đã ký | ___ | p95 ≤ ___ ms; RPS ≥ ___; lỗi ≤ ___; RSS ≤ ___% | `slo.json` (ngoài Git): ___ | ___ | ___ | ___ |
| G07 tải | ___ | p95 ___ ms; RPS ___; lỗi ___ | `load.jsonl`: ___ | ___ | ___ | ___ |
| G08 soak, RSS | ___ | p95 ___ ms; lỗi ___; RSS tăng ___% | `soak.jsonl`, `soak-rss.json`: ___ | ___ | ___ | ___ |
| G09 phục hồi | ___ | p95 ___ ms; lỗi ___; warmup ___ s | `recovery.jsonl`: ___ | ___ | ___ | ___ |

Lượt đo thất bại giữ lại và ghi cả hai (không chạy lại để "được xanh"): ___

## 3. Kết luận (một dòng)

Chọn một, xóa dòng kia:

- Core đạt 9/9 (`python -m scripts.check_mvp_gates` thoát 0 ở commit `___`).
- Core chưa đạt: G___, G___ (lý do: ___).

Đầu ra nguyên văn của `check_mvp_gates`: dán vào mục 7.

## 4. Giới hạn đã biết

Ghi lại nguyên văn từ [`gate-evidence.md`](gate-evidence.md) và các báo cáo, điền số của lượt này; xóa dòng không còn đúng, không thêm lời khẳng định chưa có bằng chứng.

- Ảnh thật chụp bằng điện thoại: ___ / ___ bị gọi là AI (cohort ADV-06 trước đó: 64/76).
- G03: ___ (có hay chưa có QA độc lập; ngưỡng nào, tập nào).
- Đo tải trên máy ___ với client ___; số hơi lạc quan nếu cùng phần cứng. VPS không đo tải.
- Soak ___ phút không chứng minh không rò bộ nhớ dài hạn.
- 503 `SERVICE_BUSY` tính là lỗi trong ngân sách lỗi.
- ___

## 5. Việc còn lại sau nghiệm thu

| Việc | Người | Hạn |
|---|---|---|
| ___ | ___ | ___ |

## 6. Chữ ký

| Vai trò | Họ tên | Ngày |
|---|---|---|
| Người chạy cổng | ___ | ___ |
| Người tính lại / kiểm (khác người chạy) | ___ | ___ |
| Lực (duyệt) | ___ | ___ |

## 7. Đầu ra `check_mvp_gates` và `SHA256SUMS`

```text
___
```
