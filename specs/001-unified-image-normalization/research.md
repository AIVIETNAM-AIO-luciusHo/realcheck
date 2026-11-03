# Research: Đồng bộ chuẩn hóa ảnh giữa huấn luyện và API

Nguồn: đọc trực tiếp `scripts/prepare_data.py`, `scripts/check_data.py`, `scripts/metadata_audit.py`, `scripts/README.md`, `data/README.md`, `.github/workflows/ci.yml`, spec và constitution v1.1.0. Mục nào chưa chạy thử được ghi "chưa kiểm chứng".

## R1. Pipeline hiện tại và cách giữ ảnh đã chuẩn hóa trùng byte

- **Hiện trạng:** `process_one()` làm: `ImageOps.exif_transpose(im).convert("RGB")`, rồi với GenImage `ImageOps.fit(im, (256, 256), BICUBIC)`, rồi `im.save(out, "JPEG", quality=95)`. Không có ngưỡng nào, nên ảnh cạnh ngắn < 256 bị **phóng to**. CIFAKE không qua `fit`, chỉ lưu JPEG 95.
- **Phát hiện quan trọng:** `ImageOps.fit` cắt giữa rồi resize trong một bước lấy mẫu. "Resize cạnh ngắn về 256 rồi cắt giữa" theo nghĩa đen (hai bước) sẽ cho giá trị pixel hơi khác. Nếu viết lại theo hai bước thì ảnh mới sẽ **không trùng** `data/processed`, làm sai SC-003 và buộc chạy lại cả dữ liệu.
- **Decision:** dùng lại đúng các lệnh Pillow hiện có (`exif_transpose` → `convert("RGB")` → `ImageOps.fit` BICUBIC → JPEG `quality=95`, tham số lưu mặc định như cũ). Mô tả "resize cạnh ngắn rồi cắt giữa" trong spec được hiểu là kết quả, không phải thuật toán hai bước.
- **Rationale:** giữ nguyên ảnh đã có (kể cả ảnh Kiệt có thể đã trích đặc trưng) và chứng minh được SC-003 bằng so byte.
- **Alternatives:** (a) resize hai bước đúng nghĩa đen: bị loại vì đổi pixel; (b) đổi sang LANCZOS: đã bị loại ở Clarifications (câu 1).
- **Chưa kiểm chứng:** tính trùng byte giữa hàm mới và dữ liệu cũ; sẽ kiểm bằng `scripts/check_normalization.py` so với baseline sha256 (R12), không so với `data/processed` sau khi ghi đè.

## R2. Chỗ đặt module và cách import

- **Hiện trạng:** `models/` và `scripts/` chưa có `__init__.py` và repo chưa có `pyproject.toml`. `python scripts/prepare_data.py` đưa `scripts/` (không phải gốc repo) vào `sys.path`, nên `from models.normalize import ...` sẽ lỗi.
- **Decision:** đặt `models/normalize.py` (theo Clarifications), chạy script bằng `python -m scripts.prepare_data` từ gốc repo; thêm `pytest.ini` hoặc `pyproject.toml` với `pythonpath = .` cho test. Cả hai thư mục dùng được như namespace package (Python 3), không cần thêm `__init__.py`.
- **Rationale:** không thêm thư mục, không chèn `sys.path` trong script.
- **Alternatives:** (a) chèn `sys.path.insert` trong từng script: dễ vỡ; (b) cài repo thành package (`pip install -e .`): nặng hơn mức cần; (c) đặt module ở `scripts/`: bị loại ở Clarifications.
- **Hệ quả:** README của `scripts/` và `data/` phải đổi lệnh chạy (`python -m scripts.prepare_data`, ...), và các script dữ liệu hiện có (`check_data.py`, `baseline_filesize.py`, `metadata_audit.py`) nên chạy cùng cách cho thống nhất.

## R3. Giao diện hàm: trả về cả bytes và ảnh đã giải mã

- **Vấn đề:** huấn luyện đọc ảnh đã nén từ đĩa (giải mã lại JPEG), còn API chuẩn hóa trong bộ nhớ. Nếu API chỉ lấy ảnh trước khi nén thì đầu vào CLIP khác với huấn luyện (vi phạm SC-002).
- **Decision:** `normalize_image(image)` nén JPEG đúng một lần ra bytes, rồi giải mã chính bytes đó để trả ảnh. Trả về `NormalizedImage` gồm `jpeg` (bytes để ghi ra đĩa), `image` (ảnh giải mã từ `jpeg`) và `version`. `prepare_data.py` ghi `jpeg` ra đĩa; `score()` dùng `image`.
- **Rationale:** cả hai đường cùng đi qua một lần nén và cùng giải mã từ bytes đó, nên đầu vào CLIP giống hệt nhau.
- **Alternatives:** (a) API tự lưu rồi đọc lại tệp: tốn I/O, thêm tác dụng phụ; (b) chấp nhận khác biệt nhỏ: loại vì spec đòi độ lệch bằng 0.
- **Ảnh hưởng dedup:** mã băm loại ảnh trùng hiện tính trên pixel **trước** khi nén. Plan chuyển sang tính trên `image` sau nén. Hai ảnh trùng trước nén vẫn trùng sau nén; kết quả có thể lệch với số hiện tại ("0 ảnh trùng") rất hiếm gặp. Chưa kiểm chứng, sẽ so khi chạy lại.

## R4. Ghi version chuẩn hóa cùng dữ liệu

- **Decision:** hằng `NORMALIZATION_VERSION` trong `models/normalize.py` (giá trị khởi tạo do Kiệt đặt, ví dụ `"1"`); ghi thành cột `norm_version` của `data/labels.csv` và vào metadata của `models/clip_probe.joblib` (Kiệt, M4); `score()` từ chối chạy khi version model khác version hàm.
- **Rationale:** `labels.csv` được commit nên version nhìn thấy được trong PR; ảnh không commit nên không ghi được version vào đó. Đặc trưng `.npy` (cũng không commit) ghi version trong `data/features/manifest.json` cạnh chúng, do `models/extract_features.py` ghi và bước huấn luyện kiểm (đã chọn, constitution VI đòi version cùng đặc trưng trích xuất).
- **Alternatives:** (a) file phụ `data/processed/NORMALIZATION.json`: nằm trong thư mục bị `.gitignore`, không vào PR; (b) tên thư mục theo version: đổi đường dẫn toàn bộ; (c) đặc trưng trong `.npz` kèm version, hoặc tên tệp có version: đã loại cho đặc trưng (đổi định dạng hoặc dễ nhầm), chọn manifest riêng.
- **Hệ quả:** `scripts/check_data.py` kiểm đúng danh sách cột (`COLUMNS`), nên phải thêm `norm_version`. Cột này mở rộng schema ngoài `filepath,label,source,split` mà constitution yêu cầu tối thiểu (đã có thêm `raw_path`); không vi phạm.

## R5. Ngưỡng quá nhỏ, ảnh bị loại và ngoại lệ CIFAKE

- **Decision:** `normalize_image` ném `ImageTooSmall` khi cạnh ngắn < 256 (sau khi xoay theo orientation; cạnh ngắn không đổi khi xoay). `prepare_data.py` bắt lỗi, bỏ ảnh khỏi dữ liệu chuẩn hóa và ghi vào danh sách bị loại gồm `raw_path`, `source`, kích thước gốc, lý do, `norm_version`, đặt cạnh dữ liệu đã chuẩn hóa. In tổng số ảnh bị loại theo source.
- **CIFAKE:** tham số `resize: bool = True`. `prepare_data.py` truyền `resize=False` cho CIFAKE (bỏ `fit` và kiểm tra kích thước, vẫn xoay/RGB/JPEG 95). API và `score()` không bao giờ truyền tham số này.
- **Rationale:** vẫn là một hàm duy nhất; ngoại lệ CIFAKE phản ánh đúng hành vi hiện tại. Ngưỡng chỉ nằm một chỗ; API bắt `ImageTooSmall` thay vì tự kiểm lại kích thước.
- **Alternatives:** (a) hàm riêng cho CIFAKE: nhân đôi logic JPEG, trái FR-001; (b) tách CIFAKE khỏi dữ liệu: ngoài phạm vi (đổi dataset).
- **Rủi ro:** ai đó truyền `resize=False` vào đường API. Giảm thiểu bằng test khẳng định `score()` luôn dùng giá trị mặc định.
- **Vị trí danh sách bị loại:** thư mục `data/processed/` bị `.gitignore` chặn, nên danh sách không vào repo; tổng số được ghi trong `data/README.md` và báo cáo chạy. Chấp nhận vì đây là "file tạm".

## R6. `score(image)` và tiền xử lý CLIP

- **Decision:** `score(image: PIL.Image.Image) -> float` trong `models/score.py`: gọi `normalize_image` đúng một lần, đưa `.image` qua `models/clip_input.py` (tiền xử lý CLIP dùng chung với bước trích đặc trưng M3), rồi tới bộ phân loại. Import PyTorch/`transformers` ở bên trong hàm nạp model để test không cần cài PyTorch.
- **Rationale:** FR-007 đòi "cùng đầu vào CLIP" giữa huấn luyện và API; chỉ đạt được nếu trích đặc trưng và `score()` dùng chung một hàm tiền xử lý CLIP.
- **Chưa kiểm chứng:** tên tệp `clip_input.py` là đề xuất; Kiệt có thể đổi, miễn là một hàm dùng chung.

## R7. Luồng API (phần của Quang)

- **Decision:** API giải mã ảnh một lần (`Image.open` + `load`), từ chối nếu hỏng; đọc EXIF (hãng, model máy) từ **chính ảnh gốc** đó; gọi `score(ảnh_gốc)`; bắt `ImageTooSmall` và trả từ chối kèm thông báo.
- **Còn mở:** mã lỗi HTTP cụ thể và giá trị `verdict` (xem Technical Context). Task liên quan phải chờ chốt, theo constitution (mục Quyết định kỹ thuật còn mở).

## R8. Metadata audit: cổng cứng hay cảnh báo

- **Hiện trạng:** `scripts/metadata_audit.py` tính `A_eff = max(AUROC, 1-AUROC)`, có khoảng tin cậy bootstrap 95% (1.000 lần, seed 42) và **thoát mã 1** khi vượt 0.55; `scripts/README.md` gọi đây là gate.
- **Spec:** FR-009 coi 0.55 là ngưỡng cảnh báo, không tự động chặn.
- **Decision (đề xuất):** giữ phép tính và khoảng tin cậy, đổi hành vi: vượt 0.55 thì in cảnh báo rõ và vẫn thoát 0, ghi trạng thái trong JSON. Cần Loan/Lực xác nhận vì đây là thay đổi hành vi đã được merge.
- **Alternatives:** giữ cổng cứng; hoặc thêm cờ để chọn chế độ.

## R9. Kiểm tra dấu vết nén JPEG nhiều lần (FR-010)

- **Hiện trạng:** chưa có script nào làm việc này; spec không đặt ngưỡng đạt/không đạt.
- **Decision (đề xuất):** `scripts/jpeg_trace_check.py` đo, trên một mẫu ảnh đã chuẩn hóa mỗi source, độ chênh pixel khi nén lại ở nhiều mức chất lượng ("JPEG ghost"), rồi báo đường cong theo source, **chỉ báo cáo, không có ngưỡng**.
- **Rationale:** chỉ cần Pillow và NumPy, đủ nhẹ cho CI/QA; so sánh được ảnh thật (vốn là JPEG) với ảnh AI (vốn là PNG).
- **Alternatives:** phân tích biểu đồ hệ số DCT (cần giải mã hệ số, thêm thư viện); phát hiện lưới khối 8×8.
- **Chưa kiểm chứng:** hiệu quả của phương pháp này trên dữ liệu thật, và tài liệu nguồn của kỹ thuật chưa được tra lại; đây là đề xuất để Lực/Kiệt xác nhận trước khi viết tasks.

## R10. Test và CI chạy thật

- **Hiện trạng:** job `test` trong CI chỉ chạy pytest khi có cả `tests/test_*.py` **và** `requirements.txt`; repo chưa có `requirements.txt`, nên hiện bước pytest luôn bị bỏ qua.
- **Decision:** thêm `requirements.txt` ở gốc (Pillow, NumPy, pytest, pytest-cov, ruff, và các gói cần cho test mock) để bước pytest thực sự chạy; test dùng ảnh tổng hợp bằng Pillow (không phụ thuộc `data/raw`), mock CLIP/PyTorch.
- **Rationale:** nếu không, CI xanh do bỏ qua và không chứng minh gì (constitution III).
- **Đã chọn (G1):** cổng `--cov=app --cov-fail-under=70` chỉ bật khi `app/` có file `.py`; chưa có thì chạy pytest không cổng và in cảnh báo. Đã bỏ phương án đo `models/` thay `app/` và phương án chờ Quang có mã `app/`.
- **Hệ quả:** bật pytest trên CI sẽ lần đầu chạy `--cov=app --cov-fail-under=70` khi `app/` còn trống hoặc chưa có mã; cần Lực/Quang quyết định cách tính coverage trong giai đoạn này (chưa kiểm chứng hành vi CI).

## R11. Ảnh hưởng tới dữ liệu hiện có

- Ảnh còn lại giữ nguyên byte (mục tiêu của R1). ~292 ảnh thật nhỏ bị loại nên `genimage_real` giảm từ 3.000 xuống khoảng 2.708 cho tới khi KAN-34 bù lại.
- `assign_splits` dùng một bộ sinh số ngẫu nhiên chung, duyệt các source theo thứ tự chữ cái (`cifake_ai`, `cifake_real`, `genimage_glide`, `genimage_midjourney`, `genimage_real`, `genimage_sd14`). Đổi số ảnh `genimage_real` làm đổi trạng thái bộ sinh nên phép chia của `genimage_real` **và** `genimage_sd14` có thể đổi (suy từ đọc code, chưa chạy kiểm chứng); các source đứng trước không đổi.
- Hệ quả: `labels.csv`, đặc trưng và baseline đã tính phải tạo lại; `check_data.py` có thể cảnh báo cân bằng lớp (`check_balance`) cho đến khi KAN-34 hoàn tất.

## R12. Bảo toàn và kiểm chứng độc lập dữ liệu cũ (I9)

- **Vấn đề:** T012 ghi đè `data/processed` bằng hàm mới; so ảnh chuẩn hóa lại với `data/processed` sau đó luôn khớp (tự so với chính nó), nên không chứng minh hàm mới trùng dữ liệu cũ (SC-003). Máy QA không có `data/raw` hay `data/processed`; dữ liệu hiện tại chỉ nằm trên máy của Loan.
- **Decision:** trước T012, Loan chụp `data/processed_baseline.sha256` (sha256 từng ảnh, kèm commit mã nguồn cũ, phiên bản Pillow, sha256 `labels.csv`), chỉ đọc dữ liệu. T012 bị chặn cho đến khi file này có. Lực đối chiếu độc lập: dựng bản sao mã cũ ở commit ghi trong baseline bằng `git archive` vào thư mục riêng, chạy lại trên máy QA (như quy trình Q4), và xác nhận `sha256sum -c` khớp baseline. `scripts/check_normalization.py` so hàm mới với baseline.
- **Rationale:** mã băm nhỏ (~1 MB), commit được, không đụng dữ liệu thật, và chứng minh độc lập hai chiều (dữ liệu của Loan, và mã cũ chạy trên máy khác).
- **Alternatives:** (a) sao chép thư mục `data/processed` (tốn đĩa, chỉ ở máy Loan, không chia sẻ được); (b) T012 ghi sang thư mục mới rồi đổi tên (đổi đường dẫn trong `labels.csv` và nhiều script).
- **Rủi ro:** baseline ghi mã cũ theo "commit cuối cùng chạm vào `prepare_data.py`"; nếu dữ liệu của Loan được sinh bằng một phiên bản khác thì bước đối chiếu của Lực sẽ lộ ra (đó là mục đích). Cần tải lại ~4 GB dữ liệu thô trên máy QA (~17 phút theo lần chạy trước).
- **Quyết định về commit (nhóm):** `data/processed_baseline.sha256` được commit như `data/labels.csv`; luật "không commit dữ liệu" nhắm tới ảnh, `.npy`, `.joblib`, `.env`, và file này chỉ là mã băm. `data/README.md` ghi một dòng giải thích để người review không hiểu nhầm. Phương án gửi file ngoài repo đã bị loại.
- **Dữ liệu thô cho T016 (G9, nhóm chọn `--raw-dir`):** dữ liệu thô không có sẵn trên mọi máy và không nằm trong repo. `scripts/check_normalization.py` nhận `--raw-dir` (mặc định `data/raw`), dừng với thông báo rõ nếu thiếu, không tự giả định. Lực chạy với dữ liệu thô do T013 tải vào thư mục riêng ngoài repo; Loan chạy với `data/raw` của mình. Đã loại phương án symlink `data/raw` và phương án chạy trong bản sao của T013.
