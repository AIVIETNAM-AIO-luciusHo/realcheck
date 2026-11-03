# RealCheck Constitution

## Nguồn chuẩn và cách áp dụng

Constitution quy định kiến trúc và tiêu chí kỹ thuật cho RealCheck: API nhận một
ảnh để phân biệt **Ảnh thật / Ảnh AI / Chưa chắc**, kèm điểm và lý do. Các từ
**PHẢI**, **KHÔNG ĐƯỢC** là yêu cầu bắt buộc; **NÊN** cho phép ngoại lệ có lý do
được ghi trong plan/PR.

Nguồn quyết định yêu cầu dự án:

1. `docs-local/final_realcheck (3).pdf`, mục 1–6: kế hoạch chính, kiến trúc,
   phân công, QA và đánh giá.
2. `docs/technical-report/report.tex` và bản PDF
   `docs/technical-report/RealCheck_Technical_Report_Week1.pdf`: phạm vi tuần 1,
   trạng thái thực tế, các điểm chưa chốt; không biến kết quả dự kiến thành số đo.
3. `docs/test-plan.md`, `docs/bug-report-template.md`, `docs/README.md`: test case,
   quy trình báo lỗi và ngôn ngữ tài liệu.
4. `README.md`, README từng thư mục, `.github/workflows/ci.yml` và
   `.github/CODEOWNERS`: cấu trúc, công cụ và quy trình cộng tác hiện có.

`docs-local` còn chứa sách AI Engineering, AI, Deep Learning, NLP, tài liệu
FastAPI, mẫu LaTeX, báo cáo KNN/PCA/LDA (`Technical_Report.pdf`) và dự án
`IS402.R11-ecommerce-realtime-data-pipeline`. Đây là tài liệu tham khảo, không
phải đặc tả RealCheck. KHÔNG ĐƯỢC đưa Kafka, Azure, database, KNN, LLM hay các
thành phần của tài liệu khác vào kiến trúc chỉ vì chúng nằm trong thư mục này.
Các file `.sty`, hình/logo và mẫu báo cáo chỉ phục vụ trình bày.

Khi tài liệu khác nhau, PHẢI phân biệt yêu cầu toàn dự án, yêu cầu từng giai đoạn
và trạng thái đã thực hiện. Thay đổi yêu cầu PHẢI ghi nguồn, lý do và được review;
không âm thầm giải quyết mâu thuẫn bằng một giả định triển khai.

## Core Principles

### I. Kiến trúc đơn giản, hợp đồng rõ ràng

- Stack chuẩn: Python 3.11 (theo CI hiện tại), FastAPI + Uvicorn, Pydantic,
  Pillow, `transformers` cho CLIP và scikit-learn cho Logistic Regression.
  PHẢI khai báo dependency và cách dựng môi trường chạy lại được; đổi phiên bản
  Python phải đồng bộ local, Docker và CI.
- Luồng phục vụ: người dùng/Streamlit → Nginx → FastAPI → `score(image)` →
  kết quả JSON. Locust gọi qua Nginx từ máy khác. Streamlit KHÔNG gọi model trực tiếp.
- Luồng suy luận: ảnh gốc → đọc EXIF → hàm chuẩn hóa chung (nguyên tắc VI) →
  preprocessing CLIP 224×224 → CLIP ViT-B/32 giữ nguyên trọng số → vector 512
  chiều → Logistic Regression → điểm AI → ngưỡng verdict.
  KHÔNG huấn luyện lại CLIP hoặc thay mô hình nền nếu chưa có quyết định đổi kiến trúc.
- `app/` chịu trách nhiệm HTTP, validation, schema, EXIF và tạo phản hồi;
  `models/` cung cấp `score(image) -> float` và artifact
  `models/clip_probe.joblib`. Mã model KHÔNG phụ thuộc FastAPI hoặc Streamlit.
  Route KHÔNG chứa logic huấn luyện hay pipeline dữ liệu.
- Endpoint core: `POST /v1/analyze`, `GET /health`, `GET /docs`.
  `GET /metrics` phục vụ Prometheus ở giai đoạn nâng cao.
- Phản hồi phân tích PHẢI có `verdict`, `score`, `exif`, `reason`, được mô tả
  bằng schema Pydantic/OpenAPI. Đổi hợp đồng PHẢI cập nhật tài liệu và test trong
  cùng PR, nêu ảnh hưởng tới bên gọi.

### II. Kết luận mô hình và dữ liệu phải trung thực

- Nhãn chuẩn: `real = 0`, `ai = 1`; điểm càng gần 1 càng giống ảnh AI.
  `score(image)` PHẢI trả số hữu hạn trong `[0, 1]`; không trả NaN/Infinity hoặc
  che lỗi suy luận bằng điểm giả.
- Ngưỡng khởi đầu: `score < 0.3` → **Ảnh thật**;
  `0.3 <= score <= 0.7` → **Chưa chắc**; `score > 0.7` → **Ảnh AI**.
  Hai biên thuộc vùng Chưa chắc. Ngưỡng PHẢI được cấu hình thống nhất và chỉ
  hiệu chỉnh trên validation, KHÔNG chọn trên test.
- EXIF chỉ là bằng chứng phụ, KHÔNG quyết định hoặc ghi đè verdict. Thiếu EXIF
  KHÔNG chứng minh ảnh là AI. PHẢI đọc EXIF từ ảnh gốc TRƯỚC khi chuẩn hóa, vì
  chuẩn hóa nén lại JPEG và làm mất EXIF. Thiếu thông tin máy chụp vẫn xử lý được;
  `exif` trả `Không có thông tin máy chụp`. `reason` PHẢI phù hợp với điểm và
  EXIF, không khẳng định kết quả chính xác 100%.
- CIFAKE chỉ dùng chạy thử luồng; GenImage là tập train/test chính. Không dùng
  kết quả CIFAKE để tuyên bố đạt mục tiêu Accuracy GenImage từ 90%.
- Quyết định dữ liệu (phương án A): GIỮ tập GenImage hiện có; KHÔNG thay hoặc
  thêm nguồn dữ liệu để xử lý thiên lệch. Thiên lệch được xử lý ở phần xử lý ảnh
  (nguyên tắc VI). Đổi quyết định này cần PR có lý do và review.
- `data/raw/` giữ ảnh gốc; `data/processed/` chứa ảnh GenImage đã chuẩn hóa JPEG
  256×256 theo cùng một hàm chuẩn hóa cho hai lớp; `data/features/` chứa đặc
  trưng; `data/labels.csv` PHẢI có `filepath,label,source,split`.
  Ngoại lệ duy nhất: ảnh CIFAKE (chỉ dùng chạy thử luồng) được miễn bước
  resize/cắt và giữ 32×32, vẫn qua cùng hàm chuẩn hóa (xoay, RGB, JPEG một lần).
  Ảnh GenImage có cạnh ngắn dưới 256 px KHÔNG được phóng to: bị loại khỏi
  dữ liệu đã chuẩn hóa kèm bản ghi lý do.
- Pipeline PHẢI chạy lại được: ghi seed, tham số chuẩn hóa, tỷ lệ chia tập và
  nguồn dữ liệu. KHÔNG để cùng ảnh xuất hiện ở nhiều split, kiểm tra cả đường
  dẫn lẫn nội dung/hash. Không dùng tập test để train hoặc chọn tham số.
- PHẢI đánh giá baseline chỉ dùng dung lượng file. Nếu cao hơn rõ rệt mức 50%
  trên dữ liệu cân bằng, PHẢI điều tra và sửa thiên lệch trước khi chấp nhận
  kết quả model; chưa có ngưỡng số học cụ thể để tự động nghiệm thu baseline.
- Mỗi bộ đánh giá PHẢI báo Accuracy theo từng `source` (không chỉ con số gộp),
  kèm AUROC, Precision, Recall, confusion matrix và tỷ lệ Chưa chắc; với ảnh điện
  thoại thật PHẢI báo thêm FPR (tỷ lệ gọi oan ảnh thật là ảnh AI). PHẢI công bố
  cách tính chỉ số khi có vùng Chưa chắc; không âm thầm loại các mẫu này để làm
  đẹp kết quả. Chỉ nêu kết quả đã đo; mục tiêu và số đo thực tế phải ghi riêng,
  chưa đo thì ghi "chưa đo".

### III. Testing là điều kiện nghiệm thu bắt buộc

- Khi nghiệm thu core, PHẢI có ít nhất **15 test pytest** cho API, model và dữ
  liệu; coverage **`app/ >= 70%`**, kiểm bằng
  `pytest --cov=app --cov-fail-under=70`. Số lượng test không thay thế việc kiểm
  tra hành vi; không tạo test hình thức để đủ chỉ tiêu.
- Tuần 1 cho phép bộ test đầu tiên chưa đủ 15; đây là mốc tiến độ, không miễn
  tiêu chí nghiệm thu core. Test mới hoặc sửa lỗi PHẢI có ca kiểm tra hành vi
  tương ứng; khi sửa lỗi NÊN có regression test tái hiện được lỗi cũ.
- Unit test PHẢI kiểm tra quy tắc ngưỡng, hai biên 0.3/0.7, miền điểm, EXIF và
  xử lý lỗi. Test HTTP dùng mock model/CLIP để CI không phải tải trọng số nặng;
  mock không được thay thế kiểm thử tích hợp với model thật trước nghiệm thu.
- Test hợp đồng API PHẢI bao phủ ảnh hợp lệ, đủ bốn trường, điểm `[0,1]`, thiếu
  file, file text giả `.jpg`, ảnh hỏng và ảnh thiếu EXIF. Dữ liệu đầu vào sai PHẢI
  bị từ chối bằng lỗi 4xx phù hợp, không thành verdict hoặc lỗi 500.
- `docs/test-plan.md` TC-01–TC-17 là nền cho test tuần 1. QA PHẢI kiểm tra schema
  CSV, nhãn, ảnh đọc được, chuẩn hóa, không trùng split, tính tái lập và baseline.
  Người làm pipeline dữ liệu KHÔNG tự là người duy nhất viết test/nghiệm thu
  dữ liệu của mình; QA phải review và chạy lại độc lập.
- Trước nghiệm thu server, PHẢI test ảnh có số pixel cực lớn, ảnh giả định dạng,
  giới hạn upload và rate limit; xác nhận lỗi 429 khi vượt tốc độ. Test Nginx
  cần chạy qua Nginx thật, không suy ra từ TestClient trong tiến trình.
- PHẢI đo độ bền khi xoay, cắt viền, thu nhỏ, chỉnh sáng; đánh giá JPEG chất
  lượng 90/70/50, ảnh qua Zalo, ảnh điện thoại thật và ảnh AI đời mới. Báo cáo
  thay đổi kết luận/suy giảm thực đo, không mặc định mọi biến đổi phải giữ verdict.
- Locust PHẢI có smoke, load, stress, soak từ máy khác, ghi p95, request/giây,
  tỷ lệ lỗi, cấu hình máy, số worker, tải và thời lượng. Mục tiêu p95/throughput
  chỉ chốt sau lần đo đầu, không tự gán SLO khi chưa có dữ liệu.
- GitHub Actions PHẢI chạy Ruff và pytest cho PR có mã thực thi/test. Lỗi test
  hoặc coverage dưới chuẩn PHẢI làm CI thất bại. Cơ chế skip của skeleton chỉ
  dành cho giai đoạn chưa có code/test; CI xanh do skip KHÔNG chứng minh đạt QA.

### IV. Code style thống nhất và dễ kiểm thử

- PHẢI vượt `ruff check .` và `ruff format --check .`, theo cấu hình Ruff chung
  của repo; không dùng `noqa` rộng hoặc bỏ qua lint để hợp thức hóa lỗi.
- Mã, định danh và commit viết tiếng Anh; tài liệu và chữ hiển thị UI/lý do cho
  người dùng viết tiếng Việt. Tên máy đọc của API theo schema đã thống nhất.
- Dùng `snake_case` cho hàm/biến/module, `PascalCase` cho lớp và `UPPER_SNAKE_CASE`
  cho hằng số. Hàm giao tiếp giữa các thành phần PHẢI có type hint và mô tả
  input/output, miền giá trị, lỗi và tác dụng phụ khi có.
- Tách xử lý HTTP, suy luận, dữ liệu và đánh giá theo trách nhiệm; ưu tiên hàm
  nhỏ, phụ thuộc có thể thay bằng mock. Không nhân bản ngưỡng/logic verdict ở
  API, UI và script. Không tạo tầng trừu tượng hoặc service mới thiếu nhu cầu cụ thể.
- PHẢI xử lý ngoại lệ dự kiến tại ranh giới thành phần; không bắt mọi lỗi rồi
  trả kết quả thành công. Log lỗi phải đủ để truy vết, không ghi secret hoặc
  toàn bộ nội dung ảnh/metadata cá nhân không cần thiết.
- Cấu hình môi trường và đường dẫn PHẢI được khai báo rõ; không hardcode secret,
  đường dẫn máy cá nhân hoặc endpoint server trong logic nghiệp vụ.
- Đổi cách chạy/input/output PHẢI sửa README liên quan trong cùng PR. Các quy
  tắc đặt tên, type hint và xử lý lỗi ở đây là chuẩn kỹ thuật được bổ sung bởi
  constitution, không phải trích nguyên văn từ PDF kế hoạch.

### V. Triển khai theo giai đoạn và bảo vệ tài nguyên

- Core: FastAPI, Streamlit, Docker, Nginx, pytest và Locust. Docker Compose điều
  phối các dịch vụ; Prometheus/Grafana chỉ thêm sau khi core chạy trên server
  và có số đo Locust. Grafana chỉ truy cập qua SSH tunnel theo kế hoạch.
- Nginx là cổng vào cho request người dùng và đo tải: giới hạn **10 request/giây
  mỗi IP**, upload tối đa **5 MB**, cấu hình rate-limit trả **429**. Phải phân
  biệt lỗi quá tốc độ với lỗi quá kích thước; mã lỗi upload cụ thể phải chốt trong
  hợp đồng, không mặc định mọi giới hạn đều là 429.
- Giới hạn dung lượng không thay thế kiểm tra giải mã ảnh/số pixel ở API.
  Không chỉ tin phần mở rộng file hoặc Content-Type do client gửi.
- Tuần 1: localhost, model/data ban đầu, API, Dockerfile, pytest đầu tiên và CI.
  Nginx/server, Locust, Streamlit và thí nghiệm nén thuộc các mốc sau tuần 1.
- ELA/heatmap, C2PA, Redis queue, ONNX và pipeline CD tự động chưa thuộc core.
  CI kiểm thử hiện có vẫn bắt buộc; việc kế hoạch để CI/CD ở giai đoạn sau
  không phải lý do bỏ GitHub Actions đang dùng.
- KHÔNG commit secret/`.env`, ảnh dữ liệu, đặc trưng `.npy` hoặc `models/*.joblib`.
  PHẢI hướng dẫn lấy artifact để tái lập. Dữ liệu chỉ dùng cho học tập, ghi nguồn
  CIFAKE/GenImage; tránh thu thập ảnh mặt người lạ.

### VI. Chuẩn hóa ảnh dùng chung, có version

- Huấn luyện và `score(image)` PHẢI dùng CHUNG MỘT hàm chuẩn hóa, không có hai
  bản cài đặt riêng cho train và suy luận. Các bước, theo đúng thứ tự: giải mã
  ảnh; chuyển RGB và xử lý hướng ảnh (orientation); resize cạnh ngắn rồi
  center-crop 256×256; nén JPEG đúng **một lần**; tiền xử lý CLIP.
- Hàm chuẩn hóa PHẢI có **version** rõ ràng. Version PHẢI được ghi cùng artifact
  `models/clip_probe.joblib` và cùng đặc trưng trích xuất; `score(image)` KHÔNG
  ĐƯỢC chạy khi version của model khác version của hàm chuẩn hóa hiện hành.
- Backend (`app/`) KHÔNG ĐƯỢC resize hoặc nén ảnh lần thứ hai ngoài hàm chuẩn hóa
  chung. Nginx/FastAPI chỉ giới hạn và kiểm tra đầu vào, không biến đổi pixel.
- Đổi bất kỳ tham số chuẩn hóa nào (kích thước, chất lượng JPEG, thuật toán
  resize, thứ tự bước) PHẢI tăng version, rồi trích lại đặc trưng và train lại
  mô hình. KHÔNG ĐƯỢC dùng đặc trưng hoặc model của version cũ cho kết quả mới.
- Lý do: train và suy luận khác cách xử lý ảnh làm điểm số lệch phân phối; ảnh
  bị nén hai lần tạo dấu vết mà mô hình có thể học nhầm thành dấu hiệu ảnh AI.

## Phạm vi trách nhiệm và giới hạn đặc tả

### Phân công hiện có

Bảng này xác định trách nhiệm phối hợp và hợp đồng bàn giao, không phải thiết kế
chi tiết cho các module ngoài phạm vi yêu cầu.

| Phạm vi | Phụ trách chính | Trách nhiệm và bàn giao |
|---|---|---|
| Data & Evaluation — `data/`, script dữ liệu/đánh giá | Loan | Pipeline tái lập, `labels.csv`, baseline, bộ đánh giá; bàn giao cho ML và QA |
| ML — `models/` | Kiệt | CLIP + Logistic Regression, artifact, `score(image)`, đề xuất ngưỡng validation |
| Backend & DevOps — `app/`, `nginx/`, Docker/server | Quang | Schema/API, tích hợp model, validation, đóng gói và bảo vệ tải |
| UI — `streamlit/` | Loan | Gọi API qua Nginx, trình bày kết quả và đánh giá |
| QA & Performance — `tests/`, `locust/` | Lực | Test độc lập, coverage, đo tải, bằng chứng lỗi và nghiệm thu |
| `scripts/`, `docs/`, `.github/` | Lực điều phối/review; người viết chịu phần mình; Quang phối hợp CI | Script tiện ích, tổng hợp báo cáo/demo, CI và quy trình review |

Owner thực hiện và reviewer là hai vai trò khác nhau. `.github/CODEOWNERS` quy
định người được yêu cầu review theo đường dẫn; không dùng bảng phân công để tự
bỏ qua review hoặc tự duyệt PR của mình.

### Quyết định kỹ thuật còn mở

PHẢI chốt trong spec/hợp đồng liên quan trước khi triển khai; không coi các mục
sau là giá trị mặc định đã được duyệt:

- Enum máy đọc đầy đủ của `verdict`: PDF mới ví dụ `likely_ai`; nhãn tiếng Việt
  không tự xác lập enum của hai trạng thái còn lại.
- Mã lỗi cụ thể cho thiếu file, file giả/hỏng, vượt dung lượng/pixel và schema lỗi;
  giới hạn số pixel; cách tính chính xác 5 MB và overhead multipart.
- Tỷ lệ train/validation/test và seed (kích thước chuẩn hóa 256×256 ở nguyên tắc
  VI; chất lượng JPEG 95 và bộ lọc BICUBIC đã chốt trong spec
  `001-unified-image-normalization`; preprocessing CLIP 224×224 là bước riêng).
- Ngưỡng số học nghiệm thu baseline dung lượng file; quy tắc tính chỉ số phân loại
  khi có Chưa chắc; mục tiêu p95/request mỗi giây sau baseline Locust.

## Quy trình phát triển và kiểm tra tuân thủ

Không push trực tiếp `main`. Dùng nhánh `ten/mo-ta-ngan`, PR vào `main`, commit
có tiền tố `feat:`, `fix:`, `docs:`, `chore:` hoặc `test:`. Mỗi PR PHẢI được
một người KHÁC tác giả review và approve; PHẢI có `ci-ok` xanh với test chạy thật
(không phải bị skip), README liên quan được cập nhật, và không chứa ảnh, `.npy`,
`models/*.joblib`, `.env`. Tài liệu viết tiếng Việt; code và commit tiếng Anh.

Trong `Constitution Check` của plan, PHẢI kiểm tra trước nghiên cứu và sau thiết
kế; PR kiểm tra lại các mục áp dụng:

- Phạm vi và owner rõ; không tự mở rộng module ngoài yêu cầu đã thống nhất.
- Kiến trúc, schema, nhãn, ngưỡng và vai trò EXIF đúng hợp đồng.
- Các quyết định mở liên quan đã chốt; thay đổi có tài liệu và test đi kèm.
- Có test hành vi, lint/format đạt; pytest thực sự chạy; nghiệm thu core đạt
  ít nhất 15 test và coverage `app/ >= 70%`.
- Dữ liệu được QA kiểm tra độc lập, không rò rỉ split; số đo có nguồn và tái lập.
- Thay đổi server có bằng chứng kiểm tra Nginx/Locust tương ứng; không coi test
  mock là bằng chứng chịu tải hoặc chất lượng model thật.
- Không có secret/dữ liệu/model nặng trong diff; README/hợp đồng đã cập nhật.

Báo lỗi dùng `docs/bug-report-template.md`: có bước tái hiện, mong đợi/thực tế,
môi trường, bằng chứng, mức độ và người phụ trách. Báo cáo phân biệt rõ **đã đo**,
**mục tiêu**, **chưa chạy**; không ghi thành công cho test bị skip.

## Governance

Constitution là chuẩn kỹ thuật cho spec, plan, task và review tiếp theo. Đây là
bản quy tắc đầu tiên, không xác nhận rằng skeleton hiện tại đã đáp ứng mọi gate.
Yêu cầu thay đổi phải được ghi bằng PR với lý do, ảnh hưởng, cách chuyển đổi và
review của người phụ trách liên quan; không dùng ngoại lệ ngầm để bỏ qua gate.

Version theo Semantic Versioning: MAJOR khi bỏ/đổi nguyên tắc không tương thích;
MINOR khi bổ sung nguyên tắc hoặc mở rộng quy tắc; PATCH khi làm rõ câu chữ không
đổi nghĩa. Khi sửa, PHẢI cập nhật Sync Impact Report, ngày sửa và kiểm tra các
Spec Kit template/tài liệu bị ảnh hưởng. Metadata `.constitution-template.json`
chỉ mô tả template nguồn, không phải nơi khai báo quy tắc dự án.

**Version**: 1.1.0 | **Ratified**: 2026-11-01 | **Last Amended**: 2026-11-03
