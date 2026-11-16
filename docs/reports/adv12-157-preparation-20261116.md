# Chuẩn bị E0/E1 (#157), ngày 16/11/2026

**Chưa chạy E0/E1 thật.** Người dùng chưa có protocol E0/E1 đã được Lực khóa riêng.
Kiệt chuẩn bị dữ liệu, môi trường và hai đề xuất để Lực kiểm ở #161. Quy tắc chung
ADV-12 bản 2.1 đã merge không thay khóa riêng cho từng mã thí nghiệm.

Preparation ID: `bfa58923-73bb-4653-b414-76bf8eea2438`, **không phải run ID E0/E1**.
Chưa có điểm/accuracy hoặc model E1 mới; không ghi số cũ thành kết quả mới.

## Đầu vào đã kiểm

| Mục | Kết quả chuẩn bị |
|---|---|
| e571 | SHA256 `e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494`; dataset GenImage, C=10, seed 42; ngưỡng 0,3 / 0,5 / 0,7 |
| Dữ liệu | 5.708 ảnh GenImage từ CSV main; đối chiếu metadata với manifest giữ split lịch sử, kiểm raw/processed hiện diện và SHA256, giải mã processed JPEG/RGB/256×256 |
| Split | train **3.988**, val **871**, candidate test **849**; không trộn 4.000 CIFAKE vào E1 |
| Chống lẫn split | 0 group vắt split; 0 pixel processed giống hệt nhau vắt split/nhãn. Chưa làm lại kiểm gần trùng dHash độc lập; kế thừa `group_id` main |
| Development manifest | **4.859 dòng, chỉ train/val, 0 test**; SHA256 `7d489ad312ae428f8bcf755b2c810c063fb2409c63013dc3fb10222e2db1c434` |
| Holdout lịch sử | **384** ảnh, đối chiếu 384/384 hash với reference G03; selection SHA256 `ee2cd345984779501b7f8773d6daaa445b5f547aae13b68ea62887b9f53a11af` |
| Runtime | venv mới Python **3.12.14**, Pillow **13.0.0**, dependency ghim theo requirements; danh sách kiểu `pip freeze` lấy bằng `uv pip freeze`, hash/environment ở JSON và gói ZIP |
| Cache CLIP | 10 file hiện diện ở revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`, đã băm; **chưa nạp encoder thật** |

**849 dòng `split=test` không phải holdout 384 ảnh.** Holdout đã loại 465 ảnh theo
lịch sử train/validation và pixel trùng. Không chấm cả 849 rồi so với 94,53%/384.
Ở bước chọn model chỉ dùng development manifest; giữ inventory 384 riêng cho quyết
định model thắng/một lượt cuối của Lực. Hash và số theo nguồn ở
[JSON kiểm đầu vào](adv12-157-preflight-20261116.json).

Máy Kiệt có i7-14650HX và RTX 5060 Laptop 8 GB; RAM khả dụng tại snapshot khoảng
1,25–1,45 GiB. Runner e571 hiện dùng **CPU**, không tự dùng GPU khi thấy card NVIDIA.
Chưa bật GPU hoặc xác nhận encoder thật nạp được trong venv mới; cần kiểm lại RAM
trước lượt chính thức. Không dùng VPS 2 CPU/1,9 GiB đang phục vụ RealCheck để train.
Các junction dữ liệu chỉ tạo trong checkout mới, không sửa/xóa dữ liệu gốc.

## Công cụ đã sửa trước khi chạy

`scripts.adv12_run fit` trước đây fit trên train nhưng gọi `predict_proba` cho toàn
bộ train/val/test và luôn xuất cả điểm test. Điều đó mở test của mọi ứng viên, trái
C5 của protocol. `score` cũng mặc định chấm mọi split và chưa kiểm group vắt split.

- `score` và `fit` nay mặc định **chỉ validation**. Chỉ những dòng của split được
  yêu cầu mới vào scorer/`predict_proba`; CSV giữ đúng cặp ID–score. Test cần opt-in
  tường minh và khóa/ủy quyền đúng trước lượt chạy.
- `score` kiểm group trên toàn manifest trước lọc split và trước nạp model.
- `extract`, `fit`, `score` từ chối output hoặc sidecar đã tồn tại trước công việc tốn
  tài nguyên, giữ nguyên bằng chứng lỗi/cũ. Không thêm chế độ ghi đè.

**Runner vẫn chưa tự kiểm protocol JSON hoặc used marker.** Output mới không thay
quy tắc mỗi protocol một lần; Lực phải chốt marker, người chạy và cách giữ lượt hỏng.
Không đổi `models.train`, `models.extract_features`, chuẩn hóa, e571, SLO hay G02.

## Đề xuất cần Lực khóa

- [E0 proposed](adv12-157-e0.proposed.json): chấm e571 trên 871 ảnh validation,
  `--image-column raw_path`, ngưỡng giữ nguyên; không chấm lại Samsung A25 để tạo số E0 mới.
- [E1 proposed](adv12-157-e1.proposed.json): **một** cấu hình GenImage train, C=10,
  max_iter=2000, seed/augment seed=42, p=0,5 cho từng phép JPEG/downscale/screenshot
  của `models.augment`; batch 8; không augment validation. Dùng raw và cùng đường
  chuẩn hóa/encoder, chỉ xuất điểm validation khi fit.
- Runner commit đề xuất: `b928588bf622b6d9a630b0f3237febe00b5b5bff`, checkout sạch
  tại lúc đóng gói. Đây là commit ứng viên để review, **chưa được Lực phê duyệt**.
  Sau merge, Lực chọn commit thật và kiểm lại fingerprint/hash trên đúng máy chạy.
- Sau E0, ghi FPR tại `score > 0,7` trên validation vào protocol E1 **trước E1**;
  không điền hoặc thay theo kết quả E1. Model E1 chưa tồn tại nên SHA output còn null:
  cần Lực chốt khóa giai đoạn train và hash model trước khi ủy quyền đánh giá cuối.

Ảnh ADV-06/Samsung A25 ở máy Loan; không đưa sang máy Kiệt hoặc Git. E0 Samsung
đã có số 29/38 gọi AI từ 15/11, chỉ là kết quả đã thấy. Cần Lực/Loan xác nhận đường
chấm ứng viên E1: bundle từ `adv12_run fit` hiện là experimental, thiếu hợp đồng
metadata mà `models.score.load_scorer` yêu cầu; không trỏ model đó vào API để né QA.
Người chạy cohort, người tính lại độc lập và quyền mở holdout vẫn chờ chốt.

## Gói bàn giao và trạng thái #157

Đã tạo `adv12-157-preparation-20261116.zip`, **787.513 byte**, SHA256
`7fce264215799ddf6dc46b476ba15895f0cfa11df8d7a4e545e31c50f91f87dc`.
14 file có checksum: hai protocol, CSV/inventory, environment/freeze, model e571 nhỏ,
README; ZIP qua CRC và so byte từng thành viên. Không ảnh, CLIP weights, venv hoặc
đường dẫn máy cá nhân trong gói. Gói giữ ngoài Git, **chưa gửi Lực/Loan**.

**Chưa làm:** E0/E1 trên dữ liệu thật, số validation mới, đánh giá ADV-06/A25, final
holdout, run ID thí nghiệm và kiểm độc lập. **Lý do:** chưa có khóa riêng E0/E1,
FPR phụ trước E1 và đường chấm/đầu vào cohort trên máy Loan. **Khi tiếp tục:** sau
khi Lực/Loan xác nhận các mục trên, dùng output mới theo đúng protocol, giữ mọi lượt
không đạt. Hạn #157 là **19/11/2026**, giữ issue mở; không báo hoàn thành thí nghiệm.
