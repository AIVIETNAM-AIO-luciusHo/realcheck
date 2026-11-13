# Quyết định kỹ thuật RealCheck

Ghi các mục D01–D14 của `specs/000-realcheck-system-baseline/spec.md` (mục 11), cùng hợp đồng `score`, manifest và phạm vi nghiệm thu (MVP-01). Phần API do Quang phụ trách; lựa chọn D08 của Kiệt ở [ml-selection.md](ml-selection.md).

Trạng thái: `proposed` (đề xuất, chờ review), `approved` (nhóm đã duyệt) hoặc `approved tạm` (đã duyệt để dùng, xem lại sau benchmark). Mục `proposed` có thể đổi khi review PR. Ghi một lựa chọn vào file này **không** làm nó thành `approved`: chỉ đổi trạng thái khi có người duyệt, ngày và lý do.

## Bảng trạng thái

| Mục | Trạng thái | Người quyết định | Reviewer | Ngày | Còn chờ |
|---|---|---|---|---|---|
| D01 Split, seed | Chưa ghi quyết định | Loan | — | — | Loan chốt; hiện trạng ở [mục D01–D04](#d01d04-dữ-liệu-và-audit) |
| D02 Chuẩn hóa | Một phần đã chốt trong spec 001 | Kiệt | — | — | [Đã ghi hiện trạng alpha/ICC/subsampling](ml-api-handoff-39.md#d02-hành-vi-version-1-hiện-có); chờ review |
| D03 Probe metadata | Chưa ghi quyết định | Loan | Kiệt, Lực | — | Loan chốt probe |
| D04 Protocol audit | Chưa ghi quyết định | Loan | Lực | — | Loan chốt protocol, tách khỏi model-test |
| D05 Enum và lỗi API | approved | Quang | Lực | 2026-11-04 | Loan xác nhận cho UI |
| D05 Lỗi gateway | approved (Lực, 2026-11-12) | Quang | Lực | 2026-11-12 | Loan đã xác nhận UI (2026-11-13): UI chọn thông báo theo mã HTTP, thêm 502; `app/schemas.py` đã thêm `RATE_LIMITED`, `API_UNAVAILABLE`, `GATEWAY_TIMEOUT` (2026-11-13), `tests/test_gateway_error_codes.py` khóa câu chữ khớp `nginx.conf` |
| D05 Làm rõ 5 câu (issue #43) | proposed; Quang đã chọn | Quang | Chờ Lực | 2026-11-11 | Lực review và khóa bằng test; xem [mục Làm rõ](#làm-rõ-issue-43) |
| D06 Dung lượng file | approved | Quang | Lực | 2026-11-04 | — |
| D06 Body dư multipart | approved (Lực, 2026-11-12) | Quang | Lực | 2026-11-12 | 64 KiB (`client_max_body_size 5184k`) |
| D07 Số pixel | approved | Quang | Lực | 2026-11-04 | — |
| D08 Ngưỡng | approved cho MVP (Lực, 2026-11-12): 0.3/0.5/0.7 | Kiệt | Lực/Loan | 2026-11-12 | Không phải duyệt release: 94,53% chỉ trên 384 ảnh test đã lọc, chưa duyệt độc lập, chưa loại trừ shortcut |
| D09 p95 | Hoãn (Lực, 2026-11-12) | Lực | — | — | Chốt sau khi đo trên máy lab; baseline sơ bộ trên máy cá nhân không đủ |
| D10 RPS, error budget, RSS | Hoãn (Lực, 2026-11-12) | Lực | — | — | Chốt sau khi đo trên máy lab |
| D11 Timeout | approved tạm, xem lại sau benchmark | Quang | Lực | 2026-11-04 | Xem lại sau benchmark MVP-09 |
| D12 Cơ chế suy luận | approved tạm, xem lại sau benchmark | Quang | Lực | 2026-11-04 | Xem lại sau benchmark MVP-09 |
| D13 Truy cập, rate limit | approved (Lực, 2026-11-12), sửa quyết định 10/11 | Quang | Lực | 2026-11-12 | Mạng lab nội bộ dùng HTTP; truy cập từ ngoài bắt buộc SSH tunnel; ngoài Internet cần TLS và quyết định mới |
| D14 Profile tải | Hoãn (Lực, 2026-11-12) | Lực | — | — | Chốt cùng D09, D10 sau khi đo trên lab; `locust/baseline.conf` (5 người dùng) chỉ là đề xuất |
| Hợp đồng `score` | approved (Lực, 2026-11-12) | Quang | Lực | 2026-11-12 | [Xác nhận ML](ml-api-handoff-39.md#hợp-đồng-score-xác-nhận-kỹ-thuật-ml), [kiểm trên máy API](#kiểm-trên-máy-api-issue-39); đã duyệt chung ngày 12/11 |
| Model phục vụ API (local/lab) | Kiệt chọn reference e571; Quang đã nhận và kiểm trên máy API | Kiệt | Quang (nhận), chờ Lực | 2026-11-11 | Không phải phê duyệt QA hay release; **bắt buộc đặt `REALCHECK_MODEL_PATH`** (mặc định trong mã vẫn là model cũ `69810fd6`, không đổi); xem [mục Kiểm trên máy API](#kiểm-trên-máy-api-issue-39) |
| Manifest phục vụ model | approved (Lực, 2026-11-12): bộ 9.708 ảnh giữ split, `data/labels.csv` (PR #83) | Loan | Kiệt, Lực | 2026-11-12 | Loan xác nhận; SHA256 sau khi đổi tiền tố đường dẫn và kiểu xuống dòng khớp manifest e571 (`4bf8e490…`), QA đã kiểm; xem [mục Manifest](#manifest) |
| Chính sách audit | approved (Lực, 2026-11-12): `metadata_audit.py` cảnh báo, release checker riêng chặn post `A_eff > 0.55` | Loan, Lực | Quang tổng hợp | 2026-11-12 | Loan xác nhận; mã `metadata_audit.py` chưa đổi (vẫn cổng cứng); xem [mục Xung đột audit](#xung-đột-audit-spec-000-và-spec-001) |
| Phạm vi M1/M2 | approved (Lực, 2026-11-12); Loan, Kiệt chưa xác nhận | Quang | Lực | 2026-11-12 | Xem [mục Phạm vi nghiệm thu](#phạm-vi-nghiệm-thu-m1-và-m2) |

## D05. Enum `verdict` và lỗi

**Lựa chọn:** `likely_real` / `uncertain` / `likely_ai` (phương án A).

**Lý do:** ba giá trị cùng kiểu; `likely_real` không khẳng định chắc chắn ảnh là thật, đúng yêu cầu không tuyên bố chính xác 100%.

Lỗi trả envelope riêng, kể cả lỗi validation của framework:

```json
{
  "error": {
    "code": "IMAGE_TOO_SMALL",
    "message": "Ảnh quá nhỏ. Cạnh ngắn tối thiểu 256 px.",
    "request_id": "6e8c9d7d-e5dc-43a0-a59c-575e586684d8"
  }
}
```

| HTTP | `code` | Khi nào |
|---|---|---|
| 400 | `EMPTY_FILE` | File 0 byte |
| 400 | `INVALID_IMAGE` | Pillow không nhận ra ảnh (text giả `.jpg`) hoặc ảnh bị cắt cụt |
| 404 | `NOT_FOUND` | Đường dẫn không tồn tại |
| 405 | `METHOD_NOT_ALLOWED` | Sai phương thức |
| 413 | `FILE_TOO_LARGE` | Vượt dung lượng |
| 413 | `TOO_MANY_PIXELS` | Vượt số pixel hoặc cạnh tối đa |
| 415 | `UNSUPPORTED_FORMAT` | Đọc được nhưng không phải JPEG/PNG, hoặc nhiều khung hình (GIF, WebP động, APNG). *Bản nháp #95, chờ quyết định: MPO cũng được nhận, chỉ chấm khung đầu* |
| 422 | `MISSING_FILE` | Thiếu trường `file` |
| 422 | `MULTIPLE_FILES` | Nhiều hơn một file |
| 422 | `IMAGE_TOO_SMALL` | Cạnh ngắn < 256 px |
| 422 | `INVALID_REQUEST` | Yêu cầu sai khác |
| 500 | `MODEL_ERROR` | `score` lỗi, hoặc trả NaN, Infinity, giá trị ngoài `[0, 1]` |
| 500 | `INTERNAL_ERROR` | Lỗi khác; không lộ stacktrace |
| 503 | `MODEL_NOT_READY` | Model chưa sẵn sàng |
| 503 | `SERVICE_BUSY` | Hết slot suy luận |
| 504 | `MODEL_TIMEOUT` | Quá thời gian xử lý |

**Ảnh hưởng:** Streamlit dựa vào `verdict` và `error.code`; Nginx phải trả lỗi cùng envelope (xem mục dưới).

**Ghi chú đã duyệt:** ranh giới 400 và 415 (file không phải ảnh là 400, ảnh sai định dạng là 415); ba mã `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INVALID_REQUEST` được thêm ngoài gợi ý của D05 để lỗi framework cùng định dạng.

**Hạn chế đã biết:** JPEG nhúng nhiều ảnh (MPO, ví dụ gain map HDR từ một số điện thoại) bị Pillow nhận là `MPO` nhiều khung hình nên trả 415 theo đúng bảng trên. Chưa đo tỷ lệ ảnh điện thoại thật bị ảnh hưởng.

**Đề xuất #95 (bản nháp, chờ quyết định, chưa đổi trạng thái approved):** nhận ảnh `MPO` và chỉ chấm khung đầu; khung phụ không được giải mã, giới hạn dung lượng, pixel và cạnh vẫn tính trên khung đầu; GIF, WebP động và APNG vẫn 415. Mã trong nhánh `luc/mpo-support`; chưa thử với file MPO thật của iPhone.

### Làm rõ (issue #43)

Quang chọn ngày 2026-11-11, trả lời 5 câu Lực hỏi khi viết test hợp đồng; chờ Lực review.

**1. `INVALID_REQUEST`:** request không có phần file ảnh (body JSON, trường `file` là chuỗi chữ, sai tên trường, content-type không phải multipart) là 422 `MISSING_FILE`. `INVALID_REQUEST` dành cho body không đọc được (multipart hỏng) và lỗi validation khác, **luôn 422**; trước đây multipart hỏng trả 400, đã sửa cho khớp bảng trên.

**2 và 4. Thứ tự kiểm tra:** request vi phạm nhiều quy tắc thì nhận lỗi của bước đầu tiên nó vi phạm:

1. Thiếu file hoặc nhiều file: 422 `MISSING_FILE`, `MULTIPLE_FILES`.
2. Không cần giải mã: 400 `EMPTY_FILE`, 413 `FILE_TOO_LARGE`.
3. Model: 503 `MODEL_NOT_READY`, rồi 503 `SERVICE_BUSY`.
4. Đọc header và giải mã ảnh, theo đúng thứ tự: 400 `INVALID_IMAGE` khi không nhận ra ảnh (hoặc 413 `TOO_MANY_PIXELS` khi header lớn tới mức Pillow chặn ngay lúc mở), 415 `UNSUPPORTED_FORMAT`, 413 `TOO_MANY_PIXELS`, 415 nhiều khung hình, 400 `INVALID_IMAGE` khi giải mã lỗi.
5. Trong `score()`: 422 `IMAGE_TOO_SMALL`, 500 `MODEL_ERROR`.

Bước 1–2 chạy trước và không chiếm slot. Giải mã nằm trong slot (MVP-02), nên model chưa sẵn sàng được báo trước lỗi giải mã. Ví dụ: GIF 100×100 là 415, không phải 422; khi chưa có model, file rỗng là 400 còn text giả `.jpg` là 503.

**3. Chuỗi `exif`:** chỉ gồm hãng (`Make`) và model máy (`Model`), không GPS hay serial.

| EXIF | `exif` |
|---|---|
| Hãng và model | `"<Hãng> <Model>"`; từ đầu tiên của model trùng từ đầu tiên của hãng (so nguyên từ, không phân biệt hoa thường) thì chỉ trả model (`Canon` + `Canon EOS 5D` → `Canon EOS 5D`; `NIKON CORPORATION` + `NIKON D750` → `NIKON D750`; `Canon` + `Canonical X` → `Canon Canonical X`) |
| Chỉ hãng hoặc chỉ model | Giá trị đó (`Canon`, `EOS 5D`) |
| Không có, rỗng hoặc đọc lỗi | `Không có thông tin máy chụp` |

Mỗi giá trị bỏ ký tự điều khiển, gộp khoảng trắng và cắt còn tối đa 64 ký tự, **trước** khi so tên hãng và ghép. Giới hạn áp cho từng giá trị, nên cả chuỗi `exif` tối đa 129 ký tự (64 + dấu cách + 64). Thẻ EXIF không phải ASCII bị Pillow ghi thành `?` khi lưu file, nên ký tự tiếng Việt trong `Make`/`Model` thường không đến được API nguyên vẹn.

Sửa ngày 2026-11-11 theo review của Lực: bỏ lặp tên hãng chuyển từ so tiền tố ký tự sang so nguyên từ; ghi rõ giới hạn 129 ký tự.

**5. Kiểu của điểm:** `score()` phải trả float, của Python hoặc numpy (`float32`, `float64`). `str`, `int`, `bool`, `None` hay mảng nhiều phần tử là 500 `MODEL_ERROR`, không ép kiểu: số nguyên 0/1 thường là nhãn lớp từ `predict()` chứ không phải xác suất.

### Lỗi do gateway trả (đề xuất 2026-11-09; Lực duyệt 2026-11-12)

Đề xuất của Quang cho MVP-01. Enum `ErrorCode` trong `app/schemas.py` chưa thêm các mã này.

**UI (Loan xác nhận 2026-11-13):** `streamlit/api_client.py` không đọc `error.code`; UI chọn thông báo tiếng Việt theo mã HTTP, riêng 413 hiện `error.message` của gateway. Mỗi lần bấm gửi đúng một POST, kể cả khi có `Retry-After`. Đã thêm thông báo cho 502; `tests/test_ui.py` kiểm 413, 429, 502, 504 với body lấy từ `nginx/nginx.conf`. Chưa thử bằng trình duyệt thật.

| HTTP | `code` | Ai trả | Khi nào | `message` |
|---|---|---|---|---|
| 413 | `FILE_TOO_LARGE` (dùng lại) | Nginx | Body vượt `client_max_body_size` (D06) | Như bảng API |
| 429 | `RATE_LIMITED` (mới) | Nginx | Vượt 10 request/giây mỗi IP (D13) | "Đang có quá nhiều yêu cầu. Vui lòng đợi một lát rồi thử lại." |
| 502 | `API_UNAVAILABLE` (mới) | Nginx | API không chạy hoặc từ chối kết nối | "Hệ thống phân tích chưa sẵn sàng. Vui lòng thử lại sau." |
| 504 | `GATEWAY_TIMEOUT` (mới) | Nginx | API không trả lời trong `proxy_read_timeout` | "Hệ thống xử lý quá lâu. Vui lòng thử lại sau." |

- Cùng envelope `{"error": {code, message, request_id}}`, `Content-Type: application/json`.
- `request_id`: Nginx tạo bằng `$request_id`, gửi sang API qua header `X-Request-ID` và trả lại trong header response. API chỉ nhận UUID, và `$request_id` (32 ký tự hex) được API ghi lại ở dạng UUID có gạch nối.
- 429 kèm `Retry-After: 1` (D13). Các lỗi khác không gửi `Retry-After`.
- `GATEWAY_TIMEOUT` khác `MODEL_TIMEOUT`: `MODEL_TIMEOUT` do API trả khi model quá D11; `GATEWAY_TIMEOUT` nghĩa là cả API không trả lời kịp. `proxy_read_timeout` phải dài hơn tổng thời gian API (D11), và timeout của UI dài hơn proxy.
- **504 cũng có thể xuất hiện khi API vừa dừng (QA kiểm 12/11, Linux, Compose):** Nginx giữ địa chỉ IP của `api` trong `valid=10s`. Trong khoảng 10 giây đầu sau khi dừng, request nào còn dùng IP cũ sẽ kết nối vào địa chỉ đã biến mất và chờ hết `proxy_connect_timeout 5s`, nên nhận `504 GATEWAY_TIMEOUT` sau 5 giây (log `upstream timed out (110) while connecting`). Hết cache thì Nginx hỏi lại DNS, không phân giải được `api` và trả `502 API_UNAVAILABLE` sau khoảng 1 giây (`resolver_timeout 1s`). Dừng bằng `docker compose kill` và các lần cache nguội đều ra 502 sau khoảng 1 giây. `pause` thì ra 504 sau khoảng 15 giây (đúng định nghĩa 504). Vì vậy "502 = API không chạy" đúng gần như luôn, không tuyệt đối. `resolver_timeout 1s` không gây ra 504 (bỏ dòng đó chỉ làm 502 chậm 3 đến 4 giây). Chưa đổi cấu hình: hạ `proxy_connect_timeout` và `valid` chỉ thu hẹp cửa sổ, không loại bỏ.
- Đổi tên `UPSTREAM_UNAVAILABLE` (đề xuất 2026-11-09) thành `API_UNAVAILABLE` (2026-11-11): `scripts/check_gateway.py` coi chữ "upstream" trong body lỗi là lộ chi tiết nội bộ (FR-N03).
- Đã cấu hình trong `nginx/nginx.conf` (MVP-05) và QA kiểm 8/8 qua Nginx thật (`check_gateway`). Lực duyệt 2026-11-12; còn chờ Loan xác nhận UI đọc `error.code` (không chặn).

## D06. Dung lượng file

**Lựa chọn:** tối đa 5.242.880 byte (`REALCHECK_MAX_FILE_BYTES`).

**Lý do:** trùng cách Nginx hiểu `5m`, tránh lệch giữa gateway và API.

**Body dư cho multipart (proposed, 2026-11-09):** 64 KiB. Nginx đặt `client_max_body_size 5184k` (5.242.880 + 65.536 = 5.308.416 byte). Phần dư chỉ để chứa header multipart; file vẫn bị API giới hạn đúng 5.242.880 byte, body lọt qua Nginx nhưng file lớn hơn vẫn nhận 413 `FILE_TOO_LARGE` từ API.

## D07. Số pixel

**Lựa chọn:** tối đa 24 MP và cạnh tối đa 10.000 px (`REALCHECK_MAX_PIXELS`, `REALCHECK_MAX_SIDE`).

**Lý do:** cho qua JPEG 4000×3000 (12 MP) và phần lớn ảnh điện thoại.

**Lưu ý:** spec yêu cầu chọn theo RAM đo; hiện chưa đo. Xem lại sau benchmark.

## D11. Timeout

**Lựa chọn:** timeout model 10 giây (`REALCHECK_MODEL_TIMEOUT_S`).

**Mốc xem lại:** sau benchmark MVP-09 trên model thật. Kiệt đo local: startup + warmup khoảng 31,57 giây, một lượt score sau warmup 0,065–0,093 giây ([bàn giao ML](../ml-handoff.md)); chưa phải số đo trên server.

**Lưu ý:** timeout của Nginx và UI phải dài hơn timeout này. Thời gian khởi động và warmup tính riêng.

**Gateway và UI (proposed, 2026-11-11):** Nginx `proxy_read_timeout` 15 giây cho `/v1/`, dư 5 giây cho giải mã và ghi response; UI 60 giây (`REALCHECK_API_TIMEOUT`). Đã đo qua gateway: API bị treo thì Nginx trả 504 `GATEWAY_TIMEOUT` sau 15,0 giây.

## D12. Cơ chế suy luận

**Lựa chọn:** thread, 1 worker, 1 slot (`REALCHECK_INFERENCE_SLOTS`), không xếp hàng; hết slot trả 503.

**Lý do:** đơn giản nhất đáp ứng được giới hạn tài nguyên.

**Hệ quả:** thread không hủy được CLIP đang chạy. Quá giờ trả 504 nhưng slot chỉ nhả khi việc thật sự kết thúc, nên trong lúc đó request mới nhận 503.

**Mốc xem lại:** sau benchmark CPU/RAM MVP-09. Kiệt chưa chứng nhận shared `Scorer` an toàn đa luồng; giữ một slot. [Trả lời và timing offline](ml-api-handoff-39.md#d12-và-fr-a06-trả-lời-câu-hỏi-pr-36); FR-A06 logging API còn chờ.

## D13. Truy cập và rate limit (đề xuất 2026-11-09; Lực duyệt 2026-11-12)

**Lựa chọn đề xuất:**
- Demo chạy HTTP cổng 80 trong mạng lab hoặc qua SSH tunnel; **không TLS**, không public.
- Rate limit 10 request/giây theo IP kết nối thật (`$binary_remote_addr`). **Không tin `X-Forwarded-For`** do client tự gửi.
- `burst=10 nodelay`: cho dồn tối đa 10 request rồi trả 429 ngay, không xếp hàng nên không làm tăng latency.
- 429 kèm `Retry-After: 1`.

**Quyết định ngày 12/11 (Lực):** duyệt, và sửa quyết định 10/11 ("không phục vụ HTTP thường trên mạng lab"): **mạng lab nội bộ được dùng HTTP thường; truy cập từ ngoài mạng lab bắt buộc SSH tunnel; ra Internet phải có TLS và quyết định mới.** Rủi ro chấp nhận: ai trong mạng lab nghe được lưu lượng thấy được ảnh gửi lên. Tường lửa máy lab chỉ cho mạng lab vào cổng 80 (`docs/deploy.md`).

**Hệ quả đã biết:** Streamlit gọi API qua Nginx từ server, nên mọi phiên UI dùng chung IP của container Streamlit và chung giới hạn 10 request/giây. Không tuyên bố giới hạn theo từng trình duyệt (spec 000 mục 10).

**Vì sao mạng lab hoặc SSH tunnel, không TLS (2026-11-11, issue #42):**
- TLS cần chứng chỉ mà client tin. Chứng chỉ tự ký buộc `scripts/smoke_api.py`, `scripts/check_gateway.py` và Locust phải cấu hình tin chứng chỉ riêng; demo chỉ dùng trong lab nên không cần mã hóa ra Internet.
- Hệ quả của SSH tunnel: mọi client đi qua tunnel vào Nginx từ cùng một địa chỉ (tiến trình `sshd` trên máy lab), nên dùng chung 10 request/giây. **Locust đo tải phải chạy từ một máy trong mạng lab** (có IP riêng), không qua tunnel; bài đo rate limit tách riêng khỏi bài đo hiệu năng (D14).
- Mở ra Internet thì phải có TLS, cần quyết định mới.

**Còn mở:** URL lab cụ thể và máy chạy demo; danh sách IP proxy tin cậy để trống vì không có proxy nào đứng trước Nginx.

**Đã cấu hình (MVP-05, 2026-11-11):** `nginx/nginx.conf` áp rate limit cho `/v1/`; `/health`, `/docs`, `/openapi.json` và UI không bị giới hạn. Lực duyệt 2026-11-12.

## Hợp đồng `score`

Ngưỡng D08 và lựa chọn manifest/holdout mới được ghi tại [ml-selection.md](ml-selection.md). Bảng API/UI hiện có khớp các mốc Kiệt chọn; việc đó không thay thế xác nhận QA hoặc kết quả model-test.

**Lựa chọn:** theo spec 001: `models/score.py`, `score(image) -> float`, `image` là PIL Image gốc đã giải mã, chưa chuẩn hóa. API giải mã một lần, đọc EXIF, gọi `score` và bắt `ImageTooSmall`. Không quay lại giao diện nhận bytes của spec 000.

**Lý do:** spec 000 ghi `models/scoring.py` và nhận bytes, nhưng spec 001 mới hơn và có Clarification riêng cho điểm này. Nhận PIL Image cho phép API giải mã đúng một lần.

**Quyết định 2026-11-12 (Lực): approved.** Đã kiểm: Quang chạy thật trên Windows, QA trên Linux (điểm CLI và API lệch tối đa 5e-9, container khớp từng chữ số). Không duyệt release model.

**Hiện trạng trước đó:** Kiệt đã ghi [xác nhận kỹ thuật phía ML](ml-api-handoff-39.md#hợp-đồng-score-xác-nhận-kỹ-thuật-ml), kèm smoke model thật trên main. Chờ Quang/Lực review nên vẫn `proposed`, không tự ghi QA/release approved.

**Trả lời phía ML:** chọn reference e571 cho local/lab; giữ một slot vì chưa chứng nhận đa luồng; gói có profiler offline, FR-A06 telemetry API chưa làm. Xem [bàn giao #39](../ml-api-model-handoff.md). Đã kiểm trên máy Quang (mục dưới); còn chờ review chung.

### Kiểm trên máy API (issue #39)

Quang kiểm ngày 2026-11-11 trên Windows 11, Python 3.11.9, torch 2.15.0+cpu, sentence-transformers 6.2.0, Pillow 13.0.0, CLIP revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f` chạy offline (`HF_HUB_OFFLINE=1`). Code: `main` tại `aa20693` (đã có MVP-02 #37, B4 #38 và #61). Model chép vào `models/clip_probe_e571.joblib` (gitignored), nạp qua `REALCHECK_MODEL_PATH`.

| Kiểm tra | Kết quả |
|---|---|
| ZIP `realcheck-api-model-e571-20261110-v2.zip` | 24.132 byte, SHA256 `baf7bd57…` khớp release |
| `sha256sum -c SHA256SUMS` và `verification/clip_probe.joblib.sha256` | `OK` |
| Model SHA256 | `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494` |
| Metadata (`load_bundle`) | `labels_sha256` `4bf8e490…`, `norm_version` `1`, ngưỡng `0.5 / 0.3 / 0.7` |
| `python -m models.score` trên 4 ảnh gốc (2 thật, GLIDE, Midjourney) | Điểm hữu hạn trong `[0, 1]`; ảnh 100×100 ném `ImageTooSmall` |
| `uvicorn app.main:app`, `REALCHECK_MODEL_PATH` trỏ tới model e571 | Nhận request sau 15,7 giây; `/health` 200 `model_ready=true`; 4 ảnh trả 200, điểm trùng CLI tới 8 chữ số thập phân; text giả `.jpg` trả 400 `INVALID_IMAGE` |

- Đây là kiểm nhận artifact và khởi động, **không phải số đo accuracy**: 4 ảnh lấy từ `data/raw` và có thể thuộc tập train.
- Chưa kiểm trong Docker/Linux, chưa kiểm tải hay nhiều slot.
- `REALCHECK_MODEL_PATH` phải đặt rõ: mặc định `models/clip_probe.joblib` là model cũ `69810fd6…`, khác model e571.

## D01–D04. Dữ liệu và audit

Hiện trạng trong mã, **không phải quyết định đã duyệt**:

| Mục | Mã hiện tại | Còn thiếu |
|---|---|---|
| D01 | `scripts/prepare_data.py`: seed 42; GenImage 70/15/15; CIFAKE tách 15% train làm val, test giữ split gốc; `--split-from` giữ split cũ | Cách nhóm ảnh cha/near-duplicate; ghi lý do chọn |
| D02 | Spec 001 Clarifications: xoay EXIF → RGB → `ImageOps.fit` BICUBIC 256×256 → JPEG 95 một lần; ảnh cạnh ngắn < 256 bị loại; version `1` | [Đã ghi quan sát v1](ml-api-handoff-39.md#d02-hành-vi-version-1-hiện-có): bỏ alpha, không chuyển/nhúng ICC, default Pillow quan sát 4:2:0; chờ duyệt chung |
| D03 | `scripts/metadata_audit.py` (bản nháp T007): `HistGradientBoostingClassifier` | Đăng ký probe trước khi xem audit-test |
| D04 | Audit dùng cột `split` của manifest; control dương và control âm | Protocol riêng khỏi model-test, cỡ mẫu tối thiểu mỗi slice, số lần bootstrap |

## Manifest

Có ba manifest khác nhau. **Kiệt chọn manifest giữ split cho reference e571 local/lab** ([bàn giao](../ml-api-model-handoff.md)); xác nhận manifest/dữ liệu của Loan và QA độc lập vẫn còn chờ.

| Manifest | Đường dẫn | Ảnh | SHA256 `labels.csv` | `norm_version` | Dùng cho |
|---|---|---|---|---|---|
| Main (từ PR #83, 2026-11-12) | `data/labels.csv` (trong Git) | 9.708 | `112aa115d233857378dd4be26711850241af15d44c4e0070a7bab9ba69ac4bdf` (nội dung trong Git, LF) | 1 | **Manifest phục vụ model đã chốt**; cùng ảnh và split với bộ giữ split của e571 (đổi tiền tố `data/processed/` thành `../outputs/realcheck-preserved-split/processed/` và CRLF thì SHA256 ra `4bf8e490…`) |
| Main cũ | `data/labels.csv` ở commit `58a21b5` | 10.000 | `dac186082dd3506bc91acda7cdd6ed5bb68b083e2ed7f445d7e89edc16d67931` | Không có cột | Tham chiếu cũ; baseline T012 và `check_raw_baseline` đo trên bộ này |
| Lần chạy ML đầu | `.cache/ml-run/labels.csv` (máy Kiệt) | 9.708 | `72313cf272f101c84c757d25c29869af8d290743e2be3151b5c9aa6debeae8c5` | 1 | Train `clip_probe.joblib` cũ, SHA256 `69810fd6…` |
| Giữ split | `../outputs/realcheck-preserved-split/labels.csv` (máy Kiệt) | 9.708 | `4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad` | 1 | Kiệt chọn; train model mới, SHA256 `e5718345…`, `release_approved=false` |

- 9.708 = 10.000 trừ 292 ảnh thật GenImage cạnh ngắn < 256 px, ghi trong `rejected_small.csv`. `prepare_data` còn ghi `rejected_invalid.csv` và `rejected_duplicate.csv`.
- Baseline T012: `data/processed_baseline.sha256` (Loan, commit `68bb352`, 10.005 dòng). Đối chiếu độc lập T013 còn chờ.
- Pillow 13.0.0 (ghim trong `requirements.txt`, nằm trong metadata của model).
- **Hash phụ thuộc kiểu xuống dòng.** SHA256 của manifest main ở trên tính trên nội dung trong Git (LF). Trên Windows với `core.autocrlf=true`, file checkout ra là CRLF và có SHA256 `7a83b1c7…`. Khi chốt manifest cần ghi hash tính theo cách nào, hoặc thêm `.gitattributes` giữ LF cho file CSV.

**Quyết định 2026-11-12 (Lực):** manifest phục vụ model là bộ 9.708 ảnh giữ split đã đưa lên `data/labels.csv` (PR #83); SHA256 khớp manifest e571 theo kiểm của QA. **Loan còn cần xác nhận** đường dẫn, commit tạo ra, chính sách split và các file rejected; `metadata_audit.json` và `baseline_filesize.json` vẫn đo trên bộ 10.000 ảnh cũ (chưa đo lại, T026).

## Xung đột audit (spec 000 và spec 001)

- Spec 000: post `A_eff > 0.55` chặn release.
- Spec 001 FR-009 và T026: đề xuất `metadata_audit.py` chỉ cảnh báo, chờ Loan và Lực xác nhận.
- Mã hiện tại: `metadata_audit.py` là cổng cứng, thoát mã 1 khi không đạt.

**Quyết định 2026-11-12 (Lực): chọn phương án do MVP-01 nêu.** `metadata_audit.py` chỉ cảnh báo theo T026, và một release checker riêng vẫn chặn post `A_eff > 0.55`. **Hiện thực (bản nháp, chờ merge):** `metadata_audit.py` chỉ cảnh báo, `scripts/check_release_audit.py` chặn. Đặc trưng post toàn hằng số là cảnh báo mạnh, không chặn; cờ `--fail-on-vacuous` chuyển thành chặn. Lưu ý: post-A_eff hiện bằng 0,5 vì 13 đặc trưng đều là hằng số, nên cổng này đạt "rỗng" và không chứng minh dữ liệu sạch. Loan xác nhận.

Dù chọn phương án nào, các ca sau phải fail: `A_eff = max(AUROC, 1 − AUROC)` vượt 0.55; thiếu slice hoặc slice thiếu một lớp; dự đoán NaN; control dương hoặc control âm không hợp lệ.

Nếu nhóm chọn khác, phải sửa spec và phạm vi nghiệm thu trước khi làm. Cần biên bản có Loan và Lực.

## Phạm vi nghiệm thu M1 và M2

Trạng thái: approved (Lực, 2026-11-12); đề xuất 2026-11-09. Loan và Kiệt chưa xác nhận.

| Mốc | Phạm vi | Acceptance |
|---|---|---|
| M1 Demo localhost | `uvicorn` và Streamlit trên một máy, model thật, chưa qua Nginx/Docker | Các AC kiểm được không cần gateway: AC-01 đến AC-08, AC-10 đến AC-12, AC-19 đến AC-22, AC-27, AC-29 |
| M2 Nghiệm thu core | Docker Compose, Nginx cổng 80, model và manifest đã chốt | AC-01 đến AC-24, AC-27, AC-29, cộng AC-25 (model-test) và AC-28 (hiệu năng, sau khi chốt D09, D10, D14) |

- AC-26 (robustness nâng cao) nằm ngoài backlog này; nhóm phải xác nhận phạm vi.
- AC-09, AC-23, AC-24 cần Nginx thật nên thuộc M2. AC-13 đến AC-18 thuộc dữ liệu và audit, kiểm trong lúc làm M1 nhưng nghiệm thu ở M2.
- Spec 000 T001–T013 trong `tasks.md` chưa task nào được đánh dấu xong; chưa rà soát thì không coi là đã hoàn thành.

## Việc cần từng người

| Người | Việc |
|---|---|
| Lực | Đã duyệt 12/11: mã lỗi gateway, body dư 64 KiB, D13, hợp đồng `score`, D08 (MVP), M1/M2. Còn: cùng Loan chốt chính sách audit; chốt D09, D10, D14 sau khi đo trên lab; duyệt mục D05 làm rõ (issue #43) |
| Loan | Xác nhận D05 và mã gateway cho UI; chốt D01, D03, D04 và manifest; cùng Lực chốt chính sách audit |
| Kiệt | Đã ghi [lựa chọn model, contract, thread/timing và D02](../ml-api-model-handoff.md); Quang đã xác nhận checksum/CLI (#39), còn review chung |
| Quang | Đăng kết quả kiểm vào issue #39; tổng hợp các mục còn chờ |
| Cả nhóm | Duyệt phạm vi M1/M2 và AC-26 |

## Quyết định của Lực ngày 12/11/2026

| Quyết định | Kết quả |
|---|---|
| Mã lỗi gateway, body dư 64 KiB, timeout `/v1/` 15 giây, rate limit 10 r/s burst 10 | Duyệt tất cả; Loan còn xác nhận UI đọc `error.code` |
| D13 truy cập | Mạng lab nội bộ dùng HTTP; truy cập ngoài bắt buộc SSH tunnel; Internet cần TLS và quyết định mới |
| Hợp đồng `score(PIL.Image) -> float` | Duyệt |
| D08 ngưỡng 0.3/0.5/0.7 | Duyệt cho MVP, không phải duyệt release (xem giới hạn ở bảng trạng thái) |
| Model mặc định | Không đổi mã; bắt buộc đặt `REALCHECK_MODEL_PATH`; hỏi Kiệt nếu muốn đổi mặc định sau |
| `inference_slots` | Giữ 1 cho MVP; `slots = 2` chỉ sau khi Kiệt xác nhận `Scorer` an toàn đa luồng |
| Phạm vi M1/M2 | Duyệt (M1 localhost đã diễn tập; M2 Compose và đo tải trên lab) |
| D09, D10, D14 | Hoãn tới khi đo trên máy lab |
| Chính sách audit, manifest phục vụ model | Đã chọn ngày 12/11 (cập nhật sau): audit cảnh báo + release checker riêng chặn `A_eff > 0.55`; manifest là bộ 9.708 ảnh giữ split (PR #83). Loan xác nhận; mã audit chưa đổi |
| Giới hạn exif 64 ký tự mỗi giá trị (tối đa 129) | Không thuộc đợt này; giữ như đã ghi ở D05 làm rõ |

Nguồn bằng chứng: `docs/qa/local-real-model-verification-20261111.md`, `docs/qa/kan-25-model-loading-review.md`, issue #44.
