# ADV-08 — Đánh giá robustness, GitHub #52

## Trạng thái thực tế

**Chưa chạy robustness thật, chờ bàn giao #51.** Kiểm tra main `a37ff0e25ca9835ece567d0313650828dfd76c99` và issue #51: chưa có runner `--robustness`, manifest chốt hoặc predictions được giao. `scripts.evaluate --help` hiện chỉ có `--split`, `--labels`, `--features`, `--model`, `--output`. Không thể dùng evaluator cache train hiện tại để thay runner cohort mới.

Phạm vi đã thống nhất chỉ #52: chuẩn bị kiểm đầu vào và phân tích predictions; Loan làm thu cohort #50 và biến thể/runner #51, Lực review độc lập #49. T023 ở đây thuộc **spec 000 / AC-26**, khác T023 migration của spec 001. [Trạng thái máy đọc được](reports/robustness-adv08-status.json) không có metrics thật hoặc chứng nhận QA.

Helper `scripts.analyze_robustness` không nạp/unpickle model, không chạy encoder, không sinh ảnh hoặc predictions. Có hai chế độ: preflight kiểm bàn giao/ảnh; analysis tính từ predictions đã lưu. Schema dưới đây là **giao diện đề xuất cho bàn giao #51**, đã kiểm bằng fixture; chưa phải tuyên bố runner của Loan hỗ trợ schema đó. Nếu schema thực tế khác, thống nhất mapping có bằng chứng trước chạy, không đoán từ tên file hoặc sửa thay runner trong #52.

## Model và môi trường khóa

Tải [gói bàn giao e571](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/releases/tag/api-model-reference-e571-20261110); xem [hướng dẫn API/model](ml-api-model-handoff.md).

```text
model SHA256 = e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494
CLIP = sentence-transformers/clip-ViT-B-32
revision = 327ab6726d33c0e22f920c83f2ff9e4bd38ca37f
normalization_version = 1
binary / low / high = 0.5 / 0.3 / 0.7
bootstrap = 2000 replicates, seed42, percentile CI95%
```

Python3.12.14, CPU, một scorer, tuần tự; torch2.15.0 / transformers5.22.1 / sentence-transformers6.2.0 / Pillow13.0.0 theo requirements đã ghim. Chỉ helper phân tích cần dependencies cơ bản trong `requirements.txt`; chạy scorer thật cần thêm `models/requirements-ml.txt`. Sidecar runtime chỉ chứa raw hash. Giữ CLIP cache đúng revision và bật offline sau provisioning. Không dùng artifact mixed `26b888…` hoặc `7164ee…` của PR #61.

## Contract bàn giao và protocol

Copy [protocol mẫu](robustness-adv08.protocol.example.json) vào thư mục input được ignore, điền **số thực nhận và tham chiếu thật**, rồi khóa trước inference. Template cố ý là `draft` với hash/commit chưa biết bằng null; helper phải từ chối nó. Không điền reviewer hoặc phê duyệt giả.

Protocol v1 bắt buộc:

- `status="locked"`, `manifest_lock_ref`, `split_review_ref`, `parent_exposure` (lịch sử đã tiếp xúc hay chưa).
- `runner`: commit40hex, `handoff_ref`, `tests_ref`; `analysis_commit`: commit chứa đúng helper đã commit sạch. Khi QA tái lập, checkout đúng commit đó; không sửa protocol để khớp HEAD mới sau khi đã xem score. Không đòi commit của runner bằng commit train model.
- `artifacts.model`, `.model_manifest`, `.manifest`: `{path,sha256}`. Path tính từ thư mục protocol. Model manifest JSON có `model_sha256`, `clip_model_id`, `clip_revision`, `normalization_version`, `thresholds`, tương thích manifest trong ZIP e571.
- `history`: danh sách `{path,sha256}` CSV có `group_id,split` (`train|val|test`). Đây phải là lineage được Loan gắn cùng namespace với cohort; CSV labels cũ thiếu group không đủ chứng nhận lịch sử. Helper kiểm giao group trong **lịch sử được cấp**, không tự xác minh near-duplicate ngoài đó. `split_review_ref` phải mô tả phạm vi lịch sử/kiểm trùng.
- `profile`, `thresholds`, `bootstrap`: đúng giá trị template; CLI không có tùy chọn tune.
- `cohorts`: đăng ký đủ `parents,jpeg90,jpeg70,jpeg50,rotate,crop,downscale,brightness,phone,ai_new,zalo`. Có thể thêm slice khác nhưng không được bỏ cohort dự kiến để báo complete. Mỗi mục `present` có `n_expected>0` và `transform={kind,params}`; mục `missing` có lý do, không sinh số đo. Tên cohort là khóa báo cáo, không phải tín hiệu model.

Manifest JSONL: mỗi dòng có `sample_id,path,sha256,label,source,cohort,split,group_id,parent_id,transform`.

- `path` trỏ ảnh đầu vào raw/biến thể **trước normalizer**, tính từ thư mục manifest; `sha256` là hash bytes.
- `label` là integer0/1, `split="test"`; không nhận CIFAKE. `sample_id` duy nhất.
- Ảnh cha hoặc ảnh external độc lập: `parent_id=null`. Biến thể: ID cha tường minh, cha phải là root, cùng label/group/source. Không nhận self-parent, chuỗi hoặc vòng cha–con. Zalo có thể không có cha nhưng lúc đó không có flip rate.
- `transform` khớp nguyên object đã khóa ở cohort; params cần ghi thao tác thực tế, ví dụ JPEG `{quality:90}`, rotate `{degrees:5}`. Không ghép các mức biến đổi khác nhau vào cùng cohort rồi mất thông tin tham số.
- Exact duplicate cùng hash phải cùng group. Helper kiểm hash; review near-duplicate vẫn cần bằng chứng Loan/Lực, không được coi hash là đủ.

Predictions CSV phải có đúng một outcome cho mỗi ID manifest, với các cột:

```text
sample_id,group_id,parent_id,label,status,score,verdict,error_code,model_sha256,manifest_sha256,protocol_sha256
```

`parent_id` của root là ô trống, label là0/1. Ba cột hash ràng buộc predictions với đúng model/manifest/protocol. Runner #51 cần ghi các hash đó trước inference; không gắn hash vào score không rõ nguồn sau khi chạy.

`status=ok`: score hữu hạn `[0,1]`, verdict khớp ngưỡng, error_code trống. `status=error`: score/verdict trống, error_code dạng `MODEL_ERROR`, `IMAGE_TOO_SMALL`, `INVALID_IMAGE` (chữ hoa/số/gạch dưới), không đưa path/traceback vào báo cáo công bố. Không cho prediction thiếu/thừa/trùng ID hoặc đổi lineage. Runner phải lưu log provenance, phiên bản môi trường và kiểm SHA model/manifest trước/sau inference; helper chỉ xác minh bytes hiện có và provenance đã được ghi, không tự chứng minh lịch sử thực thi của runner.

## Trình tự chạy khi đủ đầu vào

1. Tạo worktree riêng `kiet/adv08-robustness` từ main đã nhận runner bàn giao; giữ workspace Backend hiện tại nguyên trạng. Chạy test helper/runner rồi commit trước lượt inference. Input/output nằm trong `.cache/adv08/` để không làm Git dirty.
2. Chốt protocol, hash và tham chiếu dữ liệu/lineage với Loan. Điền `analysis_commit` bằng HEAD sạch. Không đổi protocol theo kết quả.
3. Chạy preflight bên dưới. Exit0 nghĩa hợp lệ cho phần có dữ liệu; `missing_cohorts` vẫn phải theo dõi, không nghĩa đủ AC-26. Exit1 báo ảnh decode/kích thước lỗi: giữ evidence, sửa bàn giao trước lượt chính. Exit2 là protocol/hash/lineage/history/checkout sai, dừng trước inference.
4. Chỉ chạy lệnh **thật** do #51 bàn giao, đối chiếu `--help`; mỗi ảnh một prediction, tái sử dụng prediction cha. Scorer nhận ảnh raw/biến thể và normalize một lần. Không gọi lại model-test cũ, không xóa used-marker, không lấy holdout384 ảnh cũ làm tập cha thay thế. Tập cha từng tiếp xúc phải ghi rõ trong protocol.
5. Khi runner xong, kiểm hash model/manifest còn nguyên, lưu log/predictions rồi gọi analysis. Phân tích lại cùng predictions không cần inference lại; luôn dùng output mới.

```powershell
python -m pip install -r requirements.txt
$env:PYTHONUTF8 = '1'
$env:HF_HOME = '<thu-muc-goc-HF-cache>'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'

python -m scripts.analyze_robustness --protocol .cache/adv08/input/protocol.json --manifest .cache/adv08/input/manifest.jsonl --preflight --output .cache/adv08/run-01/preflight.json

# Chạy runner #51 theo lệnh bàn giao; helper dưới đây KHÔNG tạo predictions.csv.
python -m scripts.analyze_robustness --protocol .cache/adv08/input/protocol.json --manifest .cache/adv08/input/manifest.jsonl --predictions .cache/adv08/run-01/predictions.csv --output .cache/adv08/run-01/artifacts/robustness.json
```

Analysis exit0: đủ cohort đăng ký, không lỗi, **chờ review độc lập**. Exit1: thiếu cohort hoặc mẫu lỗi, report `incomplete`. Exit2: input/protocol không hợp lệ, chỉ ghi lý do lỗi, không metrics. Không có hard gate accuracy90% cho OOD. Từ chối ghi đè mọi output đã tồn tại, kể cả report lỗi. Lỗi giữa inference giữ output/log và ghi lần chạy chưa hoàn tất; không tự dựng outcome cho ảnh runner chưa xử lý.

## Công thức và nội dung JSON

Mỗi cohort có N tổng/chấm/lỗi/group/real/AI, metrics và CI; `by_source` tách nguồn. Không có một accuracy tổng gộp ảnh cha, biến thể và external cohort. `missing` có N thực nhận0, metrics/CI/pairing null và lý do, không biến thành accuracy0. `n_groups` gồm cả group có ảnh lỗi, `n_scored_groups` chỉ group được chấm.

- Binary AI: score>=0.5. Verdict `<0.3` real; `[0.3,0.7]` uncertain; `>0.7` AI.
- Tái sử dụng `models.train.metrics`: accuracy gồm cả uncertain; precision/recall theo AI. Khi mẫu số0 giữ quy ước số0 của hàm, thêm `defined=false`/denominator và CI null. Bổ sung FPR/FNR để đọc real-only/AI-only.
- Pair chỉ gồm con **và cha đều có score hợp lệ**, ghép bằng ID. Parent có thể được lặp trong bảng matched nếu có nhiều con; mỗi dòng tương ứng đúng một cặp. `n_unpaired_or_failed_parent` báo phần không tham gia pairing, không âm thầm bỏ mẫu lỗi khỏi số tổng.
- Flip là khác **verdict ba trạng thái**. Accuracy degradation = parent_matched - child_matched (dương là xấu hơn); các delta khác = child - parent. Kèm metrics matched, số cặp, CI và ma trận chuyển verdict 3×3: hàng cha, cột con, thứ tự `likely_real,uncertain,likely_ai`.
- Không có cha/cặp hợp lệ: pairing metrics/CI null, ghi lý do; không điền flip0. Parent chỉ một số nguồn không được so với accuracy toàn bộ cohort cha.

CI: 2000 bootstrap, seed42, percentile2.5/97.5, lấy group có hoàn lại trong từng source×label; mọi ảnh/cặp trong group dùng cùng trọng số, không nhân N độc lập bằng số biến thể. Group trùng có nhiều source giữ nguyên cả group trong một stratum source tổng hợp. Cùng mẫu bootstrap cho cha/con. Dưới2 group độc lập hoặc metric/replicate không xác định thì CI null, kèm `n_boot_valid`/reason; không đổi NaN thành0. CI không bảo đảm đại diện toàn upstream; stratum rất ít group có thể tạo CI hẹp/thoái hóa, cần ghi trong phân tích.

Report lưu model/manifest/protocol/predictions SHA, runner commit/tham chiếu, analysis commit/dirty=false, Python/OS, profile/ngưỡng/bootstrap và trạng thái pending review; bỏ interpreter/cwd path máy cá nhân. Các input được hash lại sau phân tích để phát hiện đổi bytes trong lúc chạy. Không ghi QA/release approved.

## Phân tích và bàn giao Lực

Khi có số thật, bổ sung bảng theo cohort/source/biến đổi và trả lời: biến đổi nào flip nhiều nhất; degradation lớn nhất; FPR real/recall AI thay đổi; các chuyển sang uncertain hay kết luận sai; N/group/CI và cohort thiếu. Chưa có dữ liệu thì giữ trạng thái thiếu, không dựng bảng ví dụ thành kết quả.

Không suy ra JPEG là nguyên nhân shortcut từ một mức suy giảm, không tune model/ngưỡng, không quy mọi ảnh điện thoại phải real hoặc mọi biến thể phải giữ verdict. Accuracy94,53% lịch sử chỉ cho384 ảnh đã lọc, không gắn vào cohort mới.

Gói gửi #49 gồm `artifacts/robustness.json`, predictions CSV, protocol, manifest snapshot/checksums, log provenance/phiên bản và tài liệu phân tích. Chỉ commit helper/tests, README, tài liệu/report công bố đã rà đường dẫn. Ảnh/model/cache và evidence thô ở ngoài Git. Không đóng #52 hoặc ghi QA approved khi chỉ có fixture hay cohort còn thiếu.

## Kiểm thử

```text
python -m ruff check .
python -m ruff format --check .
python -m pytest tests/test_analyze_robustness.py tests/test_evaluate.py -q
python -m pytest --cov=app --cov-fail-under=70 -q -ra
```

Tests dùng ảnh/predictions tổng hợp, không unpickle model, không tải CLIP. Kiểm biên ngưỡng, matched metrics, lịch sử/split, hash/ID, partial/missing, bootstrap theo group và tái lập, provenance sạch, invalid scores và output không ghi đè. Fixture không thay cho thực nghiệm robustness hoặc QA #49. Kết quả lệnh thực tế được ghi trong PR sau khi chạy.

Kết quả local ngày 11/11/2026, Windows/Python3.12.14, `PYTHONUTF8=1`: full suite **684 passed, 0 failed, 2 skipped, 1 xfailed**, 154,88s, app coverage **98,52%**. Hai skip do Locust tùy chọn; xfail strict scorer treo vô hạn có sẵn trên main. Sau khi bổ sung guard model manifest phải là JSON object và hai ca kiểm tương ứng, chạy lại helper + evaluator: **71 passed, 0 failed, 0 skipped**, 9,09s. Ruff check qua; format check **114 files already formatted**; JSON/liên kết nội bộ/scope và `git diff --check` qua. Không chạy lại suite đầy đủ sau guard cuối; các test liên quan đã chạy trên code cuối. Không có inference/model-test, Docker/Linux hoặc QA độc lập trong lượt này.
