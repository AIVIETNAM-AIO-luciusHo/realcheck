# Feature Specification: Đồng bộ chuẩn hóa ảnh giữa huấn luyện và API

**Feature Branch**: chưa tạo (đặt tên theo quy ước repo `ten/mo-ta-ngan`)

**Created**: 2026-11-03

**Status**: Draft

**Input**: User description: "Đồng bộ chuẩn hóa ảnh giữa pipeline huấn luyện và API RealCheck. Giữ dữ liệu GenImage, chỉ sửa xử lý ảnh."

Ghi chú đánh dấu: `[CẦN CHỐT]` là mục nhóm chưa quyết định; spec KHÔNG tự đặt giá trị cho các mục này. Danh sách đầy đủ ở mục "Mục chưa chốt".

## Bối cảnh

Dữ liệu huấn luyện đến từ nhiều nguồn có đặc điểm khác nhau: ảnh thật (ImageNet) là JPEG đã nén sẵn, ảnh AI gốc từ nhiều công cụ là PNG, kích thước gốc khác nhau; ảnh demo của người dùng là JPEG chụp bằng điện thoại cỡ ~4000 px. Nếu ảnh lúc huấn luyện và ảnh lúc API suy luận được xử lý theo hai cách khác nhau, điểm số của mô hình lệch phân phối; nếu ảnh bị nén nhiều lần, dấu vết nén cũ có thể bị mô hình học nhầm thành dấu hiệu "thật" hoặc "AI". Tính năng này làm cho hai đường xử lý ảnh trùng nhau tuyệt đối và kiểm chứng được điều đó.

## Clarifications

### Session 2026-11-03

- Q: Hàm chuẩn hóa chung dùng bộ lọc resize nào và chất lượng JPEG bao nhiêu? → A: BICUBIC và JPEG chất lượng 95 (giữ như pipeline hiện tại, khớp dữ liệu đã có trong `data/processed`).
- Q: Hàm chuẩn hóa có xoay ảnh theo orientation EXIF trước khi resize không? → A: Có, xoay trước khi resize, giống nhau ở huấn luyện và API.
- Q: Ảnh có cạnh ngắn dưới bao nhiêu pixel là "quá nhỏ", và CIFAKE có thuộc diện đó không? → A: Cạnh ngắn < 256 px là quá nhỏ: loại khỏi dữ liệu GenImage (thay bù ở KAN-34) và API từ chối kèm thông báo. CIFAKE là ngoại lệ, giữ 32×32 vì chỉ dùng để chạy thử luồng.
- Q (làm rõ câu trên): Ảnh GenImage quá nhỏ có còn ghi vào file tạm kèm lý do không? → A: Có, loại khỏi dữ liệu đã chuẩn hóa và ghi vào file tạm kèm lý do; việc thay bù ảnh thuộc KAN-34, ngoài phạm vi tính năng này.
- Q (làm rõ câu trên): Mã lỗi khi API từ chối ảnh quá nhỏ? → A: Giữ ở mục chưa chốt (mã lỗi); chỉ quy định từ chối kèm thông báo rõ lý do.
- Q: Hàm chuẩn hóa chung đặt ở thư mục nào và ai chịu trách nhiệm chính? → A: Đặt trong `models/`, Kiệt chịu trách nhiệm chính, Loan review; `scripts/prepare_data.py` import lại từ đó.
- Q: `score()` nhận đầu vào là gì? → A: Ảnh gốc đã giải mã (PIL Image), chưa chuẩn hóa; API giải mã một lần, đọc EXIF và kiểm tra lỗi trước khi gọi `score()`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Cùng một ảnh cho cùng một đầu vào mô hình ở huấn luyện và API (Priority: P1)

Là thành viên ML/QA, tôi cần chắc rằng một bức ảnh đi qua pipeline huấn luyện và đi qua API chấm điểm cho ra **cùng một đầu vào** cho mô hình, để điểm số khi chạy thật phản ánh đúng những gì mô hình đã học.

**Why this priority**: Đây là lý do tồn tại của tính năng; nếu hai đường lệch nhau thì mọi số đo mô hình đều không đáng tin.

**Independent Test**: Lấy một ảnh gốc, cho qua đường chuẩn hóa của huấn luyện và đường chuẩn hóa của API, so sánh đầu vào mô hình thu được; hai kết quả phải giống nhau từng giá trị.

**Acceptance Scenarios**:

1. **Given** một ảnh gốc trong dữ liệu, **When** ảnh được chuẩn hóa bởi pipeline huấn luyện và bởi API, **Then** hai đầu vào mô hình giống nhau hoàn toàn.
2. **Given** một ảnh mẫu truy theo `raw_path` trong `data/labels.csv`, **When** ảnh gốc được chuẩn hóa lại, **Then** mã băm sha256 của kết quả trùng với mã băm của ảnh tương ứng đã có trong `data/processed` trước khi tính năng này ghi đè dữ liệu (lưu trong `data/processed_baseline.sha256`).
3. **Given** một yêu cầu chấm điểm một ảnh, **When** API xử lý, **Then** bước chuẩn hóa được gọi đúng một lần cho ảnh đó.

---

### User Story 2 - Ảnh lớn (điện thoại ~4000 px) ra đúng kích thước và chất lượng chuẩn (Priority: P1)

Là người dùng demo, tôi gửi ảnh chụp bằng điện thoại cỡ 4000×3000 và cần hệ thống xử lý nó thành ảnh chuẩn 256×256 với đúng chất lượng đã quy định, giống hệt cách ảnh huấn luyện được xử lý.

**Why this priority**: Ảnh demo thực tế là ảnh lớn; nếu chuẩn hóa sai ở ảnh lớn thì kết quả demo không đại diện cho mô hình.

**Independent Test**: Chuẩn hóa một ảnh 4000×3000, kiểm tra kích thước đầu ra, số lần nén và chất lượng đầu ra.

**Acceptance Scenarios**:

1. **Given** một ảnh 4000×3000, **When** chuẩn hóa, **Then** đầu ra là 256×256, được cắt giữa sau khi đưa cạnh ngắn về 256, và chỉ trải qua một lần nén JPEG.
2. **Given** ảnh đầu ra, **When** kiểm tra chất lượng nén, **Then** chất lượng nén JPEG là 95.

---

### User Story 3 - Ảnh quá nhỏ được tách riêng, có ghi lý do (Priority: P2)

Là người làm dữ liệu, khi một ảnh gốc quá nhỏ để chuẩn hóa mà không phóng to, tôi cần ảnh đó được đưa vào một nơi tạm kèm lý do, thay vì bị phóng to hoặc bị loại bỏ mà không ai biết.

**Why this priority**: Phóng to ảnh làm đổi đặc trưng pixel; bỏ im lặng làm lệch tập dữ liệu mà không để lại dấu vết kiểm tra.

**Independent Test**: Đưa một ảnh nhỏ hơn ngưỡng vào chuẩn hóa; kiểm tra ảnh nằm ở nơi tạm, có bản ghi lý do, và không xuất hiện trong dữ liệu đã chuẩn hóa.

**Acceptance Scenarios**:

1. **Given** một ảnh GenImage có cạnh ngắn nhỏ hơn 256 px, **When** chuẩn hóa, **Then** ảnh không bị phóng to, được ghi vào file tạm kèm lý do, và không nằm trong dữ liệu đã chuẩn hóa.
2. **Given** một ảnh gửi qua API có cạnh ngắn nhỏ hơn 256 px, **When** API xử lý, **Then** API từ chối kèm thông báo nêu rõ lý do (mã lỗi cụ thể `[CẦN CHỐT]`) và không chấm điểm ảnh đó.
3. **Given** ảnh CIFAKE 32×32, **When** chạy luồng thử, **Then** ảnh được giữ nguyên 32×32 và không bị ngưỡng "quá nhỏ" loại bỏ.
4. **Given** một lần chạy chuẩn hóa toàn bộ dữ liệu, **When** có ảnh bị tách do quá nhỏ, **Then** báo cáo của lần chạy nêu số ảnh bị tách và lý do; không có ảnh nào biến mất mà không có bản ghi.

---

### User Story 4 - Kiểm tra metadata còn lộ nhãn, ghi khoảng tin cậy (Priority: P2)

Là QA, tôi cần một phép kiểm tra cho biết thông tin metadata của ảnh sau chuẩn hóa còn đoán được nhãn thật/AI hay không, với AUROC ≤ 0.55 là mức chấp nhận được và vượt mức đó là cảnh báo, kèm khoảng tin cậy.

**Why this priority**: Chuẩn hóa chỉ có ý nghĩa nếu loại được dấu hiệu định dạng; cần con số có khoảng tin cậy để quyết định, không chỉ một điểm.

**Independent Test**: Chạy phép kiểm tra trên dữ liệu đã chuẩn hóa; kết quả gồm AUROC, khoảng tin cậy và trạng thái đạt/cảnh báo so với 0.55.

**Acceptance Scenarios**:

1. **Given** dữ liệu đã chuẩn hóa, **When** chạy kiểm tra metadata, **Then** kết quả nêu AUROC và khoảng tin cậy của nó.
2. **Given** AUROC lớn hơn 0.55, **When** báo kết quả, **Then** kết quả được đánh dấu cảnh báo (không tự động chặn bàn giao).

---

### User Story 5 - Kiểm tra dấu vết nén nhiều lần còn trong pixel (Priority: P3)

Là QA, tôi cần biết dấu vết của các lần nén JPEG trước đó (ví dụ ảnh thật ImageNet vốn đã nén) có còn trong pixel của ảnh đã chuẩn hóa không, vì chỉ đưa ảnh về cùng chất lượng JPEG chưa chắc xóa hết dấu vết cũ.

**Why this priority**: Giá trị cao về chất lượng dữ liệu nhưng không chặn việc đồng bộ chuẩn hóa (P1); có thể làm sau khi đã đồng bộ.

**Independent Test**: Chạy phép kiểm tra trên một mẫu ảnh đã chuẩn hóa gồm cả hai lớp; kết quả báo mức dấu vết nén nhiều lần theo từng nguồn.

**Acceptance Scenarios**:

1. **Given** ảnh thật vốn là JPEG đã nén và ảnh AI vốn là PNG, **When** chạy kiểm tra dấu vết nén nhiều lần sau chuẩn hóa, **Then** kết quả được báo riêng cho từng nguồn để so sánh.

---

### Edge Cases

- Ảnh gốc có kênh trong suốt (alpha), bảng màu (palette), thang xám hoặc không gian màu khác RGB: được chuyển về cùng một dạng màu trước khi chuẩn hóa; cách xử lý nền trong suốt `[CẦN CHỐT]` chỉ khi nhóm thấy cần.
- Ảnh có cạnh ngắn đúng bằng 256: đủ điều kiện (không phải "quá nhỏ"); ảnh 255 px trở xuống là quá nhỏ và không được phóng to.
- Ảnh có tỷ lệ khung hình cực dài (ví dụ rất hẹp): cắt giữa có thể bỏ phần lớn nội dung; kết quả vẫn phải 256×256 nếu cạnh ngắn đạt 256 px, ngược lại bị coi là quá nhỏ.
- Ảnh có thông tin hướng (orientation) trong metadata: được xoay theo hướng đó trước khi resize; huấn luyện và API làm giống nhau.
- File không giải mã được thành ảnh: không đi vào chuẩn hóa; mã lỗi/phản hồi `[CẦN CHỐT]`.
- Ảnh đã là 256×256 JPEG: vẫn đi qua đúng một lần nén theo quy trình chung, không được bỏ qua bước để "tiết kiệm".

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Hệ thống MUST có đúng MỘT hàm chuẩn hóa ảnh, được dùng chung bởi pipeline chuẩn hóa dữ liệu (`scripts/prepare_data.py`) và bởi bước chấm điểm `score(image)`; không có bản cài đặt thứ hai. Hàm này MUST nằm trong `models/` (Kiệt chịu trách nhiệm chính, Loan review); `scripts/prepare_data.py` chỉ import lại, không sao chép logic.
- **FR-002**: Hàm chuẩn hóa MUST cho ra ảnh 256×256 bằng cách đưa cạnh ngắn về 256 và cắt giữa, dùng bộ lọc BICUBIC theo đúng cách pipeline hiện tại làm (một bước cắt giữa và resize, `ImageOps.fit`), để ảnh còn lại trùng byte với dữ liệu cũ (mã băm lưu trong `data/processed_baseline.sha256`, chụp trước khi ghi đè); sau đó nén JPEG đúng một lần ở chất lượng 95, rồi chuyển sang tiền xử lý đầu vào của CLIP. Cách làm hai bước tách rời (resize toàn ảnh rồi mới cắt) KHÔNG được dùng vì cho giá trị pixel khác.
- **FR-003**: Hệ thống MUST KHÔNG phóng to ảnh. Ảnh có cạnh ngắn nhỏ hơn 256 px là "quá nhỏ": với GenImage, ảnh MUST bị loại khỏi dữ liệu đã chuẩn hóa và ghi vào file tạm kèm lý do (không bỏ âm thầm); với API, ảnh MUST bị từ chối kèm thông báo rõ lý do. CIFAKE là ngoại lệ, giữ 32×32 vì chỉ dùng để chạy thử luồng.
- **FR-004**: `score(image)` MUST gọi hàm chuẩn hóa đúng một lần cho mỗi ảnh; API KHÔNG ĐƯỢC resize hoặc nén ảnh thêm ngoài hàm chuẩn hóa.
- **FR-005**: Hàm chuẩn hóa MUST có version; version MUST được ghi cùng dữ liệu đã chuẩn hóa, cùng đặc trưng trích xuất (`data/features/manifest.json`) và cùng model, để truy lại được ảnh và đặc trưng được xử lý bằng phiên bản nào. Hàm tải đặc trưng (do tính năng này cung cấp) MUST từ chối đặc trưng khi version trong manifest khác version hiện hành, khác version ghi trong `labels.csv`, hoặc số dòng không khớp `labels.csv`. Bước huấn luyện của M4 (ngoài phạm vi tính năng này, không có script huấn luyện mới ở đây) MUST tải đặc trưng bằng hàm tải này.
- **FR-006**: Đọc EXIF (nếu có) MUST xảy ra từ ảnh gốc TRƯỚC khi chuẩn hóa; thiếu EXIF không làm hỏng việc chuẩn hóa.
- **FR-007**: Với cùng một ảnh gốc, đầu vào CLIP thu được từ đường huấn luyện và đường API MUST giống nhau hoàn toàn.
- **FR-008**: Với ảnh mẫu truy theo `raw_path` trong `data/labels.csv`, kết quả chuẩn hóa lại MUST trùng (cùng sha256) với ảnh tương ứng trong `data/processed` **tại thời điểm trước khi tính năng này ghi đè dữ liệu**; mã băm của dữ liệu cũ MUST được lưu trong `data/processed_baseline.sha256` trước khi dữ liệu bị ghi đè, vì sau khi ghi đè thì so với `data/processed` mới là so với chính hàm mới.
- **FR-009**: Phải có phép kiểm tra metadata sau chuẩn hóa, báo AUROC cùng khoảng tin cậy; AUROC ≤ 0.55 là ngưỡng cảnh báo (vượt ngưỡng thì cảnh báo, không tự chặn).
- **FR-010**: Phải có phép kiểm tra dấu vết nén JPEG nhiều lần còn trong pixel của ảnh đã chuẩn hóa, báo kết quả theo từng nguồn dữ liệu.
- **FR-011**: Hàm chuẩn hóa MUST xoay ảnh theo thông tin hướng (orientation) trong EXIF trước khi resize, áp dụng giống nhau ở huấn luyện và API.
- **FR-012**: `score(image)` MUST nhận ảnh gốc đã giải mã, chưa chuẩn hóa. API MUST giải mã ảnh một lần ở ranh giới, đọc EXIF từ chính ảnh đó, và từ chối ảnh không đọc được hoặc quá nhỏ trước khi gọi `score()`. Giá trị `verdict` ngoài `likely_ai` (`[CẦN CHỐT]`) và mã lỗi cho ảnh không đọc được/quá nhỏ (`[CẦN CHỐT]`) MUST được chốt trước khi triển khai phần liên quan; spec không tự đặt.
- **FR-013**: Tính năng MUST KHÔNG thay đổi dữ liệu nguồn (GenImage), mô hình hay phần hạ tầng; chỉ thay đổi xử lý ảnh.

### Key Entities *(include if feature involves data)*

- **Ảnh gốc**: ảnh trước khi chuẩn hóa, gồm nguồn (ImageNet, các công cụ AI, ảnh demo), định dạng gốc, kích thước gốc.
- **Ảnh đã chuẩn hóa**: ảnh 256×256 sau một lần nén JPEG, gắn với version của hàm chuẩn hóa và đường dẫn ảnh gốc (`raw_path`).
- **Baseline dữ liệu cũ**: danh sách sha256 từng ảnh trong `data/processed` trước khi ghi đè, kèm mã nguồn đã tạo ra và phiên bản Pillow; dùng để chứng minh hàm mới trùng dữ liệu cũ.
- **Manifest đặc trưng**: bản ghi version, số dòng và cách ghép đặc trưng CLIP, nằm cạnh các tệp đặc trưng.
- **Ảnh bị tách (quá nhỏ)**: ảnh không đủ điều kiện chuẩn hóa, kèm lý do ghi lại.
- **Version chuẩn hóa**: định danh phiên bản quy trình chuẩn hóa, gắn với dữ liệu và mô hình.
- **Kết quả kiểm tra chất lượng**: AUROC kèm khoảng tin cậy, và mức dấu vết nén nhiều lần theo nguồn.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% ảnh thử cỡ 4000×3000 sau chuẩn hóa có kích thước 256×256 và chỉ qua một lần nén.
- **SC-002**: 100% ảnh trong tập kiểm tra cho cùng đầu vào mô hình giữa đường huấn luyện và đường API (độ lệch bằng 0).
- **SC-003**: 100% ảnh mẫu truy theo `raw_path` khi chuẩn hóa lại có sha256 trùng với mã băm cùng ảnh trong `data/processed_baseline.sha256` (dữ liệu trước khi ghi đè).
- **SC-004**: 100% ảnh quá nhỏ trong một lần chạy có bản ghi lý do và không nằm trong dữ liệu đã chuẩn hóa; không ảnh nào mất mà không có bản ghi.
- **SC-005**: Có bằng chứng bằng kiểm thử tự động rằng chấm điểm một ảnh gọi chuẩn hóa đúng một lần.
- **SC-006**: Kết quả kiểm tra metadata có AUROC và khoảng tin cậy; mọi AUROC vượt 0.55 đều được nêu cảnh báo trong báo cáo.

## Mục chưa chốt

Các mục sau do nhóm chưa quyết định; KHÔNG được tự đặt khi triển khai. Phải chốt qua `/speckit-clarify` hoặc review của nhóm:

| # | Mục | Ảnh hưởng | Trạng thái |
|---|---|---|---|
| 1 | Giá trị `verdict` (ngoài `likely_ai`) | FR-012 | Đề xuất, chờ duyệt: D05 trong [`docs/decisions/realcheck-baseline.md`](../../docs/decisions/realcheck-baseline.md) |
| 2 | Mã lỗi (ảnh không đọc được, ảnh quá nhỏ) | FR-003, FR-012 | Đề xuất, chờ duyệt: D05 trong [`docs/decisions/realcheck-baseline.md`](../../docs/decisions/realcheck-baseline.md) |

Đã chốt (xem mục Clarifications): bộ lọc resize BICUBIC, chất lượng JPEG 95, xoay theo orientation, ngưỡng "quá nhỏ" (cạnh ngắn < 256 px), chủ sở hữu hàm chuẩn hóa chung, kiểu đầu vào của `score()`.

## Assumptions

- Giữ nguyên dữ liệu GenImage hiện có (phương án A); không thêm, không đổi tập dữ liệu.
- Mô hình (CLIP ViT-B/32 + Logistic Regression) và thành phần hạ tầng không thay đổi trong tính năng này.
- "Cùng đầu vào CLIP" được hiểu là giống nhau từng giá trị sau tiền xử lý, không phải chỉ gần giống.
- Phép kiểm tra dấu vết nén nhiều lần (FR-010) hiện chỉ yêu cầu báo kết quả; chưa có ngưỡng đạt/không đạt nên spec không tự đặt ngưỡng.
- AUROC ≤ 0.55 là mức chấp nhận, vượt mức là cảnh báo cho người xem xét, không phải điều kiện tự động chặn.
- Mục tiêu hiện tại là đường chuẩn hóa dùng cho dữ liệu và API local; không đo hiệu năng tải.
- Việc thay bù các ảnh GenImage bị loại do quá nhỏ thuộc KAN-34, không thuộc tính năng này; tính năng chỉ cần nêu số ảnh bị loại và lý do.
- CIFAKE không bị ngưỡng "quá nhỏ" áp dụng và giữ 32×32 như pipeline hiện tại; cách CIFAKE đi qua hàm chuẩn hóa chung (bỏ bước resize/cắt hay không) sẽ được nêu trong plan, chưa quy định ở spec.

## Ngoài phạm vi

- Đổi dataset hoặc thêm nguồn dữ liệu.
- Đổi mô hình hoặc huấn luyện lại CLIP.
- Script huấn luyện bộ phân loại (M4): tính năng này chỉ cung cấp hàm tải đặc trưng kiểm manifest và ràng buộc M4 phải dùng nó.
- Nginx và Locust (giới hạn tải, đo tải).
- Thí nghiệm ảnh bị nén (JPEG 90/70/50, ảnh qua Zalo).
- Xử lý ảnh nhỏ ở phần nâng cao (ngoài việc tách riêng ảnh quá nhỏ ở User Story 3).
