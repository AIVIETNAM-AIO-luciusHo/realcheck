# Mở rộng dữ liệu và train lại — 10/11/2026

Đã tải bổ sung, lọc dữ liệu và train một **model ứng viên** trên 9.936 ảnh. Model cải thiện trên mẫu Reddit và validation nguồn mới, nhưng giảm trên validation GenImage giữ nguyên và mẫu OpenFake core/test. Chưa đủ cơ sở thay model đang phục vụ hoặc nghiệm thu release. Toàn bộ số đo, hash và provenance đã bỏ đường dẫn cá nhân nằm trong [báo cáo JSON](reports/ml-data-expansion-20261110.json).

**Phạm vi PR #61: chỉ KAN-44, mở rộng dữ liệu và train candidate thử nghiệm.** Bàn giao/chốt artifact cho API thuộc [issue #39](https://github.com/AIVIETNAM-AIO-luciusHo/realcheck/issues/39), được xử lý ở nhánh riêng; PR này không hoàn thành hoặc đóng issue đó. Không tuyên bố hoàn tất KAN-37/39/51 qua PR này.

`models/score.py` mở rộng danh sách dataset được loader chấp nhận sang mixed v2/v3 để kiểm/nạp candidate hợp lệ. Đây là thay đổi ở đường nạp model, dù không thay hành vi cho artifact GenImage hiện hành; cần được reviewer ML đánh giá. Không thay đường dẫn model mặc định, cấu hình API hoặc chọn candidate mới làm model phục vụ.

## Đối chiếu nghiệm thu KAN-44 / T024

**KAN-44 chưa đủ điều kiện đóng.** Theo sáu nhóm tiêu chí đang review, khoảng **4/6 có bằng chứng kỹ thuật** trong PR; đây không phải xác nhận QA độc lập hay sáu AC đã được duyệt trên Jira.

| Nhóm tiêu chí | Bằng chứng trong PR | Kết luận review |
|---|---|---|
| CLIP cố định, embeddings đúng hợp đồng | Revision đã ghim, encoder frozen/eval, float32 L2; parity validation có báo cáo | Cơ bản đáp ứng về kỹ thuật |
| Manifest và normalization metadata | Feature manifest ghi version/hash/số dòng; bundle ghi normalization version 1 | Cơ bản đáp ứng về kỹ thuật |
| Train dùng `load_features` kiểm manifest | `models.train.train` gọi loader chung; regression từ chối sai version/hash/số dòng/cache | Cơ bản đáp ứng về kỹ thuật |
| Fit trên train, chọn tham số trên validation | C-grid cố định, seed42, C10 chọn bằng 1.860 validation; test không dùng để chọn C | Cơ bản đáp ứng về kỹ thuật |
| Phụ thuộc dữ liệu chính T023 | Lần train này dùng manifest mở rộng tự dựng `realcheck_mixed_v3`, SHA labels `2997cdb9…`; không phải bàn giao migration dữ liệu chính sau T023 | **Chưa đáp ứng phụ thuộc của T024** |
| QA độc lập / nghiệm thu artifact | `independent_qa_approved=false`; còn review dữ liệu, lịch sử/near-duplicate và artifact | **Chưa đáp ứng** |

T024 của [spec 001](../specs/001-unified-image-normalization/tasks.md) phụ thuộc **T011 và T023**. PR #61 chỉ là thí nghiệm candidate cho phần mở rộng nguồn; việc fit trên code sạch không thay thế dữ liệu chính đã được Loan bàn giao sau T023 hoặc QA của Lực. Không tick T024, không đóng KAN-44 chỉ bằng merge PR này.

Để hoàn tất phần còn lại: nhận manifest/dữ liệu chính sau T023 cùng hash, normalization version, split và biên bản kiểm; extract lại vào cache riêng, train bằng `load_features` trên commit sạch, kiểm version/parity rồi bàn giao artifact/report đúng hash cho QA độc lập. Không ghi đè dữ liệu/model hiện có hoặc mở lại test đã tiếp xúc để thay cho bước nghiệm thu này.

Kiểm lại khi bổ sung review: `python -m pytest tests/test_ml_pipeline.py tests/test_extract_features.py tests/test_domain_expansion.py tests/test_train_expansion.py -q` → **56 passed, 0 failed, 0 skipped**, 9,95 giây; `git diff --check` qua. Đây là test hợp đồng/fixture, không nghiệm thu dữ liệu T023 hoặc chất lượng model thay QA. Hai report thí nghiệm gốc/fit sạch được giữ nguyên; lượt chỉnh tài liệu này không train hoặc chấm test.

## Dữ liệu thực tế

Tận dụng 18.332 ảnh hợp lệ đã tải ngày 08/11, gồm ảnh được chọn và dự phòng; tải thêm để có **28.007 ứng viên hợp lệ**. Đây là pool để lọc/lấy mẫu, không phải số ảnh fit. 157 trường hợp tải bổ sung bị loại ở bước giải mã/kích thước; các ảnh bị loại của lần tải cũ vẫn giữ nhật ký riêng.

| Nguồn | Thật được giữ | AI được giữ | Cách lấy |
|---|---:|---:|---|
| Tiny-GenImage | 2.300 | 2.000 | ADM, GLIDE, Midjourney, SD1.5, Wukong: mỗi loại 400; trải đều **14 shard train thực có**, khác con số 11 trong đề xuất |
| OpenFake core/train | 966 | 1.378 | LAION/Pexels và các model AI; lọc type video, tên anime và ảnh không đạt screen ảnh chụp |
| COCO | 885 | 0 | Qua mirror CommunityForensics-Small |
| VISION | 590 | 0 | Đủ 35 thiết bị, 16–17 ảnh/thiết bị |
| FFHQ | 470 | 0 | Qua mirror CommunityForensics-Small |
| Landscapes HQ | 415 | 0 | Qua mirror CommunityForensics-Small |
| Community Forensics AI | 0 | 1.921 | 1.300 diffusion, 335 nhóm chân dung, 286 nhóm phong cảnh; **354 tên công cụ chuẩn hóa**, tối đa 10 ảnh/công cụ |
| **Tổng trước tách validation mới** | **5.626** | **5.299** | **10.925 ảnh** |

Các số trong đề xuất là mức tối đa. Sau lọc thiếu 214 OpenFake real, 392 OpenFake AI, 135 AI chân dung và 69 AI phong cảnh so với mức đó; không bù bằng ảnh test hoặc ảnh không đạt screen.

Nguồn được khóa revision: [Tiny-GenImage](https://huggingface.co/datasets/TheKernel01/Tiny-GenImage), [OpenFake](https://huggingface.co/datasets/ComplexDataLab/OpenFake), [CommunityForensics-Small](https://huggingface.co/datasets/OwensLab/CommunityForensics-Small). Revision đầy đủ trong JSON. COCO/VISION/FFHQ/Landscapes HQ lấy qua mirror này, không tải trọn các bộ gốc. Giữ nguyên điều kiện giấy phép của từng nguồn; đây là lượt thử nghiệm nghiên cứu.

## Lọc và chia tập

- Chuẩn hóa version 1 không đổi: EXIF → RGB → BICUBIC 256×256 → JPEG95 một lần. CLIP revision cố định, embedding float32 L2, encoder frozen/eval.
- Dùng CLIP text/image cosine để screen ảnh chụp so với anime, tranh, đồ họa, 3D nhân vật và ảnh có chữ; margin tối thiểu 0. Đây là **nhãn tự động**, không phải QA bằng mắt cho mọi ảnh. Nhóm chân dung/phong cảnh cũng là pseudo-topic, có thể nhầm.
- Đã xem 60 thumbnail phân tầng và 32 mẫu sát biên thuộc train/validation. Trước fit, bổ sung prompt screen và bỏ fallback chủ đề theo metadata nguồn sau khi thấy ảnh hoạt hình/sản phẩm lọt vào nhóm chưa phù hợp. Giữ cả hai lần chuẩn bị; chưa có detector test scores ở giai đoạn chỉnh screen. Vẫn còn trường hợp mơ hồ ở biên, cần nhóm review thêm.
- Trong bước chọn cuối, 8.438 ứng viên bị loại bởi screen ảnh chụp; 262 bởi metadata/generator; 55 trùng/gần trùng; 3 gần validation/test lịch sử. Tách riêng 6 trường hợp trùng/gần lịch sử khi lấy mẫu đánh giá. Đây không phải thống kê toàn bộ ảnh upstream.
- So hash pixel và dHash Hamming ≤4 với các manifest lịch sử đang có; loại trùng trong pool và giữ test mới ngoài train. Chỉ kiểm được lịch sử được cung cấp; không có manifest mới 1.309/1.603/test kín được nhắc trong hồ sơ cũ để xác nhận độc lập với các cohort đó.

| Tập | N | Quy tắc |
|---|---:|---|
| Train mới | **9.936** | 5.132 thật / 4.804 AI; Tiny chỉ train; không ghép thêm 3.988 train của model cũ |
| Validation nguồn mới | **989** | Khoảng 15% nguồn ngoài Tiny; VISION giữ nguyên thiết bị |
| GenImage validation cũ | **871** | Giữ đúng ảnh/nhãn/split để đối chiếu baseline |
| OpenFake core/test | **1.040** | 520 thật / 520 AI, chỉ đánh giá sau khóa model |
| OpenFake reddit/test | **840** | 420 thật / 420 AI, chỉ đánh giá sau khóa model |

VISION validation gồm **D06, D10, D13, D21, D32**; ảnh của các thiết bị này không vào train. Tiny train không vào validation. Tên generator OpenFake test đã chuẩn hóa được loại khỏi train; alias chưa biết và việc dùng chung kiến trúc gốc vẫn cần review, không tự chứng nhận toàn bộ generator đều unseen giữa mọi nguồn.

CSV huấn luyện giữ thêm 849 GenImage test cũ để tương thích kiểm manifest, **không tính score** của chúng. Holdout 384 ảnh đã mở trong thí nghiệm trước cũng không được chấm lại. Các tập OpenFake mới nằm riêng trong selection/predictions.

## Train và kết quả

Giữ CLIP `sentence-transformers/clip-ViT-B-32` revision `327ab6726d33c0e22f920c83f2ff9e4bd38ca37f`; **train lại Logistic Regression từ đầu**, không fine-tune CLIP. Grid C cố định `[0.01, 0.1, 1, 10, 100]`, seed 42, chỉ fit train. Chọn C bằng accuracy gộp 1.860 validation; chọn **C=10**, accuracy gộp **84,03%**. Khóa binary threshold 0.5, low/high 0.3/0.7 trước test.

Baseline là candidate cũ SHA `e5718345…69494`, không phải artifact mặc định cũ hơn trong `models/clip_probe.joblib`, và không được gọi là baseline 87,39%/83,1% chưa nhận được artifact.

**Bảng dưới chỉ thuộc model mixed gốc SHA `26b8882963b9224eb72d2010b46dd390dbd3545173c40c4e452908fbd596c28d`, train trên source `dirty=true`. Không phải kết quả test của bản fit sạch `7164eeca…`.**

| Cohort | N | Accuracy baseline | Accuracy mixed gốc `26b888…` | FPR thật baseline → mixed gốc |
|---|---:|---:|---:|---:|
| GenImage validation giữ nguyên | 871 | 97,24% | **86,45%** | 2,14% → 14,01% |
| Validation nguồn mới | 989 | 57,94% | **81,90%** | 80,57% → 15,79% |
| OpenFake core/test lấy mẫu | 1.040 | 84,13% | **80,38%** | 28,85% → 25,00% |
| OpenFake reddit/test lấy mẫu | 840 | 56,67% | **75,95%** | 82,86% → 37,38% |

Accuracy binary tính **mọi ảnh**, gồm vùng Chưa chắc; không lấy decided-only accuracy thay thế. Model mới có uncertain rate 24,42% trên core và 22,26% trên Reddit. Recall AI core giảm 97,12% → 85,77%, Reddit giảm 96,19% → 89,29%: giảm báo nhầm ảnh thật đi kèm bỏ sót AI nhiều hơn. Không đủ bằng chứng quy nguyên nhân cho một loại shortcut cụ thể từ các số này.

Đây là **mẫu shard/row-group có giới hạn**, không phải điểm toàn bộ OpenFake hoặc mẫu uniform toàn upstream. OpenFake core/reddit nay đã mở; không tune ngưỡng/C theo chúng rồi gọi lại là test chưa từng xem. Candidate chưa có kết quả GenImage test mới để khẳng định AC-25.

## Artifact và kiểm chứng

Đường dẫn tính từ repo root, output local không đưa ảnh/weights/đường dẫn cá nhân vào Git:

| Artifact | Đường dẫn |
|---|---|
| Probe mới + checksum | `outputs/data-expansion-20261110/run-v2/mixed-v3.joblib`, `.joblib.sha256` |
| Manifest train/val và legacy test chưa chấm | `outputs/data-expansion-20261110/run-v2/labels.csv` |
| Metadata nguồn và lựa chọn ảnh | `outputs/data-expansion-20261110/downloads/pool.jsonl`, `run-v2/selection.jsonl` |
| Raw/processed mới | `outputs/data-expansion-20261110/downloads/` |
| Raw/processed tái sử dụng | `../outputs/realcheck-domain-expansion/acquired-01/` |
| Train, so sánh validation | `run-v2/training.json`, `run-v2/validation-comparison.json` trong thư mục output trên |
| Protocol, used marker, predictions, test | `run-v2/frozen-model.json`, `openfake-test-used.json`, `openfake-predictions.csv`, `openfake-evaluation.json` |

Model SHA256: `26b8882963b9224eb72d2010b46dd390dbd3545173c40c4e452908fbd596c28d`. Dataset label SHA256: `2997cdb9a7899f6daa4807fe024b87bf4150ef2286473676fa59d31ef2a22c5d`. Probe cần CLIP/cache đúng revision và dependencies ML, không phải checkpoint chứa toàn bộ CLIP.

Đã nạp model/CLIP thật và đối chiếu **8 nguồn validation**: JPEG/tensor train–serve khớp, sai khác score lớn nhất **6,56e-7 < 1e-5**; encoder frozen/eval. Đếm lại 1.880 dòng predictions, tất cả metrics khớp report. Model/labels/features/protocol khớp hash; hai model cũ không đổi. Raw SHA ảnh chẩn đoán Tháp Rùa không xuất hiện trong train, không chứng nhận đã loại mọi bản biến đổi của ảnh đó.

Kiểm tra cuối của lần train trước khi đồng bộ main: **514 passed, 1 skipped, 1 xfailed**, 99,35 giây; Ruff check/format đạt; `git diff --check` không có lỗi whitespace (chỉ thông báo CRLF ở tài liệu có sẵn). Skip là dependency Locust tùy chọn; xfail có sẵn cho scorer treo vô hạn. Không có skip/xfail mới. Lượt train này không đo lại coverage hoặc chạy lại Docker/Linux.

Lệnh local đã dùng; tải mẫu cần catalogue và pool cũ đang có trên máy, không phải luồng bootstrap từ repo sạch:

```text
python -m scripts.download_expansion --output outputs/data-expansion-20261110/downloads
python -m scripts.train_expansion --downloads outputs/data-expansion-20261110/downloads --output outputs/data-expansion-20261110/run-v2 --prepare-only
python -m scripts.train_expansion --downloads outputs/data-expansion-20261110/downloads --output outputs/data-expansion-20261110/run-v2
```

Dùng `HF_HOME=.cache/huggingface`, `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` cho bước ML. Download cần mạng. Source của lần train là `9a3ca19` với working tree dirty; hash từng module nằm trong báo cáo, không giả đây là clean release/CI. Các bước cache/kiểm model thật có log local riêng trong output.

## Đồng bộ code mới trước khi push

Nhánh `kiet/ml-data-expansion-20261110` đã pull/rebase lên `origin/main` tại `274f869ada646400d00f832b0aa3723c219d7742`, không có conflict. Commit code ML được kiểm là `48de1a0`. Sau review, hồ sơ bàn giao #39 và rà soát bốn task được tách khỏi diff; cùng report tái lập sạch, PR B có 15 file cho KAN-44. CSV Jira, dữ liệu/cache/weights và thay đổi Backend local ngoài task được giữ riêng. Việc implementation cũ đã có trên main không phải bằng chứng PR #61 đóng các task khác.

Kiểm tra local trên bản đã đồng bộ, Windows/Python 3.12.14, với `PYTHONUTF8=1`:

```text
python -m pytest --cov=app --cov-fail-under=70 -q -ra
650 passed, 2 skipped, 1 xfailed; app coverage 98,52%; 199,35 giây
python -m ruff check .                 → passed
python -m ruff format --check .        → 114 files already formatted
git diff origin/main...HEAD --check    → passed
```

Hai skip là dependency Locust tùy chọn; xfail scorer treo vô hạn đã có trên main. Lượt chạy Windows mặc định gặp CP1252 khi một test Docker mới của main đọc file CI tiếng Việt; cùng test và toàn bộ suite đều qua khi chạy UTF-8, không sửa Dockerfile/test ngoài phạm vi. Đây là kiểm tra code sau tích hợp, không phải lần train hay mở lại model-test; provenance và số đo thí nghiệm trong JSON giữ nguyên. Chưa thay kiểm chứng này bằng CI từ xa hoặc build Docker/Linux mới.

## Kết luận sử dụng

### Tái lập bước train trên commit sạch sau review

Đã fit lại từ đúng labels/features đã khóa trên code commit sạch **`e4b6d29018144d86c515262750a0a28aa56835f4`**, `dirty=false`, seed 42, `OMP_NUM_THREADS=4`. [Bằng chứng tái lập](reports/ml-clean-repro-20261110.json) ghi import source từ worktree sạch qua `PYTHONSAFEPATH=1`/`PYTHONPATH`; cwd chỉ dùng để resolve đường dẫn dữ liệu cũ. Không tải/trích lại dữ liệu hoặc mở test.

Kết quả vẫn chọn **C=10**, validation **84,032258%/1.860**, cùng confusion matrix. Model tái lập SHA **`7164eeca27ce1d30f73ed70451cafd2a4c26423352a04a2cf44ff26685e19678`** khác bytes bản gốc; AUROC là **0,9172648683** so với **0,9172683378** của lần gốc. Chưa xác định nguyên nhân khác bytes; không suy ra hai artifact có cùng dự đoán test từ validation giống nhau. Không gán số OpenFake test đã lưu cho model tái lập, không đổi model phục vụ. Report gốc tiếp tục giữ đúng `dirty=true`; provenance của acquisition/normalization chưa được biến thành clean run bằng bước fit lại này.

| Thuộc tính | Mixed gốc `26b888…` | Fit sạch `7164ee…` |
|---|---|---|
| Commit chạy train | `9a3ca19…`, `dirty=true` | `e4b6d29…`, `dirty=false` |
| Labels/features | Cache mở rộng đã khóa | Cùng cache đã khóa, không trích lại |
| C / accuracy validation, N=1.860 | 10 / 84,032258% | 10 / 84,032258% |
| AUROC validation | 0,9172683378 | 0,9172648683 |
| OpenFake core/test, N=1.040 | 80,38% | **Chưa đánh giá** |
| OpenFake reddit/test, N=840 | 75,95% | **Chưa đánh giá** |
| JSON nguồn | [Thí nghiệm gốc](reports/ml-data-expansion-20261110.json) | [Fit sạch](reports/ml-clean-repro-20261110.json), `test=null` |

Fit sạch chỉ xử lý provenance của **bước train**, chưa hoàn tất toàn bộ KAN-44. Hai model vẫn là candidate thử nghiệm; số liệu test cũ gắn với hash model gốc. OpenFake đã được mở, nên không chạy lại rồi mô tả như test unseen hoặc tune theo kết quả đó.

Lệnh chạy từ workspace dữ liệu gốc, sau khi chỉ đường `PYTHONPATH` tới worktree PR sạch và đặt `PYTHONSAFEPATH=1`, `OMP_NUM_THREADS=4`:

```text
python -P -m models.train --labels outputs/data-expansion-20261110/run-v2/labels.csv --features outputs/data-expansion-20261110/run-v2/features --dataset realcheck_mixed_v3 --output outputs/data-expansion-20261110/clean-repro/mixed-v3.joblib --report outputs/data-expansion-20261110/clean-repro/validation.json --binary-threshold 0.5
```

Giữ model mới ở trạng thái thử nghiệm: FPR Reddit còn 37,38%, validation GenImage và core accuracy giảm. Chưa đổi artifact phục vụ, tune ngưỡng sau test hoặc phê duyệt QA/release. Lần phát triển tiếp theo nên đánh giá lại tỷ lệ trộn dữ liệu cũ/mới và chất lượng screen bằng train/validation; đánh giá độc lập tiếp theo cần cohort/protocol phù hợp, ghi rõ các mẫu OpenFake này đã được mở.
