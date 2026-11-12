# Metadata bộ realcheck_mixed_v3, run-v2

Bàn giao ngày 12/11/2026 cho Loan kiểm #54 / PR #81. Chỉ có metadata, không ảnh, weights, embedding, cache hoặc đường dẫn máy cá nhân. Đây là bản xuất của **đúng run-v2 đã dùng cho candidate mixed-v3 của PR #61**, không tạo bộ chọn mới hoặc thay nhãn/split. Model phục vụ e571 không đổi.

## Hai file cần dùng

| File | Số dòng dữ liệu | Phạm vi |
|---|---:|---|
| [labels.csv](labels.csv) | 12.645 | 9.936 train + 1.860 val + 849 test GenImage cũ chưa chấm trong run này |
| [selection.jsonl](selection.jsonl) | 12.805 | 9.936 expanded_train + 989 new_validation + 1.040 core_test + 840 reddit_test |

`labels.csv` gồm 10.925 ảnh mới train/validation và 1.720 ảnh GenImage validation/test cũ giữ lại để kiểm manifest. 1.880 ảnh OpenFake chỉ đánh giá nằm trong selection, không vào labels train. Vì vậy hai file không có cùng số dòng; không ghép bằng thứ tự dòng. Ghép bằng `filepath` đã bỏ đường dẫn máy cá nhân.

Giữ nguyên thứ tự, thành viên, nhãn và split của snapshot gốc. Các trường `status=candidate`, `reason` trong selection được giữ nguyên dù là metadata cũ từ pool; **membership của selection và các trường cohort/split/selection_group xác định mẫu cuối**, không lọc lại theo reason cũ. Không bịa `group_id` cho dữ liệu chưa có lineage được chốt.

## dHash và dung lượng

- `dhash`: số nguyên không dấu 64 bit, tính trên **ảnh chuẩn hóa được `filepath` tham chiếu**. Dùng nguyên `scripts.check_data.dhash`: grayscale, resize9×8 LANCZOS, so pixel bên phải `>` pixel bên trái, pack big-endian. Không phải dHash của raw.
- `file_size`: số **byte của file chuẩn hóa** tại `filepath`, dùng cho baseline dung lượng sau chuẩn hóa.
- `raw_file_size`: số **byte file gốc** tại `raw_path`, bổ sung để Loan có thể đo cả baseline trước chuẩn hóa.
- Selection vốn đã có dHash; đã tính lại và đối chiếu đủ12.805 bản ghi, không thay giá trị. Labels được thêm dHash và hai cột kích thước cho mọi dòng, kể cả1.720 ảnh GenImage cũ.
- Đã đọc/đối chiếu14.525 cặp raw/chuẩn hóa riêng biệt. Với12.805 ảnh selection, raw SHA256, normalized SHA256 và dHash đều khớp metadata gốc. Byte size được đo từ file thực, không suy từ kích thước pixel hoặc kích thước nén HTTP.

Đọc dHash bằng Python `int`. Tránh Excel hoặc JavaScript `Number` tự chuyển uint64 thành float và mất bit. CSV chứa số nguyên dạng thập phân; JSONL giữ integer gốc. JSONL dùng escaping Unicode để mỗi bản ghi nằm đúng một dòng vật lý, không bị ký tự phân cách Unicode trong prompt làm tách sai dòng.

Đường dẫn là **logical path tương đối với một data root được provision**, giữ cấu trúc `outputs/...` hoặc `realcheck/...`; không tương đối với thư mục metadata này. File dùng cho audit không cần tải ảnh. Bản enriched này không phải manifest đầu vào thay thế trực tiếp cho feature cache/model cũ: schema/hashes đã đổi, original labels và ảnh vẫn nguyên trạng. Không chạy `check_data` trực tiếp rồi coi lỗi thiếu ảnh/schema là lỗi dữ liệu; checker đó yêu cầu ảnh và sáu cột schema huấn luyện gốc.

## Trả lời: đã so với những manifest lịch sử nào?

Code chọn của run-v2 gọi `protected([baseline_labels, Path(".cache/ml-run/labels.csv")])`, với hai reference sau (tính tương đối từ repo gốc):

| Reference | SHA256 CSV gốc | GenImage train / val / test |
|---|---|---|
| `../outputs/realcheck-preserved-split/labels.csv` | `4bf8e4901ae09f258eeb01a5471ce1416898848f111dee2b1b2c3359235dfcad` | 3.988 / 871 / 849 |
| `.cache/ml-run/labels.csv` | `72313cf272f101c84c757d25c29869af8d290743e2be3151b5c9aa6debeae8c5` | 3.996 / 856 / 856 |

Mỗi CSV có9.708 dòng, trong đó5.708 GenImage; code bỏ CIFAKE khi xây lịch sử. Hai manifest có phần lớn cùng pool ảnh nhưng khác split, không cộng thành11.416 ảnh độc lập.

Quy tắc trong code đã ghi nguồn:

1. Dùng hash pixel RGB của ảnh chuẩn hóa và dHash với Hamming **≤4**.
2. Khi chọn ảnh train/validation mới: đối chiếu với **val/test GenImage của cả hai manifest**, rồi chống trùng/gần trùng trong pool; không tuyên bố mọi ảnh khác train lịch sử.
3. Khi chọn OpenFake core/reddit chỉ đánh giá: dHash đối chiếu với **toàn bộ train/val/test GenImage của cả hai manifest**, hash pixel bảo vệ val/test, và chống trùng với các ảnh đã chọn.
4. Đây là lọc gần trùng theo các reference đang có, không phải chứng nhận không còn mọi dạng leakage hoặc near-duplicate.

**Giới hạn bằng chứng:** policy gốc ghim checksum của reference thứ nhất. Reference thứ hai đúng đường dẫn trong source, checksum ở bảng là snapshot đối chiếu khi bàn giao; policy run-v2 không ghi riêng hash thứ hai. Lệnh train cũng có thể resume selection đã tồn tại, không có log riêng chứng minh mỗi lần gọi `protected()` hoặc toàn bộ hash lịch sử tại thời điểm tạo selection. File [handoff.json](handoff.json) ghi rõ các giới hạn đó. Source script hiện có khớp SHA đã ghi trong run.json: `f9141eafca1621557e1f8490b838f4e7fb417fd66b9fdce6b8b036b7a95880ed`; original run commit `9a3ca19`, **dirty=true**, không đổi thành provenance sạch khi xuất metadata.

**Chưa có manifest val1.309, bộ độc lập1.603 hoặc test kín** trong đầu vào của selector; không nhận đã kiểm các bộ này. Phát hiện của Loan ở #81 vẫn cần đối chiếu trên đúng metadata vừa bàn giao. Không rút kết luận sạch leakage từ số9 trường hợp bị loại trong báo cáo cũ.

`check_tiny_overlap.py` hiện nhận identity từ tên file shard/dòng. Nhiều file mới có tên UID hash nên checker đó không tự suy ra identity từ tên. Dùng provenance `repo/revision/parquet/row_group/offset`, các SHA trong selection và dHash mới có trong labels để so; kết quả0 từ việc không parse được tên không chứng minh không trùng. Upstream `split=train` cũng không chứng minh ảnh chưa được dự án lấy làm validation/test nội bộ.

## Checksum và kiểm bàn giao

- [handoff.json](handoff.json): checksum đầu vào gốc, số thực nhận, định nghĩa cột, phạm vi lịch sử và kiểm hash/dHash. Nguồn labels gốc có SHA256 `2997cdb9a7899f6daa4807fe024b87bf4150ef2286473676fa59d31ef2a22c5d`; selection gốc `96600baa314010febf9701721c1f6f92ce115f9d2e9ddb64aaa65916bab8c089`.
- `SHA256SUMS` kiểm bản metadata đã xuất. `.gitattributes` giữ LF để checkout Windows không đổi checksum. Các hash output khác input vì bỏ prefix đường dẫn máy cá nhân và thêm metadata; không thay snapshot nguồn.
- Đã kiểm độc lập số dòng, split/cohort, row order, join labels↔selection, uint64/byte-size, không đường dẫn tuyệt đối và không payload ảnh. Không train hoặc inference, không sửa dữ liệu/model, không nhận QA độc lập hoặc đóng #54 bằng lần bàn giao này.

Ví dụ đọc không cần ảnh:

```python
import csv
import json
from pathlib import Path

root = Path("data/metadata/realcheck_mixed_v3/run-v2")
with (root / "labels.csv").open(encoding="utf-8", newline="") as stream:
    labels = list(csv.DictReader(stream))
with (root / "selection.jsonl").open(encoding="utf-8") as stream:
    selection = [json.loads(line) for line in stream]
assert len(labels) == 12645 and len(selection) == 12805
assert all(0 <= int(r["dhash"]) < 2**64 for r in labels)
```
