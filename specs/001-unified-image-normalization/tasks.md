---

description: "Task list: Đồng bộ chuẩn hóa ảnh giữa huấn luyện và API"
---

# Tasks: Đồng bộ chuẩn hóa ảnh giữa huấn luyện và API

**Input**: Design documents from `specs/001-unified-image-normalization/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/interfaces.md, quickstart.md

**Tests**: Có. Tiêu chí chấp nhận của spec yêu cầu test chứng minh `score()` gọi chuẩn hóa đúng một lần và đầu vào CLIP giống nhau giữa huấn luyện và API; test viết trước và phải thất bại trước khi cài đặt (trừ T006 kiểm hàm nền T005, chạy sau T005).

**Organization**: Nhóm theo user story. Mỗi task ghi người phụ trách (**Kiệt**, **Loan**, **Quang**, **Lực**) và lệnh kiểm chứng (`Kiểm chứng:`). Lệnh `ruff check .` và `pytest` chạy từ gốc repo.

## Trạng thái triển khai trong PR 15 ngày 05 tháng 11 năm 2026

PR ML KAN-16..20 có phần tích hợp liên quan spec 001. Bảng này ghi bằng chứng hiện có, không chuyển người phụ trách và không tự đánh dấu nghiệm thu các task của Loan/Lực.

| Task | Trạng thái và giới hạn |
|---|---|
| T005, T009–T011 | Đã có hàm chuẩn hóa, encode, score, extraction và kiểm manifest trong PR ML; chờ review. |
| T006–T008, T018, T020 | Có regression test trong `tests/test_ml_pipeline.py`, không đồng nghĩa hoàn tất toàn bộ task/test độc lập được chỉ định. Test recipe JPEG chỉ tái viết các lệnh Pillow trên ảnh tổng hợp, không chạy `prepare_data.py` cũ trên baseline thật. |
| T012 | Chưa có `data/processed_baseline.sha256` được Loan chụp/commit trước migration. Dữ liệu chạy ML ở thư mục riêng; chưa ghi đè `data/labels.csv` chính. |
| T013 | Chưa đối chiếu độc lập baseline thật từ commit cũ trên máy Lực. Không dùng test synthetic để tick task này. |
| T014, T015, T021 | Có adapter dùng normalize chung, version bắt buộc và phân loại ảnh loại trong PR; chờ Loan/Lực review. Ảnh hỏng/bomb tách `rejected_invalid.csv`, không ghi vào `rejected_small.csv`. |
| T016, T022 | Chưa có `scripts/check_normalization.py`, chưa đạt đối chiếu baseline hoặc kiểm kê toàn bộ dữ liệu thật. Checker tương lai cần tính cả `rejected_invalid.csv` và xử lý ảnh trùng, không mặc nhiên coi mọi ảnh raw nằm trong labels hoặc rejected_small. |
| T023, T024 | Đã chạy bộ ML riêng 9.708 ảnh và train trên manifest version 1; chưa phải nghiệm thu migration dữ liệu chính sau baseline của Loan hoặc thay bù KAN-34. |
| T026 | Chưa đổi gate metadata; vẫn chờ Loan/Lực xác nhận. Post metadata đều hằng, A_eff=0,50 không chứng minh hết shortcut. |
| T027 | Chưa có `scripts/jpeg_trace_check.py`; chưa đo JPEG ghost, chờ xác nhận phương pháp. Kết quả 95,68% validation vẫn có nguy cơ shortcut dung lượng/độ mịn/dấu vết JPEG. |
| T030 | Chưa có biên bản QA độc lập trên máy Lực. Bộ artifact bàn giao không thay thế nghiệm thu này. |

Chi tiết phạm vi chồng lấn và bằng chứng: [bàn giao ML](../../docs/ml-handoff.md), [truy vết thí nghiệm](../../docs/ml-reproducibility.md).

Cập nhật KAN-37/39/44/51 ngày 05/11: PR #15 và bản sửa test #16 đã merge. Đã rà soát module chuẩn hóa/score, bổ sung kiểm raw identity và embedding cache; có công cụ đánh giá GenImage bằng model khóa tại `models.evaluate`. Theo xác nhận của Kiệt, manifest phát hành chưa chốt, chưa mở model-test và chưa nghiệm thu T024. Xem [hồ sơ task ML](../../docs/ml-normalization-release.md). Các checkbox QA/baseline bên dưới không tự chuyển thành hoàn thành.

Theo đề nghị tiếp theo, nhánh ML có thêm `prepare_data --split-from` để giữ split của ảnh hợp lệ theo manifest 10.000, giữ raw và ghi riêng ảnh bị loại. Candidate 9.708 ảnh được tạo ngoài dữ liệu chính, 0 split lệch tham chiếu và 9.708 hash khớp baseline Loan mới merge. Candidate khác bộ QA dùng train trước đây và có lịch sử tiếp xúc holdout, nên T024/KAN-51 vẫn chờ chốt manifest/QA/audit/holdout. Loan/Lực review thay đổi tùy chọn split; chi tiết ở [ml-preserved-split.md](../../docs/ml-preserved-split.md).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: có thể chạy song song (khác file, không phụ thuộc task chưa xong)
- **[Story]**: US1 đến US5 theo `spec.md`
- Quy ước chạy script: `python -m scripts.<tên>` từ gốc repo (research R2)

## Quyết định đã chốt và mục chờ xác nhận

Hai mục sau đã chốt tại D05 trong [`docs/decisions/realcheck-baseline.md`](../../docs/decisions/realcheck-baseline.md), nên T025 không còn bị chặn:
- Giá trị máy đọc của `verdict`: `likely_real`, `uncertain`, `likely_ai`.
- Mã lỗi: ảnh không đọc được `INVALID_IMAGE` (400), ảnh quá nhỏ `IMAGE_TOO_SMALL` (422).

Hai điểm cần xác nhận trước khi làm task liên quan (research R8, R9): đổi `metadata_audit.py` từ cổng cứng sang cảnh báo (T026); phương pháp kiểm tra dấu vết nén (T027). Task đánh dấu `[CHỜ XÁC NHẬN]`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Để test chạy thật trên máy và trên CI

- [ ] T001 **Lực**: Tạo `requirements.txt` ở gốc repo (pillow==13.0.0, numpy==2.4.6, pytest, pytest-cov, ruff; cùng phiên bản với `scripts/requirements-data.txt` cho gói trùng) để job `test` của `.github/workflows/ci.yml` chạy pytest thật thay vì bỏ qua. Kiểm chứng: `pip install -r requirements.txt && ruff --version && pytest --version`
- [ ] T002 **Lực**: Thêm cấu hình pytest `pythonpath = .` trong `pytest.ini` ở gốc repo để test import được `models.normalize` (research R2). Kiểm chứng: `pytest --collect-only` không lỗi import
- [ ] T003 **Lực**: Sửa `.github/workflows/ci.yml` (cần Loan review theo CODEOWNERS): bước pytest chạy `pytest --cov=app --cov-fail-under=70` chỉ khi `app/` có file `.py`; khi `app/` chưa có mã thì chạy `pytest` không cổng coverage và in cảnh báo rõ "app/ chưa có mã, bỏ qua cổng coverage" (skip chỉ dành cho giai đoạn chưa có code, constitution III). Giữ bước kiểm tra tồn tại test và `requirements.txt`. Kiểm chứng: mở PR thử và đọc log GitHub Actions thấy đúng một trong hai chế độ, và `ci-ok` xanh khi test qua (chưa kiểm chứng hành vi coverage khi `app/` trống trước task này)
- [ ] T004 [P] **Loan**: Đổi lệnh chạy sang `python -m scripts.<tên>` trong `scripts/README.md` và `data/README.md`. Kiểm chứng: `grep -rn "python scripts/" scripts/README.md data/README.md` không còn kết quả

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Hàm chuẩn hóa chung mà mọi user story đều dùng

**⚠️ CRITICAL**: Chưa làm user story nào trước khi xong phase này

- [ ] T005 **Kiệt** (review: **Loan**): Tạo `models/normalize.py` theo `contracts/interfaces.md` mục C1: hằng `NORMALIZATION_VERSION` (chuỗi không rỗng), lỗi `ImageTooSmall` (mang kích thước gốc), kiểu `NormalizedImage` (`jpeg` bytes, `image` giải mã từ chính `jpeg`, `version`), hàm `normalize_image(image, resize=True)`. Thứ tự bước: `ImageOps.exif_transpose` → `convert("RGB")` → `ImageOps.fit` BICUBIC 256×256 → JPEG `quality=95` đúng một lần → giải mã lại từ bytes; ném `ImageTooSmall` khi cạnh ngắn < 256 và `resize=True`; `resize=False` chỉ bỏ `fit` và kiểm tra kích thước. Chỉ phụ thuộc Pillow, có type hint. Kiểm chứng: `ruff check . && ruff format --check . && python -c "import models.normalize"`

**Checkpoint**: Module chuẩn hóa import được; các user story bắt đầu

---

## Phase 3: User Story 1 - Cùng ảnh cho cùng đầu vào mô hình ở huấn luyện và API (Priority: P1) 🎯 MVP

**Goal**: Ảnh qua pipeline huấn luyện và qua API cho đầu vào CLIP giống hệt nhau.

**Independent Test**: Chuẩn hóa một ảnh bằng đường huấn luyện (đọc tệp đã ghi) và bằng đường API (trong bộ nhớ); đầu vào CLIP giống từng giá trị; ảnh mẫu theo `raw_path` trùng baseline `data/processed_baseline.sha256` (dữ liệu cũ, không so với `data/processed` sau khi ghi đè).

### Tests for User Story 1 (viết trước, phải thất bại trước khi cài đặt) ⚠️

- [ ] T006 [P] [US1] **Lực**: Viết `tests/test_normalize.py`: (a) `NormalizedImage.image` bằng kết quả giải mã `jpeg`; (b) `jpeg` trùng byte với cách làm hiện tại của `scripts/prepare_data.py` (tái tạo bằng chính các lệnh Pillow cũ trên ảnh tổng hợp); (c) cùng ảnh vào thì cùng `jpeg` ra; (d) ghim tham số: với một ảnh tổng hợp cố định, sha256 của `jpeg` được ghim cạnh `NORMALIZATION_VERSION` trong test, nên đổi bất kỳ tham số nào (kích thước, bộ lọc, chất lượng) làm hash đổi và test thất bại, buộc tăng version và cập nhật cặp ghim (constitution VI; hash phụ thuộc phiên bản Pillow, đã ghim trong `requirements.txt`). Ảnh tổng hợp bằng Pillow, không dùng dữ liệu thật. Kiểm chứng: `pytest tests/test_normalize.py` (chạy sau T005 để xác nhận hợp đồng hàm nền; T005 là nền của mọi story nên test này không cần thấy thất bại trước)
- [ ] T007 [P] [US1] **Lực**: Viết `tests/test_score_normalization.py`: với mock CLIP và bộ phân loại, khẳng định `score(image)` gọi `normalize_image` đúng một lần với `resize` mặc định, không nhận tham số `resize`, và đầu vào CLIP từ đường "đọc `jpeg` từ đĩa" bằng đầu vào từ đường API (độ lệch 0). Kiểm chứng: `pytest tests/test_score_normalization.py`
- [ ] T008 [P] [US1] **Lực**: Viết `tests/test_extract_features.py` (mock CLIP): manifest ghi đúng `norm_version`, `rows` và `labels_norm_version`; hàm tải đặc trưng từ chối khi `norm_version` của manifest khác `NORMALIZATION_VERSION`, khi khác `labels_norm_version`, hoặc khi `rows` khác số dòng `data/labels.csv`. Kiểm chứng: `pytest tests/test_extract_features.py`

### Implementation for User Story 1

- [ ] T009 [P] [US1] **Kiệt**: Tạo `models/clip_input.py` với MỘT hàm tiền xử lý CLIP dùng chung cho bước trích đặc trưng (M3) và `score()` (contracts C3). Kiểm chứng: `ruff check . && python -c "import models.clip_input"` (kiểm thử hành vi của hàm này nằm ở T007, chạy được sau T010)
- [ ] T010 [US1] **Kiệt**: Tạo `models/score.py`: `score(image) -> float` nhận ảnh gốc đã giải mã, gọi `normalize_image` đúng một lần, đưa `.image` qua `models/clip_input.py`, rồi bộ phân loại; trả số hữu hạn trong [0, 1] (AI = 1); từ chối chạy khi version trong model khác `NORMALIZATION_VERSION`; import PyTorch/`transformers` bên trong hàm nạp model (research R6). `ImageTooSmall` được truyền ra, không bắt. Kiểm chứng: `ruff check . && pytest tests/test_score_normalization.py` (phụ thuộc T005, T009)
- [ ] T011 [US1] **Kiệt**: Tạo `models/extract_features.py` (contracts C3b): đọc ảnh theo `data/labels.csv`, đưa từng ảnh qua hàm tiền xử lý CLIP dùng chung (`models/clip_input.py`), ghi `.npy` trong `data/features/` và `data/features/manifest.json` (`norm_version`, `rows`, `order`, `labels_norm_version`); cung cấp hàm tải đặc trưng kiểm manifest; KHÔNG tự resize hay nén ảnh. Bước huấn luyện PHẢI dùng hàm tải này. Kiểm chứng: `ruff check . && pytest tests/test_extract_features.py` (phụ thuộc T009, T010)
- [ ] T012 [US1] **Loan**: Chụp baseline dữ liệu chuẩn hóa hiện có TRƯỚC khi chạy T014 (chỉ đọc, KHÔNG đổi, ghi đè hay xóa dữ liệu): tạo `data/processed_baseline.sha256` gồm dòng chú thích `#` ghi commit cuối cùng chạm vào `scripts/prepare_data.py` (`git log -1 --format=%H -- scripts/prepare_data.py`), phiên bản Pillow (`python -c "import PIL; print(PIL.__version__)"`) và sha256 của `data/labels.csv`, rồi sha256 của mọi tệp `.jpg` trong `data/processed` sắp theo đường dẫn (`find data/processed -type f -name '*.jpg' | sort | xargs sha256sum`). Commit tệp này như `data/labels.csv` (khoảng 1 MB, chỉ là mã băm, không chứa ảnh, không bị `.gitignore`) và thêm một dòng vào `data/README.md` giải thích đó là metadata mã băm để người review không hiểu nhầm là commit dữ liệu. Kiểm chứng: `grep -v '^#' data/processed_baseline.sha256 | sha256sum -c -` báo mọi tệp OK; số dòng dữ liệu bằng số dòng `data/labels.csv` trừ 1
- [ ] T013 [US1] **Lực**: Đối chiếu độc lập baseline của Loan trên máy QA, trong thư mục riêng (không đụng repo hay dữ liệu của Loan): dựng bản sao mã cũ ở commit ghi trong dòng chú thích của baseline (`git archive <commit> | tar -x -C <thư mục riêng>`), tải dữ liệu thô bằng script của bản sao đó (~4 GB), chạy `prepare_data.py` cũ trong bản sao, rồi chạy `grep -v '^#' data/processed_baseline.sha256 | sha256sum -c -` từ gốc bản sao. Ghi biên bản số liệu thô (số tệp OK, FAILED, thiếu), cùng quy trình Q4 trước đây; mọi lệch đều ghi lý do. Giữ thư mục riêng và ghi đường dẫn `data/raw` của nó vào biên bản để T016 dùng qua `--raw-dir`; dữ liệu thô KHÔNG được chép vào repo. Kiểm chứng: biên bản nêu số tệp khớp trên tổng (phụ thuộc T012)
- [ ] T014 [US1] **Loan**: Sửa `scripts/prepare_data.py` để import `models.normalize`: ghi `NormalizedImage.jpeg` ra `data/processed`, thêm cột `norm_version` vào `labels.csv` (thêm ở cuối, giữ nguyên thứ tự cột hiện có), truyền `resize=False` cho ảnh CIFAKE, tính mã băm loại ảnh trùng trên `image` sau nén (research R3). Cùng task này, vì `normalize_image` ném `ImageTooSmall` cho ảnh GenImage cạnh ngắn < 256 px: bắt `ImageTooSmall`, không ghi ảnh vào `data/processed` và `labels.csv`, ghi bản ghi vào `data/processed/rejected_small.csv` (cột `raw_path, source, width, height, reason, norm_version` theo `data-model.md`) và in số ảnh bị loại theo source cuối lần chạy, để script không sập (phần ảnh quá nhỏ của US3 được gộp vào đây). KHÔNG chạy `python -m scripts.prepare_data` (lệnh ghi đè `data/processed` và `labels.csv`) trước khi `data/processed_baseline.sha256` đã được chụp và commit (T012). Kiểm chứng: `ruff check . && python -m scripts.prepare_data` thoát mã 0 (phụ thuộc T005, T012)
- [ ] T015 [US1] **Loan**: Sửa `scripts/check_data.py`: thêm `norm_version` vào `COLUMNS` để `check_schema` chấp nhận cột mới. Kiểm chứng: `python -m scripts.check_data` thoát mã 0 (phụ thuộc T014)
- [ ] T016 [US1] **Lực**: Tạo `scripts/check_normalization.py` nhận `--raw-dir <thư mục đóng vai trò data/raw>` (mặc định `data/raw`; thư mục không tồn tại hoặc thiếu ảnh cần so thì thoát mã khác 0 và nêu rõ đường dẫn đã thử, không tự giả định, không bỏ qua): lấy mẫu ảnh (ghép đường dẫn ảnh đã chuẩn hóa với `raw_path` bằng `data/labels.csv`, thay tiền tố `data/raw` bằng `--raw-dir`; cột `raw_path` không đổi sau T014 với ảnh còn lại), chuẩn hóa lại bằng `models.normalize.normalize_image`, so sha256 của `jpeg` với dòng tương ứng trong `data/processed_baseline.sha256`; KHÔNG so với `data/processed` hiện tại vì T014 ghi đè nó (nếu so thì luôn khớp, không chứng minh gì); thoát mã khác 0 nếu có ảnh mẫu không trùng (SC-003). Dữ liệu thô không có sẵn trên mọi máy: Lực chạy với `--raw-dir` trỏ tới dữ liệu do T013 tải (ngoài repo), Loan chạy với `data/raw` của mình. Kiểm chứng: `python -m scripts.check_normalization --raw-dir <thư mục dữ liệu thô của T013>` thoát mã 0 (phụ thuộc T005, T012, T013; không phụ thuộc T014)
- [ ] T017 [US1] **Quang**: Trong `app/main.py` (tạo nếu chưa có theo B1/B2): giải mã ảnh upload đúng một lần, đọc EXIF (hãng, model máy) từ ảnh gốc đó, gọi `score(ảnh_gốc)`; KHÔNG resize hay nén ảnh trong `app/`. Phần từ chối ảnh hỏng/quá nhỏ **không** làm ở task này (xem T025). Kiểm chứng: `ruff check . && pytest` (phụ thuộc T010)

**Checkpoint**: Đầu vào CLIP giống nhau giữa huấn luyện và API; ảnh mẫu trùng baseline dữ liệu cũ

---

## Phase 4: User Story 2 - Ảnh lớn (điện thoại ~4000 px) ra đúng kích thước và chất lượng (Priority: P1)

**Goal**: Ảnh 4000×3000 ra 256×256, nén đúng một lần ở chất lượng 95, có xoay theo orientation.

**Independent Test**: Chuẩn hóa ảnh tổng hợp 4000×3000 (có và không có cờ orientation), kiểm tra kích thước, số lần nén và chất lượng.

### Tests for User Story 2 ⚠️

- [ ] T018 [P] [US2] **Lực**: Viết `tests/test_normalize_large.py`: (a) ảnh 4000×3000 cho `image` 256×256; (b) bảng lượng tử của `jpeg` khớp JPEG chất lượng 95 (ví dụ `quantization[0][0] == 2`); (c) `save` JPEG được gọi đúng một lần (bao hàm bằng cách bọc/giả lập); (d) ảnh có cờ orientation (vd. 6) được xoay trước khi resize, cạnh ngắn tính sau xoay. Kiểm chứng: `pytest tests/test_normalize_large.py`

### Implementation for User Story 2

- [ ] T019 [US2] **Kiệt**: Chạy `pytest tests/test_normalize_large.py`; nếu thất bại, sửa `models/normalize.py` (không thêm bước resize/nén ngoài đặc tả). Cập nhật `models/README.md` ghi các tham số cố định (BICUBIC, chất lượng 95, 256×256, xoay theo EXIF). Kiểm chứng: `ruff check . && pytest tests/test_normalize_large.py` (phụ thuộc T005, T018)

**Checkpoint**: US1 và US2 đều chứng minh được bằng test

---

## Phase 5: User Story 3 - Ảnh quá nhỏ được tách riêng, có ghi lý do (Priority: P2)

**Goal**: Ảnh cạnh ngắn < 256 px không bị phóng to; GenImage bị loại khỏi dữ liệu chuẩn hóa và ghi lý do; API từ chối; CIFAKE giữ 32×32.

**Independent Test**: Chuẩn hóa ảnh 255 px và 256 px; chạy `prepare_data` và kiểm tra mọi ảnh bị loại đều có bản ghi lý do.

### Tests for User Story 3 ⚠️

- [ ] T020 [P] [US3] **Lực**: Viết `tests/test_too_small.py`: cạnh ngắn 255 thì `normalize_image` ném `ImageTooSmall` (mang kích thước gốc) và không có đầu ra; cạnh ngắn 256 thì qua; ảnh 32×32 với `resize=False` giữ nguyên 32×32 và không bị loại; không có phóng to ở mọi trường hợp. Kiểm chứng: `pytest tests/test_too_small.py`

### Implementation for User Story 3

- [ ] T021 [US3] **Loan**: Kiểm chứng đầu ra ảnh quá nhỏ của T014: chạy `python -m scripts.prepare_data`, xác nhận số dòng `data/processed/rejected_small.csv` khớp số ảnh in ra và không ảnh nào trong đó còn xuất hiện trong `data/labels.csv`; ghi bảng số ảnh bị loại theo source vào mô tả PR. Kiểm chứng: `python -m scripts.prepare_data` rồi `python -c "import pandas as pd; r=pd.read_csv('data/processed/rejected_small.csv'); l=pd.read_csv('data/labels.csv'); print(len(r), set(r.raw_path)&set(l.raw_path))"` in `N set()` (tập giao rỗng) (phụ thuộc T014)
- [ ] T022 [US3] **Lực**: Mở rộng `scripts/check_normalization.py`: mỗi ảnh trong thư mục dữ liệu thô (`--raw-dir`) hoặc có mặt trong `labels.csv` hoặc có bản ghi trong `rejected_small.csv`, không ảnh nào ở cả hai nơi và không ảnh nào mất (SC-004). Kiểm chứng: `python -m scripts.check_normalization --raw-dir <thư mục dữ liệu thô>` thoát mã 0 (phụ thuộc T016, T021)
- [ ] T023 [US3] **Loan**: Chạy lại `python -m scripts.prepare_data`, xác nhận ảnh bị loại và tổng số dòng `labels.csv`; cập nhật `data/README.md` (số ảnh bị loại, ghi rõ việc thay bù thuộc KAN-34, cảnh báo cân bằng lớp tới khi bù xong). Lưu ý phép chia `genimage_real` và `genimage_sd14` có thể đổi (research R11) nên đặc trưng và baseline cũ phải tạo lại. Kiểm chứng: `python -m scripts.check_data` (chấp nhận cảnh báo cân bằng) (phụ thuộc T021)
- [ ] T024 [US3] **Kiệt**: Sau T023, báo cho nhóm đặc trưng CLIP (M3) và model (M4) tạo từ dữ liệu cũ không còn dùng được; trích lại đặc trưng bằng `python -m models.extract_features` (ghi `data/features/manifest.json`) và train lại bằng bước huấn luyện của Kiệt (M4, ngoài phạm vi tính năng này, không có script mới ở đây): bước đó PHẢI tải đặc trưng bằng hàm tải kiểm manifest của `models/extract_features.py`, và ghi `NORMALIZATION_VERSION` vào metadata của `models/clip_probe.joblib`. Kiểm chứng: nạp model, xác nhận `score()` chạy với version khớp và hàm tải đặc trưng từ chối manifest có version lệch (phụ thuộc T011, T023)
- [ ] T025 [US3] **Quang**: Trong `app/main.py`: bắt `ImageTooSmall` và từ chối ảnh quá nhỏ kèm thông báo nêu lý do và kích thước tối thiểu 256 px; từ chối ảnh không giải mã được. Dùng mã lỗi theo D05. Viết kèm test API trong `tests/test_api_reject.py`. Kiểm chứng: `ruff check . && pytest tests/test_api_reject.py` (phụ thuộc T017)

**Checkpoint**: Ảnh quá nhỏ được xử lý có dấu vết; API từ chối chờ mã lỗi

---

## Phase 6: User Story 4 - Kiểm tra metadata, ghi khoảng tin cậy (Priority: P2)

**Goal**: Báo AUROC kèm khoảng tin cậy; vượt 0.55 là cảnh báo, không tự chặn.

**Independent Test**: Chạy phép kiểm tra trên dữ liệu đã chuẩn hóa; kết quả có AUROC, khoảng tin cậy và trạng thái đạt/cảnh báo.

- [ ] T026 [US4] [CHỜ XÁC NHẬN] **Loan** (review: **Lực**): Sửa `scripts/metadata_audit.py`: giữ tính `A_eff` và khoảng tin cậy bootstrap 95%, nhưng khi `A_eff` > 0.55 chỉ in cảnh báo rõ, ghi trạng thái `đạt`/`cảnh báo` vào `data/metadata_audit.json` và thoát mã 0 (research R8); cập nhật mô tả "gate" trong `scripts/README.md`. Chỉ làm sau khi Loan và Lực xác nhận đổi hành vi đã merge. Kiểm chứng: `python -m scripts.metadata_audit` in AUROC, khoảng tin cậy và trạng thái theo slice (phụ thuộc T021)

**Checkpoint**: Báo cáo metadata có khoảng tin cậy và cảnh báo thay vì cổng cứng

---

## Phase 7: User Story 5 - Kiểm tra dấu vết nén nhiều lần còn trong pixel (Priority: P3)

**Goal**: Báo mức dấu vết nén JPEG nhiều lần theo từng nguồn trên ảnh đã chuẩn hóa.

**Independent Test**: Chạy kiểm tra trên một mẫu ảnh đã chuẩn hóa của cả hai lớp; nhận bảng số đo theo từng nguồn.

- [ ] T027 [US5] [CHỜ XÁC NHẬN] **Lực**: Tạo `scripts/jpeg_trace_check.py` đo, trên một mẫu ảnh đã chuẩn hóa mỗi source, độ chênh pixel khi nén lại ở nhiều mức chất lượng (kỹ thuật "JPEG ghost", research R9), in bảng theo source; chỉ báo cáo, KHÔNG có ngưỡng đạt/không đạt. Chỉ làm sau khi nhóm xác nhận phương pháp. Kiểm chứng: `ruff check . && python -m scripts.jpeg_trace_check` in bảng đủ 6 source (phụ thuộc T023)

**Checkpoint**: Có số đo dấu vết nén theo từng nguồn để QA xem xét

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Tài liệu, CI và kiểm chứng độc lập

- [ ] T028 [P] **Lực**: Cập nhật `tests/README.md` (danh sách test mới) và, khi các task trên xong, `scripts/README.md` (thêm `check_normalization.py`, `jpeg_trace_check.py`). Kiểm chứng: `grep -n "check_normalization\|jpeg_trace_check" scripts/README.md`
- [ ] T029 **Lực**: Mở PR cho các task xong và xác nhận trong log GitHub Actions rằng bước pytest **thực sự chạy** (không bị bỏ qua) và `ci-ok` xanh; sau đó thêm `ci-ok` làm required check trong Ruleset. Kiểm chứng: log lượt chạy hiển thị `pytest ... passed`; không có dòng "skipping" (phụ thuộc T001, T002, T003, T006 trở đi)
- [ ] T030 **Lực**: Chạy độc lập toàn bộ `quickstart.md` các bước 1 đến 5 trên máy QA, so với bản đã chuẩn hóa của Loan (cùng quy trình Q4 trước đây), ghi biên bản số liệu thô. Kiểm chứng: `ruff check . && pytest && python -m scripts.check_normalization --raw-dir <thư mục dữ liệu thô> && python -m scripts.check_data` (phụ thuộc T016, T022, T023)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: bắt đầu ngay; T004 độc lập với T001, T002
- **Foundational (Phase 2)**: T005 chặn mọi user story
- **US1 và US2 (P1)**: bắt đầu sau T005, có thể song song (khác file)
- **US3 (P2)**: cần T005 và T014 (cùng file `prepare_data.py`, phải làm tuần tự T014 → T021)
- **US4, US5**: cần dữ liệu đã chuẩn hóa từ T021/T023; còn chờ xác nhận
- **Polish**: sau khi các story mong muốn xong

### Thứ tự theo người (theo yêu cầu phân công)

1. **Module chung** (Kiệt + Loan): T005
2. Song song: **prepare_data** (Loan: T012 trước, rồi T014, T015, T021, T023) và **score() cùng trích đặc trưng** (Kiệt: T009, T010, T011)
3. **API** (Quang): T017, rồi T025
4. **Test và file tạm** (Lực): T001 đến T003 (CI), T006, T007, T008, T018, T020 viết trước; T013 (song song, cần tải dữ liệu thô) rồi T016, T022, T028 đến T030 sau

### Within Each User Story

- T014 chỉ chạy sau khi baseline (T012) đã commit; T016 so với baseline, không so với `data/processed` sau T014 (I9)
- Test (T006, T007, T008, T018, T020) viết và thấy thất bại trước khi cài đặt
- Hàm chung (T005) trước script và `score()`; script và `score()` trước API

### Parallel Opportunities

- T004 song song với T001, T002
- T006, T007, T008 song song (khác file, đều chỉ cần T005 để chạy xanh)
- T009 song song với T014 (Kiệt và Loan, khác file)
- T018 song song với T006, T007; T020 song song với T018

---

## Parallel Example: User Story 1

```bash
# Viết test US1 cùng lúc (khác file):
Task: "tests/test_normalize.py (Lực)"
Task: "tests/test_score_normalization.py (Lực)"
Task: "tests/test_extract_features.py (Lực)"

# Sau T005, Kiệt và Loan làm song song:
Task: "models/clip_input.py, models/score.py rồi models/extract_features.py (Kiệt)"
Task: "scripts/prepare_data.py (Loan)"
```

---

## Implementation Strategy

### MVP First (User Story 1 và 2)

1. Setup (T001 đến T004) và Foundational (T005)
2. US1 (T006 đến T017): đầu vào CLIP giống nhau, ảnh mẫu trùng baseline dữ liệu cũ (`data/processed_baseline.sha256`)
3. US2 (T018, T019): ảnh lớn và orientation
4. **DỪNG và kiểm chứng**: `ruff check . && pytest && python -m scripts.check_normalization` `--raw-dir <thư mục dữ liệu thô>`

### Incremental Delivery

1. MVP ở trên
2. US3 (T020 đến T024) rồi T025 khi mã lỗi đã chốt
3. US4 và US5 sau khi nhóm xác nhận (T026, T027)
4. Polish (T028 đến T030)

### Notes

- `data/processed` và `labels.csv` đổi sau T014/T023; đặc trưng và model cũ phải tạo lại (T024)
- Bước huấn luyện (M4) không thuộc tính năng này: chỉ ràng buộc dùng hàm tải đặc trưng kiểm manifest (T024)
- Không implement `[CHỜ XÁC NHẬN]` (T026, T027) khi nhóm chưa đồng ý
- Mỗi PR cần một người khác tác giả review và CI xanh với pytest chạy thật (constitution)
