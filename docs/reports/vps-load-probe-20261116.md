# Thăm dò tải VPS từ máy Kiệt, 16/11/2026 (#132)

Kiệt chạy **một lượt 2 user, 60 giây** theo yêu cầu trực tiếp trong phiên làm việc,
bắt đầu **21:48:13 UTC+7 ngày 16/11**. Đây là khảo sát riêng, không thay quyết định
của Lực ở #42 về phạm vi VPS và không phải bằng chứng nghiệm thu G07–G09.
Kết quả giữ nguyên, kể cả lỗi; chưa chạy `check_performance` hoặc sửa SLO.

## Máy và cách chạy

- VPS: Ubuntu 24.04.3 LTS x86_64, Xeon E5-2696 v4, **2 vCPU, 1.922 GiB RAM**, không swap;
  Docker Engine 29.9.2, Compose 5.6.1; còn khoảng 26,4 GiB đĩa. Có 3 container dịch vụ khác.
- Giữ nguyên deploy: `realcheck-api:9c8162f`, API **1,5 CPU / 900 MiB**;
  UI 0,5 CPU / 256 MiB; Nginx 0,25 CPU / 64 MiB. Image ID API ghi trong JSON.
  Không build, deploy, restart, đổi slot, model, Nginx hoặc giới hạn tài nguyên.
- Client Windows 11 **khác máy vật lý**, Locust 2.47.0, SSH tunnel tới gateway loopback.
  Loader từ base `496a238` với thay đổi chưa commit trong PR này (`dirty=true`, hash trong JSON).
  **Pytest đang chạy đồng thời trên client**: chưa loại trừ client bottleneck.
- Chưa có gói GenImage/phone tại máy chạy lượt này. Dùng **4 ảnh noise tổng hợp**
  (2 JPEG, 2 PNG), 512×512 và 1024×768, 158.118–2.361.744 byte, mix nhóm 50/50.
  Hash, kích thước và chiều ảnh nằm trong JSON. Không có ảnh cá nhân; không đo accuracy.
- 2 user, spawn 1/s, wait 1–3 s; warmup **10 s**. Đây là profile khảo sát,
  khác profile nghiệm thu 5 phút/warmup 30 s. Thời gian gồm truyền ảnh và SSH tunnel.
- Tự dừng client nếu host `MemAvailable` <400 MiB hoặc API `memory.current` >810 MiB
  (90% giới hạn). Không chạm dịch vụ khác; không giả `X-Forwarded-For`.

Lệnh Locust (tunnel chỉ nghe localhost, `<payload>` là thư mục ảnh tổng hợp đã mô tả):

```bash
RC_PAYLOAD_DIR=<payload> RC_MIX=jpeg=50,png=50 RC_WARMUP_SECONDS=10 \
RC_SIDECAR=<out>/load.jsonl \
python -m locust -f locust/locustfile.py --headless --rc-scenario baseline \
  --users 2 --spawn-rate 1 --run-time 60s --stop-timeout 5 --only-summary \
  --host http://127.0.0.1:<tunnel-port> --csv <out>/locust --html <out>/locust.html
```

Đây chỉ là lệnh tái lập profile; lần thực tế có guard đọc RAM/cgroup qua SSH khoảng
2 giây/lần. Không chạy lại trên VPS dùng chung chỉ để tìm số đẹp.

## Kết quả thật

| Chỉ số | Toàn lượt | Sau warmup 10 s |
|---|---:|---:|
| Request hoàn tất | 51 | 41 |
| HTTP 200 đúng schema | 44 | 35 |
| HTTP 503 `SERVICE_BUSY` | 7 | 6 |
| HTTP 429 / 504 / lỗi khác | 0 / 0 / 0 | 0 / 0 / 0 |
| p95 riêng 200 | xem JSON | **657,808 ms** |
| RPS 200 | xem JSON | **0,709686** |
| Lỗi không tính 429 | 13,725% | **14,634%** |

Locust **exit 1**, chạy hết thời lượng, không bị guard dừng. Cửa sổ sau warmup là
49,318 s; 10 request warmup được bỏ. So số với ngưỡng MVP cũ thì p95 >400 ms và lỗi
>8%; không gọi đây là kết luận SLO vì phần cứng, nguồn payload, thời lượng và client
chưa đúng điều kiện của #132. `SERVICE_BUSY` cho thấy admission đã từ chối một số
request đồng thời; lượt này không xác định riêng nút thắt CPU hay đường truyền.

31 snapshot tài nguyên (trước lượt và trong lúc chạy):

- Host `MemAvailable`: trước **514,398 MiB**, thấp nhất **504,313 MiB**, sau **519,180 MiB**.
- API cgroup `memory.current`: trước **672,965 MiB**, lớn nhất/sau **778,332 MiB**.
  Bao gồm cache/bộ nhớ kernel, **không phải process RSS**, không dùng để chấm RSS +20%.
- `/health`: **200 trước và sau**; API/UI healthy. ID, PID, state, restart count và OOM flag
  của cả 6 container giữ nguyên. Restart API/UI/Nginx vẫn **0/2/0**; UI có 2 restart từ trước.

## Bằng chứng và phần còn lại

- [JSON kết quả](vps-load-probe-20261116.json): cấu hình, inventory/hash ảnh tổng hợp,
  số đo cả lượt/sau warmup, tài nguyên và giới hạn. Không chứa IP hoặc thông tin đăng nhập.
- [Sidecar request gốc](vps-load-probe-20261116.jsonl), SHA256
  `84e9c340efc29b8c9d2babc9294860d59a2ef45387c81439261a4a2671c09a08`.
  `.gitattributes` giữ nguyên CRLF của riêng file này để checkout không đổi hash.
  Đã đối chiếu **51/51** dòng request có đường dẫn nhóm/hash/kích thước khớp ảnh gửi.
  HTML, CSV định kỳ, log Locust và snapshot chi tiết giữ cục bộ; số trong báo cáo lấy từ sidecar.

Reviewer tính lại bằng:

```bash
python -m scripts.perf_report docs/reports/vps-load-probe-20261116.jsonl
python -m scripts.perf_report docs/reports/vps-load-probe-20261116.jsonl --warmup-seconds 0
```

VPS sẵn Docker và RealCheck nên thuận tiện kiểm chức năng hơn máy Kiệt hiện tại;
**cả hai vẫn chưa đủ điều kiện làm server #132**. Máy Kiệt được đọc trước lượt:
RAM trống khoảng 0,851 GiB, WSL Ubuntu chưa có Docker CLI. Chưa chạy A/B cùng workload
trên máy Kiệt nên không kết luận VPS có hiệu năng tốt hơn máy cá nhân.

Chưa làm: gói phone thật của Loan, xác minh lại model/config hash trong lượt này,
stress, recovery, soak 30 phút/RSS và lượt G06–G09 trên máy ≥4 nhân/≥3 GiB RAM trống.
Tiếp tục khi có server được Lực chốt và người đo nhận đủ hai gói payload; giữ #132 mở.
