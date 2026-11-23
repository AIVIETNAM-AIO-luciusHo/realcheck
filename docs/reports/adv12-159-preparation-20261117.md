# Bàn giao E4/E5 (#159), ngày 17/11/2026

**Chưa chạy E4/E5 trên điểm thật.** #161 chưa có khóa riêng E4/E5; model tốt
nhất E0–E3 và FPR validation E0 chưa được khóa. Đây là công cụ, kiểm đầu vào và
đề xuất để Lực duyệt; không phải kết quả thí nghiệm, chứng nhận xác suất hay QA.
Hạn #159: **19/11/2026**.

## 1. Phần đã làm

- Sửa `calibrate_scores`: trước đây trường hợp ảnh thật đạt điểm 1,0 có thể báo
  FPR=0 nhưng xuất ngưỡng 1,0, tái chạy `score >= 1,0` lại gọi ảnh đó AI. Nay giữ
  ngưỡng thực (có thể >1: không gọi ảnh nào AI), chọn ngưỡng trên từng bộ điểm
  thực sự đã biến đổi; FPR/recall đi cùng đúng ngưỡng. Dùng sigmoid ổn định số học.
- Bổ sung `adv12_scores fit/apply`: E4 Platt trên validation, E5 trung bình cố
  định 50/50 theo ID; lưu tham số rồi áp nguyên trạng, kể cả cohort chỉ ảnh thật.
  Apply không fit, chọn ngưỡng hay tính metrics. Nhãn output vẫn là **score**.
- Fit yêu cầu đúng toàn bộ validation GenImage trong development manifest,
  cùng ID/nhãn/group/source, đủ hai lớp; từ chối manifest có test, nhóm vắt split,
  điểm lỗi hoặc cặp lệch. E0 là đầu vào riêng, luôn so với E0 và kiểm target FPR
  khớp E0 tại `score > 0,7` trước fit. Người chạy vẫn phải chứng minh FPR này đã
  được khóa **trước** lượt E4/E5 bằng receipt/protocol, không chỉ suy ra sau đó.
- Báo N theo nguồn; so sánh cặp tại 0,3/0,5/0,7 bằng `compare_models`, gồm AUROC,
  FPR, recall, vùng chưa chắc và CI hiệu E0 − kết quả. Có accuracy nhị phân theo
  nguồn và FPR/FNR/accuracy + CI ở điểm phụ. FNR = 1 − recall.
- Kiểm hash input trước/sau, output mới, giữ report lỗi, lưu hash tham số/CSV,
  commit/dirty/runtime/fingerprint môi trường. SHA model là **khai báo người tạo
  CSV**, không chứng minh CSV thực sự được tạo bởi model đó; phải kiểm receipt
  `adv12_run score/fit` độc lập. JSON protocol/used marker **chưa được tự kiểm**.

Runner ứng viên: `fad5cf9d460ab3ffce347c1d51b6b722785dbfa7`, checkout sạch
ngay sau commit. Phụ thuộc PR #192 (an toàn split E0/E1); không cần PR #193
(encoder/benchmark E2/E3). Sau merge, Lực ghim commit sạch thực tế và fingerprint
trên máy chạy. Không sửa chuẩn hóa, model API, SLO hoặc G02 0,55.

## 2. Đầu vào và nguồn gốc mixed-v3

Chi tiết máy đọc: [preflight](adv12-159-preflight-20261117.json).

| Artifact | SHA256 | Ý nghĩa |
|---|---|---|
| e571 | `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494` | Đối chứng, C=10, seed 42, CLIP B/32 512 chiều |
| mixed gốc | `26b8882963b9224eb72d2010b46dd390dbd3545173c40c4e452908fbd596c28d` | Bản gắn với số GenImage validation 86,45%/871 trong báo cáo cũ; không phải số mới của #159 |
| mixed dựng lại | `7164eeca27ce1d30f73ed70451cafd2a4c26423352a04a2cf44ff26685e19678` | Ứng viên đề xuất E5; fit bằng code sạch từ cache cũ, chưa QA/phê duyệt release |
| development CSV | `7d489ad312ae428f8bcf755b2c810c063fb2409c63013dc3fb10222e2db1c434` | 4.859 dòng = 3.988 train + 871 val, **0 test** |
| inventory validation | `bbda229da02e2cd1f47a0834c9dc896857ed4758b84d4cc4fe1bd00337798863` | 421 thật + 150 SD1.4 + 150 Midjourney + 150 GLIDE |

Đã băm lại ba model, kiểm sidecar và hợp đồng bundle bằng `load_bundle`; **không
nạp encoder, gọi predict hay fit**. Đã đối chiếu 871/871 ID/nhãn/group/source/split
giữa CSV và inventory. Hash ảnh kế thừa preflight #157; **không băm/giải mã lại
ảnh trong lượt #159 này**. Có cả model gốc trong gói để truy vết, không tự chạy
hai biến thể mixed thành hai cấu hình E5.

Bản gốc xuất phát commit `9a3ca19e7f8eee273476bcf3ea8f3c4c6510c483`,
`dirty=true`. Không có commit sạch tái tạo đúng byte đó vì working tree gốc chưa
commit. Bản 7164ee có fit commit `e4b6d29018144d86c515262750a0a28aa56835f4`,
`dirty=false` **chỉ cho bước fit**; khâu đóng gói trước đó ở commit
`285316782afcaf6e6b61b24b1a8dfb0042caeef5`, `dirty=true`. Không suy ra việc thu
thập/chuẩn hóa cache sạch, không gán 86,45% hay số test của 26b888 cho 7164ee.
Các việc giấy phép Landscapes HQ, dHash/metadata/nhãn dữ liệu mới ở #144 vẫn chờ
Loan; kiểm kỹ thuật bundle không thay QA đó. Không train mixed mới ở lượt này.

Môi trường mới Python 3.12.14, Pillow 13.0.0; package fingerprint
`178e84d2841526f75522ae6eb4ede2d653f34dbf59e4fecba710323966987694`.
Freeze đầy đủ trong gói. Các thao tác điểm CSV không cần GPU hay VPS; tạo điểm
ảnh về sau cần kiểm RAM/cache/runner đúng model và khóa protocol trước.

## 3. Lực cần khóa gì

Hai đề xuất: [E4](adv12-159-e4.proposed.json), [E5](adv12-159-e5.proposed.json).
Giữ `status=proposed`, `run_id=null`, `independent_qa_approved=false`.

1. Ghim commit sạch đã review và môi trường thực chạy; chốt người viết, chạy,
   tính lại độc lập, marker một lần và cách giữ lượt lỗi.
2. Chọn model tốt nhất E0–E3 bằng validation theo mục 4 protocol v2.1: accuracy
   tụt ≤2 điểm %, recall từng nguồn AI tụt ≤5 điểm %, AUROC không tụt có CI loại
   0; trong các model hợp lệ chọn FPR thật thấp nhất, hòa CI ưu tiên ít chiều.
   Ghim SHA model, receipt chấm, SHA point CSV và manifest. Không chọn bằng ADV-06.
3. Ghim point CSV E0 871 ảnh và FPR E0 ở `score > 0,7` **trước E4/E5**; số chưa có
   nên proposal để null, không tự điền một target FPR tùy ý như 5%.
4. E4 đề xuất **một** cấu hình Platt (C=1e10, max_iter=1000, 15 bin ECE), không
   grid. Temperature trong `calibrate_scores` chỉ là chẩn đoán kèm, không được
   lựa chọn thay Platt sau khi xem số. Nếu muốn bỏ/thêm thì chốt trước lượt thật.
5. **E5 có chỗ cần quyết:** tiêu đề #159 ghi e571 + mixed-v3, còn protocol chung
   mục 4 yêu cầu model tốt nhất E0–E3. Proposal tuân theo protocol chung: anchor
   chưa điền; e571 chỉ khi thắng hoặc Lực sửa/khóa rõ protocol riêng trước chạy.
   Bản mixed đề xuất 7164ee; nếu chọn 26b888 phải khóa lại hash/nguồn gốc trước,
   không thử cả hai rồi chọn. Một cấu hình trung bình **0,5/0,5**, không stacking,
   không sweep trọng số, không ghép thêm Platt E4 vào E5 trong đề xuất này.
6. Loan xác nhận QA mixed-data và đường chấm cohort riêng trên máy Loan. ADV-06
   là phát triển; #116 là 38 ảnh thật cuối, không đo recall AI. Với anchor E1/E2/E3
   experimental, cần đường chấm đúng encoder/bundle đã duyệt; không trỏ bundle
   thử nghiệm vào API để né hợp đồng serving.

## 4. Thực hiện sau khi có khóa

Các biến `<...>` là giá trị Lực phải khóa; các lệnh dưới **chưa chạy trên dữ liệu
thật**. Chạy từ root repo, kiểm package checksum và commit sạch trước. Không dùng
`data/labels.csv` đầy đủ có test cho bước fit này.
Gói chỉ có manifest/model probe nhỏ, không có ảnh hay CLIP weights. Máy chạy phải
ánh xạ dữ liệu đã kiểm về `data/raw/genimage`/`data/processed/genimage`, giữ nguyên
ID tương đối trong CSV, đối chiếu lại hash ảnh trước lượt thật; không sửa CSV để
trỏ sang bộ khác. Ghim cache CLIP offline đã kiểm cho đúng revision của model;
kiểm RAM trước khi nạp, không dùng VPS đang phục vụ để ép chạy encoder.

Nếu anchor là e571, tạo điểm bằng `adv12_run score` mặc định chỉ validation;
hai scorer phải dùng **cùng CSV** để giữ ID (không dùng CSV mixed riêng với alias
đường dẫn khác):

```bash
HF_HUB_OFFLINE=1 python -m scripts.adv12_run score \
  --labels .cache/adv12-159-preparation/development-labels.csv \
  --image-column raw_path --split val \
  --model .cache/adv12-159-preparation/models/e571.joblib \
  --output .cache/<locked-e0-output>/scores.csv
HF_HUB_OFFLINE=1 python -m scripts.adv12_run score \
  --labels .cache/adv12-159-preparation/development-labels.csv \
  --image-column raw_path --split val \
  --model .cache/adv12-159-preparation/models/mixed-clean-7164ee.joblib \
  --output .cache/<locked-mixed-output>/scores.csv
python -m scripts.adv12_scores fit --mode platt \
  --labels .cache/adv12-159-preparation/development-labels.csv \
  --a <locked-best-val.csv> --a-model-sha <locked-best-sha> \
  --e0 <locked-e0-val.csv> --target-fpr <locked-e0-fpr> \
  --replicates 2000 --seed 42 --output-dir .cache/<locked-E4-output>
python -m scripts.adv12_scores fit --mode mean \
  --labels .cache/adv12-159-preparation/development-labels.csv \
  --a <locked-anchor-val.csv> --a-model-sha <locked-anchor-sha> \
  --b <locked-mixed-val.csv> --b-model-sha <locked-mixed-sha> \
  --e0 <locked-e0-val.csv> --target-fpr <locked-e0-fpr> \
  --replicates 2000 --seed 42 --output-dir .cache/<locked-E5-output>
```

Đây không phải lệnh cho phép chạy lại E0 nếu protocol E0 đã dùng; tái sử dụng
CSV/receipt đã khóa khi có, không chấm lại để làm đẹp số. Với model thắng khác
e571, dùng điểm validation đúng receipt của E1/E2/E3; không ép qua scorer e571.
Giữ stdout/stderr, protocol/hash/used marker, report kể cả lỗi. Sau fit, Lực khóa
hash `params.json`, CSV output và điểm vận hành trước khi mở cohort/final:

```bash
python -m scripts.adv12_scores apply --params <locked-params.json> \
  --a <cohort-anchor.csv> --a-model-sha <locked-anchor-sha> \
  --output-dir .cache/<locked-cohort-E4-output>
python -m scripts.adv12_scores apply --params <locked-E5-params.json> \
  --a <cohort-anchor.csv> --a-model-sha <locked-anchor-sha> \
  --b <cohort-mixed.csv> --b-model-sha <locked-mixed-sha> \
  --output-dir .cache/<locked-cohort-E5-output>
```

Ảnh ở máy Loan; chỉ trao đổi point CSV/manifest/receipt được phép. Apply không
xác nhận input là tập cuối hợp lệ; người chạy phải đối chiếu protocol/cohort và
checksum tham số đã khóa. Công cụ không tự tiêu thụ used marker.

## 5. Cách đọc và kết luận

- Điểm chính giữ 0,3/0,5/0,7: nhị phân `>=0,5`, gọi "Ảnh AI" **`>0,7`**; không
  đánh đồng với điểm phụ `>= selected threshold`. `selected_ai` trong CSV chỉ là
  quyết định tại **điểm phụ**; không dùng thay verdict API hay vùng chưa chắc.
- `fixed_thresholds_E0_vs_result`: A=E0, B=kết quả, hiệu **E0 − kết quả**. Khi
  đọc FPR, CI toàn dương mới gợi ý giảm FPR; đọc recall/AUROC theo đúng chiều.
  Có thêm A=anchor, B=kết quả và mixed-vs-result khi E5.
- Bảng điểm phụ báo FPR, **FNR/bỏ sót**, accuracy, CI và N từng nguồn; nguồn chỉ
  một lớp có metric thiếu lớp là null. CI bootstrap nhóm 2.000, seed 42, có điều
  kiện trên tham số/ngưỡng đã fit; **không điều chỉnh chọn model/ngưỡng**, không
  phải CI tổng quát hóa độc lập. ECE/Brier/NLL sau fit trên cùng validation cũng
  là resubstitution; không đủ bằng chứng để gọi score là xác suất.
- E4 chỉ ghi **đổi điểm vận hành**, không tuyên bố model tốt hơn. Đo AUROC thực
  tế vì clipping ở 0/1 hoặc bão hòa có thể gộp ties số học.
- Nếu đạt target FPR chỉ bằng cách không gọi ảnh nào AI, báo FNR=1/recall=0,
  không ghi thành cải thiện. Nếu không có cấu hình/ngưỡng đáp ứng các ràng buộc
  đã khóa, ghi **không cải thiện** hoặc **chưa phân biệt được** kèm số; không mở
  thêm grid, đổi target, đổi model sau khi thấy cohort/test. Không có số thật
  hiện tại để kết luận một trong các kết cục đó.
- #116: báo số đổi nhãn cả hai hướng so với E0 và kiểm định dấu chính xác theo
  protocol; công cụ điểm CSV này chưa tự làm kiểm định đó. Không đo recall trên
  38 ảnh toàn thật. ADV-06 chỉ tham khảo chuyển miền, không chọn model một mình.
- Test GenImage chỉ **model thắng, một lượt, 384 ảnh holdout lịch sử** khi Lực
  cho phép. 849 candidate test rows không phải 384; không mở test của mọi E4/E5.
  Bảo toàn số không đạt, không sửa SLO/ngưỡng G02 hay serving sau kết quả.

## 6. Kiểm chứng và việc còn lại

Gói `adv12-159-preparation-20261117-final.zip` (202.755 byte) giữ ngoài Git, **chưa gửi
Lực/Loan**; [receipt và SHA256](adv12-159-package-20261117.json). Kiểm read-only
đạt SHA ZIP, CRC, checksum 18 file và liên kết nội bộ; thử hash ZIP sai và sửa member (dù tính lại
hash ZIP) đều bị từ chối. Gói có manifest/inventory, ba probe nhỏ + sidecar,
receipt, environment/freeze, hai proposal, kiểm chứng local, hướng dẫn và verifier; không có ảnh,
CLIP weights, tham số hiệu chuẩn đã fit hay kết quả E4/E5.

Đã có hai regression fail trước sửa cho biên ngưỡng/tái tạo quyết định; bộ tập
trung 66 passed sau sửa (trước hai test E0 reference bổ sung). Full suite sau cùng:
**1.206 passed, 0 failed, 0 skipped, 1 xfail có sẵn**, 529,46 giây;
`pytest --cov=app --cov-fail-under=70`, coverage app **99,43%**. Ruff check và
format check toàn repo đạt (181 file). [Receipt kiểm chứng](adv12-159-validation-20261117.json).
Test dùng dữ liệu tổng hợp, không thay lượt E4/E5 thật hoặc QA độc lập.

**Chưa làm:** tạo điểm thật, fit E4, gộp E5 thật, chấm ADV-06/#116/test, kiểm định
dấu, kết luận cải thiện và xác nhận xác suất. **Lý do:** thiếu các khóa/receipt và
đầu vào cohort nêu mục 3. **Khi tiếp tục:** sau Lực/Loan xác nhận, dùng commit sạch,
môi trường/hash đã ghim, output/marker mới đúng protocol. Nếu chưa đủ trước hết
19/11, cập nhật chính xác phần chưa làm theo quy ước #159; không đánh dấu các ô
thí nghiệm đã xong và không tự đóng issue ở thời điểm chuẩn bị này.
