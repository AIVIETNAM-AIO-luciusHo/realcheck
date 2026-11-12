# ADV-06 — Ba cohort đánh giá thực tế: điện thoại, AI mới, Zalo (#50)

Người thu: Loan. Mục đích: đo model đã khóa trên ảnh ngoài GenImage cho AC-26. **Chỉ dùng để đánh giá**, không đưa vào train và không dùng để chọn model hay ngưỡng. Ảnh là ảnh cá nhân nên **không nằm trong Git và không chia sẻ**; Git có báo cáo này, manifest hash và kết quả chấm.

## Số thực nhận

Số trong kế hoạch của issue là mức dự kiến. Dưới đây là số thực nhận sau khi loại ảnh (mục "Ảnh bị loại").

| Cohort | Kế hoạch | Ảnh thu | **Đưa vào cohort** | Thật / AI | Nguồn |
|---|---|---:|---:|---|---|
| `phone` (ảnh chụp điện thoại) | 100–200 | 60 | **56** | 56 / 0 | iPhone 11: 45; iPhone 13: 1; không có EXIF: 10 |
| `ai_new` (ảnh AI đời mới) | 100–200 | 33 | **32** | 0 / 32 | Gemini: 16; ChatGPT (GPT-image): 4; Google Images, không rõ công cụ: 12 |
| `zalo` (ảnh gửi qua Zalo rồi tải về) | 50–100 | 45 | **36** | 22 / 14 | 1 ảnh thật ghép được với ảnh gốc trong `phone`; 35 ảnh không có ảnh gốc |

Cả ba cohort đều **thấp hơn kế hoạch**. Nhãn: `phone` luôn 0, `ai_new` luôn 1, `zalo` theo thư mục Loan tách (`AI/`).

Định dạng: `phone` 55 JPEG + 1 MPO; `ai_new` 20 PNG + 12 JPEG; `zalo` 35 JPEG + 1 MPO. Mọi ảnh có cạnh ngắn ≥ 256 px.

## Ảnh bị loại

| Cohort | Số ảnh | Lý do |
|---|---:|---|
| `phone` | 3 | Ảnh PNG 828×1792 (đúng kích thước màn hình iPhone 11): ảnh chụp màn hình, không phải ảnh camera |
| `phone` | 1 | Bản sao trùng byte của một ảnh khác (macOS tạo tên "… 2") |
| `zalo` | 8 | Trùng byte với một ảnh trong `phone`: chưa qua Zalo nén, chỉ là bản sao |
| `ai_new` | 1 | Cạnh ngắn 168 px (ảnh Google Images): API sẽ từ chối (`IMAGE_TOO_SMALL`), không có điểm |
| `zalo` | 1 | Cạnh ngắn 132 px (ảnh AI kiểu tranh minh họa): như trên |

Hai ảnh nhỏ bị loại sau khi preflight ADV-08 báo lỗi kích thước, trước lượt chấm chính, theo hướng dẫn của `docs/robustness-adv08.md`. Ảnh gốc của Loan không bị sửa hay xóa.

## Bảo vệ riêng tư

- **Lọc nội dung bằng mắt:** Loan tự loại ảnh có người, địa chỉ hay thông tin riêng tư trước khi đưa vào thư mục; script không thay được bước này.
- **Xóa vị trí GPS:** 50 ảnh có GPS (46 `phone`, 4 `zalo`). Bản chép chỉ bỏ phần GPS trong EXIF, **không nén lại ảnh**; mỗi ảnh được kiểm điểm ảnh trước và sau giống hệt nhau, và không còn GPS ở mọi khung (kể cả ảnh MPO nhiều khung). `scripts.robustness_manifest cohort` từ chối mọi ảnh còn GPS.
- **Tên file trung tính:** `phone_001.jpg`, `ai_new_001.png`, `zalo_001.jpg`… Bảng đối chiếu tên gốc chỉ nằm trên máy Loan.
- **Ảnh không rời máy Loan và không gửi cho QA**, kể cả mẫu. Theo thống nhất với Lực (QA, 12/11): chỉ chia sẻ manifest (hash), Loan chấm trên máy và công bố predictions, protocol và kết quả phân tích.

## Kiểm trùng với dữ liệu train

Ảnh cohort so với bộ chính (bộ A, model e571 train trên bộ này) và bộ mở rộng mixed-v3: **0 trùng byte, 0 gần trùng** (dHash ≤ 4) với bộ A. Với mixed-v3: 1 ảnh thật Zalo gần trùng (khoảng cách 4) một ảnh thật của OpenFake core test; không ảnh hưởng e571.

## Kết quả chấm với model e571

Model phục vụ API e571 (SHA256 `e5718345…`, gói release #39, kiểm SHA256 trước khi dùng), runner `scripts.evaluate --robustness`, phân tích `scripts.analyze_robustness` (ADV-08), cùng commit sạch `1e77b60` của main (`dirty=false`). Ngưỡng 0,3/0,7; accuracy theo ngưỡng 0,5 tính cả ảnh "Chưa chắc".

| Cohort | Nhãn | N chấm | Accuracy | CI 95% | Kết luận của model |
|---|---|---:|---:|---|---|
| `phone` | thật | 55 | **3,6%** | 0,0–9,1% | 47 AI, 6 chưa chắc, 2 thật |
| `zalo` | thật | 21 | 19,0% | — | 17 AI, 4 thật |
| `zalo` | AI | 14 | 100% | — | 14 AI |
| `zalo` | cả hai | 35 | 51,4% | 42,9–62,9% | |
| `ai_new` | AI | 32 | 87,5% | 75,0–96,9% | 26 AI, 2 chưa chắc, 4 thật (cả 4 là Gemini) |

2 ảnh MPO (1 `phone`, 1 `zalo`) bị từ chối với `UNSUPPORTED_FORMAT`, không có điểm. CI tính bằng bootstrap 2.000 lần theo nhóm (ADV-08); dòng Zalo tách theo nhãn đếm trực tiếp từ predictions.

**Đọc kết quả:**
- **Model e571 gọi gần như mọi ảnh thật chụp bằng iPhone là ảnh AI** (điểm AI trung vị 0,97). Ảnh thật qua Zalo cũng bị gọi là AI phần lớn. Đây là suy giảm lớn trên ảnh thật thực tế; AC-26 không đòi 90% nhưng không được giấu số này.
- Ảnh AI đa số được nhận đúng; cả 4 lần gọi nhầm là thật đều là ảnh Gemini.
- Không đo được tỷ lệ đổi kết luận do Zalo nén: chỉ 1 ảnh Zalo có ảnh gốc.
- Báo cáo ADV-08 có trạng thái `incomplete` vì các cohort biến thể (JPEG, xoay, cắt…) chưa chạy, chờ `group_id` của bộ A.

## Truy vết

| File | SHA256 |
|---|---|
| `phone.jsonl` (56 dòng) | `8c4978693580367f3ba44095dd072a1e1bb874d0e4d7a5ffaa99dac5b0150ffc` |
| `ai_new.jsonl` (32 dòng) | `10bd5298673a14253c63da962d81883523fc7e04415de5524bfb65ea5b8d97c7` |
| `zalo.jsonl` (36 dòng) | `e506a00acab2bf4150e9f37f783bc6bdfb1eea89b23b88f65cd7e12759aba4ad` |
| `manifest.jsonl` (gộp 3 file, 124 dòng) | `665219d8eca1d5fac963e6af7f91d66623f9026dafade277ad259049ce643828` |
| [`cohorts-adv06-protocol.json`](reports/cohorts-adv06-protocol.json) | `684d5783f525e0dc6b64d1f40a169f6e2757ca333dccdace4acd2c6550d86550` |
| [`cohorts-adv06-predictions.csv`](reports/cohorts-adv06-predictions.csv) | `4058ec61f9bcc53e5ce6eaafafe6b413a1b84fc0813bfd7c42a73480f9276796` |
| [`cohorts-adv06-robustness.json`](reports/cohorts-adv06-robustness.json) | Kết quả ADV-08, chưa QA độc lập |

Protocol đã dùng một lần (`.used.json` giữ trên máy Loan). Chạy lại phải tạo protocol mới. Lệnh đã chạy, từ checkout sạch của main:

```bash
python -m scripts.robustness_manifest cohort --name phone --dir <phone> --output phone.jsonl     # tương tự ai_new, zalo (--parent-manifest)
python -m scripts.analyze_robustness --protocol protocol.json --manifest manifest.jsonl --preflight --output preflight.json
python -m scripts.evaluate --robustness --manifest manifest.jsonl --model <e571>/model/clip_probe.joblib --model-manifest <e571>/manifest.json --protocol protocol.json --output predictions.csv
python -m scripts.analyze_robustness --protocol protocol.json --manifest manifest.jsonl --predictions predictions.csv --output robustness.json
```

## Hạn chế

- **Ít ảnh:** 56 / 32 / 36 ảnh, thấp hơn kế hoạch; khoảng tin cậy rộng.
- **Ít thiết bị:** ảnh điện thoại gần như chỉ từ iPhone 11. 10 ảnh không có EXIF nên chưa xác nhận được là ảnh tự chụp bằng camera.
- **12 ảnh AI lấy từ Google Images:** nhãn AI dựa trên nơi đăng tải, chưa xác minh được công cụ tạo; ảnh đã bị nén và thu nhỏ khi đăng.
- **Zalo:** 14 ảnh AI qua Zalo không phải bản Zalo của ảnh trong `ai_new`, và chỉ 1 ảnh thật có ảnh gốc, nên chưa đo được tỷ lệ đổi kết luận do Zalo nén.
- **Ảnh MPO** (ảnh chân dung iPhone) bị API từ chối vì API chỉ nhận JPEG và PNG; đây là định dạng iPhone hay gặp, nên là một phát hiện cho API.
- Không có ảnh từ máy Android, ảnh chụp đêm hay ảnh đã chỉnh sửa.
- **QA không kiểm được nội dung và nhãn ảnh**, vì ảnh không được chia sẻ. QA kiểm được: hash trong predictions khớp manifest và protocol, kết quả phân tích tính lại được từ `cohorts-adv06-predictions.csv`. Nhãn và việc lọc thông tin riêng tư dựa trên xác nhận của Loan.
