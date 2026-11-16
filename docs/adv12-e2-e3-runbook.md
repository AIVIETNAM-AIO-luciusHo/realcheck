# E2/E3 (#158): chuẩn bị, khóa, chạy và bàn giao

**Trạng thái 16/11/2026: chuẩn bị xong công cụ/cache; chưa chạy E2/E3 thật.**
Hạn #158: **19/11/2026**. [Protocol chung](adv12-protocol.md) đã merge nhưng từng
mã vẫn cần Lực khóa riêng ở #161. Code kế thừa bảo vệ validation/holdout của
[PR #192](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/pull/192); review/merge
#192 trước, rồi cập nhật nhánh #158 lên commit được nhóm chốt. Không tự thay e571.

## 1. Phân vai và điểm dừng

- **Kiệt:** chuẩn bị bytes/hash, môi trường, extractor/benchmark, chạy khi đã khóa,
  giữ mọi artifact/log/exit code, báo cả kết quả xấu.
- **Lực:** duyệt commit, cấu hình duy nhất của từng mã, FPR phụ, giới hạn tài nguyên,
  used marker, quyền mở holdout và người tính lại độc lập.
- **Loan:** giữ ảnh ADV-06/A25, chạy phần cohort theo đường chấm được duyệt và gửi
  predictions/log/hash; ảnh cá nhân không rời máy Loan.
- Dừng trước chạy khi thiếu khóa, hash/split/environment lệch, artifact đã tồn tại,
  thiếu RAM hoặc encoder/device khác protocol. Lượt hỏng giữ nguyên; chạy lại cần
  protocol mới, không xóa marker để lựa số đẹp.

CLI `adv12_run`/`benchmark_adv12` **chưa tự xác minh protocol JSON/approval/used
marker**. Các kiểm tra output/hash/split không thay các bước Lực khóa và đánh dấu
lượt dùng. Không dùng một file `proposed` như giấy phép chạy.

## 2. Đầu vào cố định và đề xuất cấu hình

[Biên bản máy đọc](reports/adv12-158-preparation-20261116.json), preparation ID
`48a6cfe3-bdb6-44cf-9642-cc9bfcd426ca` (**không phải run ID thí nghiệm**):

- Dùng development manifest của #157: **3.988 train + 871 validation, 0 test**,
  SHA256 `7d489ad312ae428f8bcf755b2c810c063fb2409c63013dc3fb10222e2db1c434`.
  Đã kiểm lại raw/processed SHA256 của **4.859/4.859** ảnh tại #158. Không trộn CIFAKE.
- Holdout lịch sử **384** giữ riêng, không thay bằng 849 dòng candidate test. Chỉ
  model thắng được Lực cho mở đúng holdout một lần. ADV-06 không dùng chọn model/ngưỡng.
- [E2 proposed](reports/adv12-158-e2.proposed.json): ViT-B/32, CLS lớp **6,9,12**, 2.304 chiều, batch extract 8.
- [E3 proposed](reports/adv12-158-e3.proposed.json): ViT-L/14, CLS lớp **12,18,24**, 3.072 chiều, batch extract 2.
- Mỗi mã **một cấu hình**: C=10, max_iter=2000, seed 42, không augmentation,
  raw → chuẩn hóa hiện có → encoder đóng băng → LR. Nối CLS trước post-layernorm,
  không projection và không L2 từng lớp. Các tỷ lệ độ sâu tương ứng 1/2, 3/4, cuối.
- Giữ ngưỡng 0,3 / 0,5 / 0,7. FPR phụ lấy từ E0 validation tại `score >0,7`
  phải được Lực điền/khóa **trước E2/E3**. Không bổ sung lưới C/lớp sau khi thấy số.

Ma trận float32 4.859 dòng ước tính E2 **44.780.544 byte**, E3 **59.707.392 byte**,
chưa gồm metadata/bản sao/weights/activation. Đây là kích thước tính toán, **không
phải RAM đo được**. Batch extract khác nhau nên không dùng throughput extract để
thay latency batch 1.

## 3. Cache và máy chạy

Trọng số được tải theo yêu cầu người dùng, chỉ giữ cache ngoài Git:

| Encoder | Revision cố định | File đã kiểm byte/SHA256 |
|---|---|---|
| ViT-B/32 | `3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268` | `pytorch_model.bin`, 605.247.071 B, SHA256 `a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f` |
| ViT-L/14 | `32bd64288804d66eefd0ccbe215aa642df71cc41` | `model.safetensors`, 1.710.540.580 B, SHA256 `a2bf730a0c7debf160f7a6b50b3aaf3703e7e88ac73de7a314903141db026dcb` |

Nguồn chính thức: [B/32 config](https://huggingface.co/openai/clip-vit-base-patch32/blob/3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268/config.json),
[L/14 config](https://huggingface.co/openai/clip-vit-large-patch14/blob/32bd64288804d66eefd0ccbe215aa642df71cc41/config.json).
Config và processor cũng đã băm, resolver/config/processor qua kiểm với mạng tắt.
Cache chỉ gồm allowlist cần cho PyTorch vision; không tải mọi biến thể TF/Flax.
**Chưa instantiate trọng số thật**, chưa có phép đo model RAM hoặc thời gian thật.

Venv mới Python **3.12.14**, Pillow **13.0.0**, torch **2.15.0+cpu**; có RTX 5060
Laptop 8 GB nhưng `torch.cuda.is_available()` hiện **false**. Không tự chuyển sang
CUDA hoặc cài package giữa lượt. Processor hiện fallback **PIL** vì chưa có
torchvision; backend này phải được giữ trong fingerprint trước khi khóa.

CPU model dùng **4 torch thread** như e571. Trước lượt chính thức, Lực chốt máy và
budget RAM; Kiệt kiểm lại RAM khả dụng. Snapshot lúc chuẩn bị chỉ **1,307 GiB**,
chưa chứng minh đủ để nạp ViT-L/14. Không nạp E3 để thử khi chưa có headroom; không
train trên VPS 2 CPU/1,9 GiB đang phục vụ RealCheck. Mỗi phase dùng process mới,
không đồng thời pytest/download/model khác khi đo chi phí.

## 4. Trước mỗi phase đã được khóa

1. Checkout đúng commit sạch (`git status --porcelain` rỗng); lưu commit 40 ký tự,
   `python --version`, `python -m models.run_info`, freeze, OS/CPU/RAM và giờ UTC+7.
2. Đối chiếu checksum gói và data/cache bằng protocol trên **chính máy chạy**.
   Không sửa dữ liệu để khớp hash; junction/đường dẫn canonical phải đọc đúng bytes.
3. Lực chốt/ghi dùng protocol và marker trước chạy. Tạo thư mục run mới, giữ marker
   ở vị trí đã thống nhất; ghi người viết/chạy/tính lại riêng. Không tái sử dụng run cũ.
4. Pin các biến môi trường **trước khi khởi động Python** (PowerShell):

```powershell
$env:PYTHONUTF8='1'
$env:HF_HUB_OFFLINE='1'
$env:HF_HUB_CACHE=(Resolve-Path '.cache/adv12-158-hf').Path
$env:OMP_NUM_THREADS='4'
$env:MKL_NUM_THREADS='4'
$env:OPENBLAS_NUM_THREADS='4'
```

Cache e571 dùng cho baseline cost ở `.cache/adv12-158-e571-hub` (junction cache cũ
trên máy Kiệt). Chuyển `HF_HUB_CACHE` sang đó **cho process E0**, rồi đặt lại cache
B/32/L/14 cho process E2/E3. Không dùng một cache trống rồi cho phép tải revision mới.

## 5. Extract → fit validation → khóa output

Các lệnh đầy đủ nằm trong hai JSON proposed, **chỉ dùng sau khi Lực khóa**.
Ví dụ E2 (E3 dùng đúng model/revision/layers/batch trong JSON của nó):

```powershell
.venv/Scripts/python.exe -m scripts.adv12_run extract --labels .cache/adv12-158-preparation/development-labels.csv --image-column raw_path --output .cache/adv12-e2-run01/features.npz --encoder layers --model-id openai/clip-vit-base-patch32 --revision 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268 --layers 6,9,12 --augment 0 --batch-size 8 --device cpu
.venv/Scripts/python.exe -m scripts.adv12_run fit --features .cache/adv12-e2-run01/features.npz --output-dir .cache/adv12-e2-run01/fit --name adv12_e2 --C 10 --seed 42 --split val
```

Lưu stdout/stderr và exit code từng lệnh; dừng nếu khác 0. Ví dụ chạy một lệnh vào
`extract.log` sau khi đã tạo thư mục run mới:

```powershell
# Thêm *> .cache/adv12-e2-run01/extract.log ở cuối lệnh extract trên.
$adv12Exit=$LASTEXITCODE
$adv12Exit | Set-Content .cache/adv12-e2-run01/extract.exit.txt
if ($adv12Exit -ne 0) { throw 'Giữ artifact/log; dừng lượt và báo Lực' }
```

Manifest extract ghi revision/device/batch, tổng giây **gồm load encoder và đọc/
chuẩn hóa/trích**, không gồm ghi NPZ, cùng peak RSS toàn process. `fit` chỉ xuất val.
Sau fit ghi SHA256 NPZ, manifest, model/sidecar và CSV val; Lực kiểm/đóng băng output
trước cost/cohort/final eval. Model SHA trong proposed còn null vì chưa train.

## 6. Đo chi phí từng ảnh, cùng workload cho cả ba model

[100 ID đã ghim](reports/adv12-158-cost-sample-ids.json), SHA256
`ab9e61d51289ab66563524f70f1f503fd1456c34d46003de8852d2f4b6328599`:
25 validation mỗi nguồn, chọn/sắp theo SHA256(`adv12-cost-42|filepath`) trước mọi kết quả.
Đây là mix cân bằng nguồn, không phải tần suất người dùng thực tế.
100/100 raw đã kiểm metadata đều nằm trong giới hạn định dạng/kích thước API:
45.107–1.833.510 byte, tối đa 1.048.576 pixel. Điều đó chưa thay kiểm API thật.

- Khóa cả [phase E0 cost](reports/adv12-158-e0-cost.proposed.json); phase này chỉ
  tham chiếu chi phí, không báo là một lượt accuracy E0 mới.
- Mỗi model process mới, warmup 3 ảnh không vào thống kê, 100 ảnh đo **batch 1**,
  cùng thứ tự/máy/device/thread, không tuning theo cost rồi mở thêm test.
- Công cụ đo raw read/decode → chuẩn hóa → encoder → LR. Hash preflight làm ấm
  file cache OS; thời gian gồm I/O nhưng không đại diện cold disk. `load_ms` đo
  loader; loader e571 có warmup nội bộ, ghi khác biệt này khi so startup.
- p50/p95/p99 là nearest-rank. Báo RSS trước/sau load và cuối, **peak RSS high-water
  toàn process** gồm startup, không phải phần tăng thuần của model hoặc GPU VRAM.
- Đây là offline cost, **không chấm đạt p95 HTTP ≤400 ms**; API/gateway/upload/
  concurrency/queue/network cần phép đo riêng trên máy triển khai thật.

Ví dụ sau khi đã khóa model E2 và phase cost:

```powershell
.venv/Scripts/python.exe -m scripts.benchmark_adv12 --model .cache/adv12-e2-run01/fit/adv12_e2.joblib --feature-manifest .cache/adv12-e2-run01/features.json --labels .cache/adv12-158-preparation/development-labels.csv --sample-ids .cache/adv12-158-preparation/cost-sample-ids.json --warmup 3 --device cpu --output .cache/adv12-e2-run01/cost.json
```

Candidate được kiểm model checksum và manifest/features/labels/chiều; hash ảnh và
artifact kiểm lại cuối lượt. Lỗi runtime giữ JSON `failed`, không ghi đạt. Process
bị kill đột ngột có thể chỉ để lại output rỗng/dở; giữ thêm log, exit code và marker.

## 7. Bảng báo cáo và bàn giao

| Mã | Run ID | GenImage val / từng source, CI | ADV-06 tham khảo / A25 | Extract s / batch | Offline p50/p95/p99, n | Peak RSS | Thay e571? |
|---|---|---|---|---|---|---|---|
| E0 cost | chưa chạy | số quality ở #157, không dựng lại | số đã thấy, ghi rõ | N/A | chưa đo | chưa đo | baseline |
| E2 | chưa có | chưa chạy | chờ Loan | chưa đo | chưa đo | chưa đo | chưa đủ điều kiện |
| E3 | chưa có | chưa chạy | chờ Loan | chưa đo | chưa đo | chưa đo | chưa đủ điều kiện |

So CSV validation cùng ID với E0 bằng `compare_models`, seed 42/2.000 bootstrap,
giữ ngưỡng và tiêu chí 2 điểm accuracy/5 điểm recall của protocol. Ghi đúng số,
kể cả không cải thiện. Không chọn model/ngưỡng bằng ADV-06, A25 hoặc GenImage test.

**Kết luận hiện tại:** CLS E2/E3 là 2.304/3.072 chiều, khác không gian 512 chiều
của e571. Không cắm trực tiếp vào probe/API hiện tại. Chưa có chất lượng/cost/SLO
thật nên **chưa đủ điều kiện thay e571**. Nếu sau này có bằng chứng phù hợp, thay
model/adaptor là PR riêng kèm QA độc lập; không đổi SLO, G02 0,55 hoặc ngưỡng để đạt.

Bàn giao qua PR/issue: protocol đã khóa + reference/marker, commit/env/freeze,
hash model/data/cache/features, CSV val/cohort, JSON cost, stdout/stderr/exit codes,
người chạy/tính lại và kết quả cả lượt lỗi. Full data/model/cache giữ ngoài Git;
chỉ ghi đã nhận khi bên nhận thực sự nhận và kiểm checksum.

Gói chuẩn bị tại máy Kiệt: `adv12-158-preparation-20261116.zip`, **565.955 byte**,
SHA256 `d2ba058248dc199defb7e35ee2341c4807e48119c25c0344f943f3aa624fa134`.
Gói có **14 file được checksum**, kèm `verify_handoff.py` chỉ đọc hash/metadata;
đã kiểm gói đúng và ca sửa artifact bị từ chối. Không ảnh hoặc encoder weights
trong ZIP; các weights ở cache riêng. **Chưa gửi Lực/Loan hoặc đính kèm GitHub.**

**Chưa làm / lý do / khi nào:** E2/E3, cost thật và cohort chưa chạy vì chưa có khóa
riêng, FPR E0, output model, budget RAM và người kiểm. Tiếp tục sau khi Lực/Loan chốt;
đến hạn 19/11 vẫn ghi phần chưa làm trước khi nhóm quyết định đóng/xóa issue.
