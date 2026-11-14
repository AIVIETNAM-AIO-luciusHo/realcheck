# Runbook M1 và kịch bản demo (diễn tập trên Linux với model e571, 11/11/2026)

**Mục đích:** khi có model (issue #39) thì làm theo từng bước, lấy bằng chứng cho KAN-29, rồi demo.
Soạn từ [`app/README.md`](../../app/README.md), [`streamlit/README.md`](../../streamlit/README.md), [`models/README.md`](../../models/README.md), `scripts/smoke_api.py` và [mẫu biên bản tích hợp](integration-report-template.md).

**Đã kiểm 11/11:** diễn tập các bước trên Linux với model e571 (API, Streamlit, smoke 26 ca đạt), chỉ với ảnh tổng hợp và một ảnh hoa mẫu. **Chưa kiểm:** giao diện bằng trình duyệt thật (giới hạn tải 5 MiB, theme) và bảng 6 ảnh ở mục 8 với ảnh của người demo. Kết quả của ảnh thật chụp bằng điện thoại và ảnh gửi qua Zalo lấy từ [báo cáo cohort ADV-06](../cohorts-adv06.md), không phải từ lần diễn tập này.

M1 = demo localhost: `uvicorn` và Streamlit trên một máy, model thật, **chưa** Nginx/Docker (triển khai Compose: [`docs/deploy.md`](../deploy.md)).

---

## 1. Điều kiện bắt đầu (checklist)

| # | Cần có | Lấy từ | Có rồi? |
|---|---|---|---|
| 1 | `clip_probe.joblib` **và** `clip_probe.joblib.sha256` (gói release `api-model-reference-e571-20261110`); chép vào `models/` với tên `clip_probe_e571.joblib` và `clip_probe_e571.joblib.sha256` | Người giao model (#39) | ☐ |
| 2 | Xác nhận model nào (cũ `69810fd6…` hay mới `e5718345…`), commit tạo ra, giới hạn | Người giao model (#39) | ☐ |
| 3 | Trọng số CLIP đã tải đúng revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f` (thư mục cache Hugging Face) | Người giao model hoặc tải lần đầu có mạng | ☐ |
| 4 | Python 3.11 hoặc 3.12, đủ chỗ cho torch CPU (khoảng 2 GB) | Máy demo | ☐ |
| 5 | Ảnh mẫu thật và ảnh AI có nguồn, giấy phép rõ (không commit) | Người demo | ☐ |

Thiếu mục 1 hoặc 2 thì **dừng**: `/health` sẽ trả 503 và không có gì để demo.

## 2. Kiểm model trước khi chạy

```bash
cd <thư mục gốc repo>
# đặt 2 file cạnh nhau, ví dụ models/
# File .sha256 của gói chỉ có hash trần, kết thúc CRLF nên `sha256sum -c` báo 'no properly formatted checksum lines'. Dùng:
test "$(sha256sum models/clip_probe_e571.joblib | cut -d' ' -f1)" = "$(tr -d '\r\n' < models/clip_probe_e571.joblib.sha256)" && echo OK
```
`sha256` trong file `.sha256` phải khớp. Khớp rồi mới chạy tiếp. (`load_scorer` cũng tự kiểm checksum, metadata `dataset == "genimage"`, `norm_version`, hợp đồng đặc trưng; sai thì từ chối.)

## 3. Dựng môi trường

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r models/requirements-ml.txt -r streamlit/requirements.txt
# trọng số CLIP: lần đầu cần mạng; sau đó chạy offline
export HF_HOME="$PWD/.cache/huggingface"
# sau khi đã tải xong lần đầu:
export HF_HUB_OFFLINE=1
```
Nếu chưa có cache CLIP, chạy một lần khi có mạng (không đặt `HF_HUB_OFFLINE`), bằng `python -c "from models.clip_input import load_encoder; load_encoder()"` (lệnh trong `app/README.md`), rồi đặt lại `HF_HUB_OFFLINE=1`.

## 4. Chạy API (cửa sổ terminal 1)

```bash
export REALCHECK_MODEL_PATH="$PWD/models/clip_probe_e571.joblib"   # BẮT BUỘC: mặc định models/clip_probe.joblib là model cũ 69810fd6
uvicorn app.main:app --port 8000
```
- Server chỉ nhận request sau khi nạp xong. Chạy `uvicorn` trực tiếp, không Docker (diễn tập 11/11): 8,6 giây khi cache đĩa nóng, **72,7 giây lần đầu khi cache lạnh**. Qua Docker Compose thời gian khác, xem [`docs/deploy.md`](../deploy.md). Bật API trước giờ demo ít nhất 2 phút và gọi một request để làm nóng (request đầu mất khoảng 1,4 giây).
- **Dấu hiệu thành công trong log:** dòng JSON `model_loaded` kèm `duration_ms`.
- Kiểm: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health` → **200**. `http://localhost:8000/docs` mở được.

**Nếu `/health` trả 503:** đọc log, tìm `model_load_failed` và tên lỗi:

| Tên lỗi trong log | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `FileNotFoundError` | Thiếu file model hoặc `.sha256`, sai `REALCHECK_MODEL_PATH` | Đặt đúng đường dẫn; hai file cạnh nhau |
| `ValueError` "Model checksum mismatch" | File hỏng hoặc không khớp `.sha256` | Nhận lại file từ người giao model |
| `ValueError` "Incompatible model: ..." | Model train với profile hay phiên bản khác | Hỏi người giao model; không sửa tay |
| `ImportError` / thiếu torch | Chưa cài `models/requirements-ml.txt` | Cài lại như mục 3 |
| Lỗi tải Hugging Face (offline) | Thiếu cache CLIP | Tải một lần có mạng (mục 3) |

## 5. Smoke test (KAN-29)

```bash
python -m scripts.make_fixtures --out .cache/smoke-fixtures
python -m scripts.smoke_api --base-url http://localhost:8000 --fixtures .cache/smoke-fixtures \
  --real <ảnh thật.jpg> --ai <ảnh AI.png> --out .cache/smoke-evidence.json
echo "exit=$?"
```
- Mã thoát: 0 đạt, 1 có ca lỗi, 2 không kết nối được.
- `--real` và `--ai` **chỉ ghi nhận** verdict và score, không fail khi phân loại sai (mục tiêu là luồng đúng hợp đồng, không phải độ chính xác).
- **Khác lần chạy với scorer giả:** với model thật, ca ảnh 200×200 và 255×400 phải trả 422 `IMAGE_TOO_SMALL` (scorer giả không chuẩn hóa nên trả 200). Nếu vẫn trả 200 thì ghi lại, đó là lỗi cần báo.
- Ca đúng 5.242.880 byte được gắn nhãn "cần xác nhận"; nếu báo lỗi oan thì chạy lại với `--skip-size-boundary` và ghi lý do.

## 6. Streamlit (cửa sổ terminal 2)

```bash
export REALCHECK_API_URL=http://localhost:8000
streamlit run streamlit/app.py
```
- Giao diện hiện 4 mức: Ảnh thật, Dự đoán thật, Dự đoán AI, Ảnh AI. API vẫn trả 3 kết luận (`likely_real`, `uncertain`, `likely_ai`); hai mức "Dự đoán" là `uncertain` tách theo điểm 0,5.
- Trang "Kết quả đánh giá" đọc `artifacts/evaluation.json` (hoặc `REALCHECK_EVAL_REPORT`); thiếu file thì báo chưa sẵn sàng, **không hiện số giả**.

## 7. Bằng chứng cần thu (cho KAN-29)

Sao chép [`integration-report-template.md`](integration-report-template.md) thành `docs/qa/integration-report-<ngày>.md` và điền:
- Môi trường: `git rev-parse HEAD`, dirty hay không, Python, `pip freeze`, tên file model và sha256, biến `REALCHECK_*`.
- Dán nguyên văn: đầu ra `smoke_api`, `.cache/smoke-evidence.json`, log có `model_loaded`.
- AC 1–6 (đạt / không / chưa) kèm bằng chứng; ghi lỗi còn tồn tại.
- Chạy `pytest --cov=app --cov-fail-under=70` và ghi số thật (không chép số cũ).

**Chỉ chuyển KAN-29 sang Done khi** smoke thật có kết quả và người khác (không phải người viết công cụ) xem lại. Người kiểm phải khác người viết code của bản đang kiểm.

---

## 8. Kịch bản demo (khoảng 6 đến 8 phút)

### Giới hạn khi demo (đọc trước, nói thật với người xem)

Số đo trên ảnh ngoài GenImage nằm ở [báo cáo cohort ADV-06](../cohorts-adv06.md) và [`cohorts-adv06-robustness.json`](../reports/cohorts-adv06-robustness.json), chấm bằng chính model e571 này:

| Nhóm ảnh | Số ảnh chấm | Kết quả của model e571 |
|---|---:|---|
| Ảnh **thật** (chụp bằng điện thoại, và ảnh thật gửi qua Zalo) | 76 (trong đó 1 ảnh Zalo là bản gửi qua Zalo của một ảnh gốc đã nằm trong nhóm điện thoại) | **64 bị gọi là "Ảnh AI" (84%)**, 6 "Chưa chắc", 6 đúng là thật |
| Riêng ảnh thật chụp bằng điện thoại | 55 | 47 "Ảnh AI", 6 "Chưa chắc", 2 thật (accuracy 3,6%) |
| Riêng ảnh thật qua Zalo | 21 | 17 "Ảnh AI", 4 thật |
| Ảnh **AI** (đời mới và qua Zalo) | 46 | 40 đúng là AI, 2 "Chưa chắc", 4 bị gọi là thật |

Hệ quả cho demo:
- **Một ảnh thật chụp bằng điện thoại rất có thể ra "Ảnh AI". Đây là kết quả bình thường của model hiện tại, không phải lỗi của buổi demo.** Không giới thiệu ảnh như "ảnh thật sẽ được nhận là thật".
- Model **đáng tin hơn với ảnh dạng GenImage** (cùng kiểu dữ liệu train) và **chưa đáng tin với ảnh chụp điện thoại**. Chưa kiểm ảnh từ máy Android, ảnh chụp đêm, ảnh đã chỉnh sửa.
- Số 94,53% là trên **384 ảnh test đã lọc** (65 ảnh thật), chưa được duyệt độc lập; validation GenImage 97,24% (N = 871) đã được dùng khi chọn tham số nên không phải kết quả độc lập. **Không nói "đạt 90%".**
- Cohort rất nhỏ (56 / 32 / 36 ảnh), ảnh điện thoại gần như chỉ từ iPhone 11, khoảng tin cậy rộng; xem phần "Hạn chế" trong báo cáo cohort.
- Lần diễn tập 11/11 cũng cho thấy: cả 11 ảnh hợp lệ thử (tổng hợp và ảnh hoa mẫu) đều ra "Ảnh AI" (điểm 0,708 đến 0,999), ảnh chụp màn hình giả lập bị kết luận AI 93%, không ảnh nào rơi vào vùng "Chưa chắc".
- Ảnh MPO (ảnh chân dung iPhone): từ PR #106 (đã merge) API nhận MPO và **chỉ chấm khung đầu**; GIF, WebP động và APNG vẫn bị từ chối `UNSUPPORTED_FORMAT`. Hai ảnh MPO của cohort ADV-06 không có điểm vì lượt chấm 12/11 chạy ở commit `1e77b60`, trước khi nhận MPO. **Chưa thử file MPO thật của iPhone**: Tester (T-6) mới thử MPO do Pillow tạo, điểm bằng điểm của JPEG khung đầu (0,9591100811958313). Khi demo không dùng ảnh chân dung iPhone.

### Chuẩn bị trước 1 giờ
- [ ] Chạy đủ mục 2 đến 6; `/health` 200 trước khi lên sân khấu.
- [ ] Chọn 6 ảnh và **thử trước từng ảnh**, ghi kết quả thật vào bảng bên dưới. Không giả định ảnh nào ra kết quả nào, đặc biệt ảnh thật chụp bằng điện thoại.
- [ ] Mở sẵn 3 tab: Streamlit, `http://localhost:8000/docs`, terminal có log.
- [ ] Có phương án B (mục 8.4).

Cột "Kết quả khi thử" điền sau khi thử trên máy demo; chưa có kết quả tại 13/11.

| # | Ảnh | Mục đích | Điều đã quan sát (nguồn) | Kết quả khi thử (điền) |
|---|---|---|---|---|
| 1 | Ảnh điện thoại thật có EXIF (JPEG) | Ca bình thường, hiện EXIF | Cohort điện thoại: 47/55 ra "Ảnh AI", 2/55 ra thật. **Nhiều khả năng ra "Ảnh AI"**; dùng để nói về giới hạn, không phải để khoe | |
| 2 | Ảnh AI từ công cụ có trong tập train | Ca thường bắt đúng (26/32, vẫn có 4 nhầm) | Ảnh AI đời mới: 26/32 đúng; mọi ca nhận nhầm là thật đều là ảnh Gemini (4/4) | |
| 3 | Ảnh khó, điểm gần 0,3 đến 0,7 | Minh họa "Chưa chắc" | Vùng này hiếm: 6/55 ảnh điện thoại, 2/32 ảnh AI đời mới; lần diễn tập 11/11 không có ảnh nào. **Có thể không tìm được**, khi đó bỏ ca này và nói rõ | |
| 4 | Ảnh chụp màn hình (không EXIF) | EXIF chỉ là bằng chứng phụ, không đổi kết luận | Diễn tập 11/11: ảnh chụp màn hình giả lập bị kết luận AI 93%. API chỉ dùng EXIF để hiển thị, không đưa vào điểm | |
| 5 | File text đổi đuôi `.jpg` | Lỗi `INVALID_IMAGE` (400) | Đã diễn tập đúng mã | |
| 6 | Ảnh nhỏ dưới 256 px | Lỗi `IMAGE_TOO_SMALL` (422) | Đã diễn tập đúng mã | |

### 8.1 Mở đầu (1 phút)
- Bài toán: phân biệt ảnh thật và ảnh do AI tạo; trả `verdict`, điểm, EXIF, lý do.
- Mô hình: CLIP ViT-B/32 giữ nguyên trọng số + Logistic Regression; ngưỡng 0,3 và 0,7.
- Nói ngay: **kết quả là dự đoán, không phải chứng cứ chắc chắn**, và model hiện hay gọi ảnh thật chụp điện thoại là AI (phần "Giới hạn khi demo").

### 8.2 Luồng chính (3 đến 4 phút)
1. Trang `/docs`: nêu hợp đồng, bốn trường của response, các mã lỗi.
2. Streamlit: tải ảnh 1, rồi 2; chỉ ra mức kết luận, điểm phần trăm, EXIF, lý do. Nếu ảnh 1 ra "Ảnh AI", nói thẳng đó là giới hạn đã đo, không né.
3. Ảnh 3 (nếu tìm được): giải thích vùng "Chưa chắc" và vì sao hệ thống không ép phải trả lời.
4. Ảnh 4: EXIF chỉ là bằng chứng phụ, thiếu EXIF không chứng minh ảnh là AI.
5. Ảnh 5 và 6: lỗi trả đúng mã, thông báo tiếng Việt, **không lộ stacktrace**.

### 8.3 Điểm kỹ thuật nên nói (1 đến 2 phút)
- Một hàm chuẩn hóa ảnh dùng chung cho dữ liệu, huấn luyện và API; ảnh nhỏ bị từ chối thay vì phóng to.
- API giới hạn số request đồng thời; hết chỗ thì trả 503 ngay, không xếp hàng.
- Mọi kết quả kiểm thử có script chạy lại; CI chạy lint và test trên mọi PR.
- **Số đo (đọc đúng nguồn, đúng giới hạn):** validation GenImage 97,24% (N = 871, đã dùng chọn tham số nên không phải kết quả độc lập). GenImage test 94,53% chỉ trên **384 ảnh đã lọc**, không phải toàn bộ test, chưa có duyệt độc lập. Ảnh thật ngoài GenImage: xem bảng ở đầu mục 8. Nếu model đổi (#39) thì dùng số của model được giao.

### 8.4 Phương án B nếu model hoặc API lỗi
- Chiếu log `model_load_failed` và giải thích hành vi đúng: server vẫn sống, `/health` 503, không có chế độ model giả.
- Chiếu đầu ra `smoke_api` đã chạy trước (bằng chứng luồng chạy) và báo cáo đánh giá.
- Không giả kết quả, không bịa số.

### 8.5 Câu hỏi dễ gặp và cách trả lời trung thực
| Câu hỏi | Trả lời |
|---|---|
| Độ chính xác bao nhiêu? | Nêu số kèm giới hạn ở mục 8.3: 94,53% trên 384 ảnh đã lọc, chưa duyệt độc lập. Trên ảnh thật chụp điện thoại và Zalo, model gọi 64/76 ảnh là AI. Không nói "đạt 90%" |
| Ảnh thật chụp bằng điện thoại có nhận đúng không? | Hiện chưa: 55 ảnh điện thoại thật chỉ 2 ảnh được nhận là thật, 47 bị gọi là AI. Đây là suy giảm lớn đã đo trên cohort nhỏ (xem báo cáo cohort) |
| Model có nhận ảnh AI đời mới không? | Phần lớn có: 26/32 ảnh AI đời mới (Gemini, ChatGPT, ảnh Google Images) đúng, 2 chưa chắc, 4 nhầm là thật (đều là Gemini). Cohort nhỏ, khoảng tin cậy 75,0–96,9% |
| Có học đường tắt (dung lượng file, định dạng) không? | Đã đo: baseline chỉ dùng dung lượng file đạt 84,54% ở cặp thật với GLIDE, nên nguy cơ còn, chưa loại trừ |
| Chịu tải được bao nhiêu? | **Chưa có số đã duyệt.** Công cụ Locust đã có; baseline sơ bộ trên máy phát triển ở [biên bản 11/11](local-real-model-verification-20261111.md), không phải năng lực của máy lab |
| Có chạy trên server chưa? | Chưa; M1 chạy localhost. Compose và Nginx có hướng dẫn trong `docs/deploy.md`, chưa có bằng chứng trên máy lab |
| Sao không nhận ảnh chân dung iPhone? | Có nhận: từ PR #106 API chấm ảnh MPO theo khung đầu. Chưa thử file MPO thật của iPhone (mới thử MPO do Pillow tạo), nên chưa nói là đã kiểm với ảnh thật |

## 9. Rủi ro đã biết khi demo
- Lần khởi động đầu chậm (30 đến 75 giây tùy cache đĩa) và cần cache CLIP; bật API sớm.
- Mặc định `inference_slots=1`: mở nhiều tab và gửi cùng lúc có thể nhận 503 `SERVICE_BUSY`. Demo từng ảnh một.
- Thời gian một lượt `score` sau warmup khoảng 0,065 đến 0,093 giây trên máy phát triển; máy demo có thể khác.
- Điểm không phải xác suất đã hiệu chuẩn; đừng diễn đạt "87% là AI" như một xác suất chắc chắn.

---

## Kết quả diễn tập 11/11 (Linux, model e571; ảnh tổng hợp và một ảnh hoa mẫu)

- API lên được, `/health` 200, `/docs` 200; Streamlit lên được; `scripts.smoke_api` 26 ca, 0 lỗi.
- UI lái bằng `AppTest`: bấm gửi tới khi có kết quả 0,18 đến 0,27 giây; ảnh có EXIF hiện "Apple iPhone 13"; text đổi đuôi `.jpg` trả 400 `INVALID_IMAGE`; ảnh dưới 256 px trả 422 `IMAGE_TOO_SMALL`; không có stacktrace.
- Không đặt đường dẫn model: 503, log nêu thiếu file `.sha256`. Sai checksum: 503, log `Model checksum mismatch`. Ảnh quá 5 MB: 413.
- API tắt khi UI đang mở: UI hiện "Không kết nối được tới hệ thống" kèm URL, không crash; API chưa sẵn sàng: "Hệ thống chưa sẵn sàng hoặc đang bận".
- **Rủi ro cho demo:** cả 11 ảnh hợp lệ thử (tổng hợp và ảnh hoa mẫu) đều ra "Ảnh AI" (điểm 0,708 đến 0,999); ảnh chụp màn hình giả lập bị kết luận AI 93%. Không ảnh nào rơi vào vùng "Chưa chắc". Không diễn tả kết quả này như độ chính xác.
- Chưa thử: trình duyệt thật, `SERVICE_BUSY`, timeout, ngắt API khi server Streamlit thật mở.
