# Kiểm bổ sung VPS từ máy Kiệt — 15/11/2026

Người chạy: Kiệt, với Codex hỗ trợ. Liên quan KAN-55 / #42 đã đóng và #132 còn mở. Đây là kiểm chức năng từ máy khác, bổ sung cho lần Quang deploy; **không phải kiểm độc lập model/dữ liệu, benchmark hoặc nghiệm thu G07–G09**. [JSON kết quả](vps-functional-followup-20261115.json).

## Kết luận và phạm vi

Server đã chạy RealCheck trước lượt này; không cần deploy lại. `/health` 200, API/UI healthy, model e571 đúng SHA256. 13 request nhỏ qua SSH tunnel đạt các mã phản hồi và schema mong đợi. Kiểm gateway giới hạn có một ca đạt và một ca lỗi `WriteTimeout`; upstream tắt/bật cố ý bỏ qua, nên chưa đủ bằng chứng G04 đầy đủ. Không sửa production code, image, model, Compose, tag, firewall hoặc khởi động lại service trên VPS.

Quyết định của Lực ở [#42](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/42#issuecomment-6883484187) cho phép VPS này dùng kiểm chức năng/rollback, không đo tải/SLO. #132 vẫn cần server đủ cấu hình, client khác máy, stress rồi recovery và soak. Hạn [cập nhật](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/132#issuecomment-6895240098): hết ngày 17/11/2026.

## Máy và phiên bản

| Mục | Quan sát thật |
|---|---|
| Server | VPS KVM, 2 CPU khả dụng; Ubuntu 24.04.3 x86_64 |
| RAM server | 1.967 MiB tổng, không swap; available 498 MiB ở preflight, 511 MiB ở postflight |
| Đĩa server | 27 GB trống trên `/` |
| Docker / Compose | Engine 29.9.2 / Compose v5.6.1 |
| Source/image server | `9c8162f6e9150ff0edbd6ff1c56033c9dacaa799`; API/UI tag `9c8162f`; repo clean trước/sau |
| Model | `clip_probe_e571.joblib`, SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494` |
| Giới hạn API / UI / Nginx | 1,5 CPU / 900 MiB; 0,5 CPU / 256 MiB; 0,25 CPU / 64 MiB |
| Truy cập | Server gateway `127.0.0.1:8090`; client `127.0.0.1:18090` qua SSH tunnel, không mở public |
| Client kiểm | Windows 11 Home; Intel Core i7-14650HX, 16 nhân / 24 luồng; RAM tổng 15,612 GiB, available 1,043 GiB lúc đọc cấu hình; đĩa C trống 185,267 GiB |
| Source validator client | `a70e4b60c9c628b0e2a0826d0b1e9bc79dfb2870` trong checkout riêng |

Máy cá nhân có CPU đủ nhưng Docker CLI chưa có ở PATH hay vị trí Docker Desktop thông thường; WSL mặc định Ubuntu/WSL2 đã được ghi nhận, **chưa kiểm Docker daemon trong WSL**. RAM khả dụng lúc kiểm dưới 3 GiB, nên chưa đề xuất đây là server sẵn sàng đo #132. Khả năng nối LAN với một client khác chưa xác minh. Kết nối SSH từ client tới VPS đã hoạt động; không phải xác nhận đường mạng cần cho benchmark.

## Request chức năng nhỏ

Thời gian 21:39:15–21:39:37 UTC+7. Gửi tuần tự, nghỉ 0,5 giây giữa request, không POST retry. Wrapper hỗ trợ gọi HTTP và dùng `schema_problems`/`error_problems` có sẵn trong `scripts.smoke_api` để kiểm schema. Đây là một tập con chọn rõ, không phải chạy toàn bộ CLI `smoke_api` hoặc báo "26/26".

| Ca | HTTP thật | Kết quả |
|---|---|---|
| `/health`, `/docs`, HTML `/`, `/_stcore/health` | 200 từng ca | 4/4 |
| PNG tổng hợp hợp lệ, JPEG real GenImage, PNG GLIDE | 200 + schema | 3/3 |
| File rỗng, text giả JPEG | 400 `EMPTY_FILE`, 400 `INVALID_IMAGE` | 2/2 |
| Ảnh 200×200, thiếu trường file | 422 `IMAGE_TOO_SMALL`, 422 `MISSING_FILE` | 2/2 |
| GET vào analyze, đường dẫn lạ dưới `/v1/` | 405 `METHOD_NOT_ALLOWED`, 404 `NOT_FOUND` | 2/2 |

Các file nhỏ lấy từ fixture tổng hợp có sẵn và gói GenImage #123. JSON giữ hash file và request ID, không chứa ảnh cá nhân. Verdict/score của hai ảnh GenImage chỉ được ghi nhận, không phải phép đo accuracy. Không thử ảnh 12 MP, biên 5 MiB, load hoặc stress trong tập này.

## Gateway: giữ nguyên ca chưa đạt

Lệnh từ checkout validator trên máy client:

```bash
python -m scripts.check_gateway --base-url http://127.0.0.1:18090 \
  --fixture <fixtures>/ok_valid.png --rate 10 --burst 10 \
  --upstream skip --only under body \
  --out <output>/gateway-limited.json --junit <output>/gateway-limited.xml
```

- `under`: 3/3 request trả 200 + X-Request-ID, ca đạt.
- `body`: file 6.291.456 B bị client `WriteTimeout`, ca lỗi; CLI exit **1**. Không gọi lại cùng checker để chọn một kết quả xanh.
- `rate`, `boundary` không được chọn. Upstream/recovery bỏ qua bằng `--upstream skip`; JUnit có skipped và failure, không được lấy làm G04 đạt.

Đối chiếu log Nginx tại 21:40:13–21:40:43 UTC+7: gateway ghi `client intended to send too large body: 6291630 bytes` (gồm multipart), rồi access log **413**, `upstream_time=-`, request ID `b2ce8e5c-9deb-35f4-ccaa-79d4674ad3ee`. Điều này xác nhận Nginx có chặn request, nhưng **không thay thế việc client nhận được envelope**; ca checker vẫn lỗi. Chưa kết luận nguyên nhân gốc ở mạng, SSH, thư viện client hay cấu hình gateway.

Một phép chẩn đoán riêng với `curl 8.22.0`, HTTP/1.1 và `Expect: 100-continue`:

```bash
curl --http1.1 --max-time 20 --expect100-timeout 5 \
  -H 'Expect: 100-continue' -F 'file=@<file-6-MiB>;type=image/jpeg' \
  --dump-header headers.txt --output body.json \
  --write-out 'http_code=%{http_code} upload_bytes=%{size_upload}\n' \
  http://127.0.0.1:18090/v1/analyze
```

Nhận **413**, body JSON `FILE_TOO_LARGE` đúng tiếng Việt và X-Request-ID khớp body; `upload_bytes=0`: Nginx từ chối theo Content-Length trước khi client gửi nội dung file. Đây chỉ là chẩn đoán nhánh từ chối sớm, không phải kiểm đường truyền toàn bộ 6 MiB hoặc thay kết quả checker. Không dùng thời gian request này làm SLO.

## Theo dõi tài nguyên và việc còn thiếu

- Bộ lấy mẫu read-only đọc `/proc/meminfo` mỗi giây, 600 mẫu trong cửa sổ chức năng/gateway; MemAvailable thấp nhất **490,402 MiB**, không chạm ngưỡng dừng bảo thủ 400 MiB. Đây là theo dõi an toàn khi kiểm chức năng, **không phải soak 30 phút/RSS của API**. File raw giữ ngoài Git, JSON ghi hash và tóm tắt. Không có samples phủ toàn bộ thời gian dành cho quyền điều khiển trình duyệt và viết báo cáo.
- Số restart API/UI/Nginx trước và sau là **0/2/0**, không tăng. `OOMKilled=false` ở cả hai snapshot; không suy ra lịch sử toàn máy chưa từng OOM. Hai restart UI đã có từ trước lượt kiểm, chưa điều tra nguyên nhân.
- Repo trên VPS giữ nguyên commit và clean; không tác động ba container của dịch vụ khác. Bộ lấy mẫu tự kết thúc sau 600 mẫu.
- `artifacts/evaluation.json` chưa có; UI báo chưa có số đo là trạng thái dự kiến. Không chép kết quả cũ của người train để thay QA G03.
- Trình duyệt: bước xin quyền điều khiển Edge hết thời gian chờ, nên **chưa kiểm lại thao tác tải ảnh/WebSocket/biên 5 MiB bằng trình duyệt** trong lượt này. HTTP 200 của HTML/UI health không chứng minh các thao tác đó. Biên bản của Quang vẫn là nguồn cho lần kiểm UI trước.
- Không build, deploy lại, diễn tập rollback, tắt API, đo Locust/SLO, stress, recovery hoặc soak. Chưa có server đủ điều kiện cho #132; chưa xác nhận thời hạn mượn VPS. Không tự đóng #132 hoặc xác nhận release đạt.
