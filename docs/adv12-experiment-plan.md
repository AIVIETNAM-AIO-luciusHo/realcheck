# ADV-12: kế hoạch thí nghiệm giảm ảnh thật bị gọi "Ảnh AI" (#144)

**Bản nháp cho Kiệt (thí nghiệm), Loan (dữ liệu, chạy đánh giá cuối), Lực (khóa protocol, kiểm).** Không đổi model phục vụ API: đổi model là PR riêng kèm QA độc lập (#59). Mọi số dưới đây là **chưa có**; bảng chỉ nêu cách đo.

## 1. Quy tắc (bắt buộc)
- **ADV-06 (`docs/cohorts-adv06.md`) chỉ là tập phát triển.** Nó đã dùng để so sánh nên không còn độc lập; không báo là kết quả cuối.
- **Chọn model, đặc trưng, ngưỡng và vùng "Chưa chắc" chỉ trên validation.** Đánh giá cuối (bộ 40 ảnh mới #116 và split test GenImage) chấm **một lần** theo protocol đã khóa, không chỉnh theo kết quả.
- Báo đúng số kể cả khi không cải thiện. Không ghi "đạt 90%" cho ảnh điện thoại. Không đặt ngưỡng cứng (mẫu nhỏ).
- Giữ nguyên `normalize_image`, e571 và `models/clip_input.py`: các thí nghiệm dùng công cụ phụ trợ ở các PR ADV-12 riêng.
- Tách train/validation/test **theo `group_id`** (#99, PR #113). Ảnh thật bổ sung phải ghi nguồn, giấy phép, hash (Loan); ảnh nhóm tự thu giữ trên máy, chỉ gửi hash và manifest.

## 2. Công cụ (các PR ADV-12; chỉ dùng được sau khi merge)
| Công cụ | Dùng để |
|---|---|
| `scripts/compare_models.py` (C-16) | So hai file điểm trên cùng ID: AUROC, ảnh thật bị gọi AI, recall, "Chưa chắc", theo `source`, hiệu A − B và CI bootstrap theo group |
| `scripts/calibrate_scores.py` (C-17) | Platt/temperature trên validation, ECE/Brier/NLL, chọn ngưỡng theo mục tiêu FPR |
| `models/augment.py` (C-18) | `jpeg_recompress`, `downscale_upscale`, `screenshot_like`, `apply_random` (ghi danh sách phép vào manifest) |
| `models/clip_layers.py` (C-19) | CLS của nhiều lớp ViT (không cùng không gian với e571) |
| `scripts/adv12_run.py` (C-21) | `score` (e571 thật, E0), `extract` (e571 hoặc nhiều lớp, tăng cường chỉ train) và `fit` (LR chỉ trên train, xuất điểm val/test) |
| Có sẵn | `models.extract_features`, `models.train`, `scripts.verify_ml`, `models.evaluate` (xem `docs/ml-final-experiment.md`) |

Định dạng điểm cho C-16/C-17: CSV `sample_id,label,score[,group_id,source]`. `predictions.csv` của `models.evaluate` có `image_sha256`, `label`, `score`, `source`; đổi tên `image_sha256` thành `sample_id` (và thêm `group_id` từ `data/labels.csv` theo `filepath`) trước khi so.

## 3. Bảng thí nghiệm

| Mã | Mô tả | Dữ liệu và split | Cách chạy | Ghi chú / chưa có sẵn |
|---|---|---|---|---|
| **E0** | e571, lớp cuối ViT-B/32, LR (đối chứng) | Cùng bộ dữ liệu E1..E5; train/val/test theo `group_id` | `REALCHECK_MODEL_PATH=<e571.joblib> python -m scripts.adv12_run score --labels data/labels.csv --split val --output run/e0_val.csv` (model THẬT qua `models.score`, kiểm checksum; thêm `--split test` chỉ khi protocol cho phép). Điểm tham chiếu: ảnh `syn_jpeg_00_400x300.jpg` ra 0,9993029832839966 | Hash model `e5718345…9494`; cần CLIP cache offline (`HF_HUB_OFFLINE=1`) |
| **E1** | E0 + tăng cường khi train | Như E0; `--augment p` chỉ áp lên ảnh **train** (val/test không đổi); phép đã áp ghi vào `.augment.jsonl` | `python -m scripts.adv12_run extract --labels data/labels.csv --output run/e1.npz --encoder last --augment 0.5 --augment-seed 42` rồi `python -m scripts.adv12_run fit --features run/e1.npz --output-dir run/e1 --C 10 --seed 42` | `scripts/adv12_run.py` (C-21) không sửa `models.train`/`extract_features`; `fit` ghi điểm val/test cho `compare_models` |
| **E2** | Đặc trưng nhiều lớp (kiểu RINE) | Như E0 | `python -m scripts.adv12_run extract --labels data/labels.csv --output run/e2.npz --encoder layers --layers 6,9,12` rồi `fit` như E1 (thêm `--augment` nếu muốn kết hợp E1) | Đặc trưng nhiều lớp khác không gian e571 (không đưa vào `models.score`); `--model-id`/`--revision` chọn encoder (E3 dùng ViT-L/14) |
| **E3** | Encoder lớn ViT-L/14 | Như E0 | `python -m scripts.adv12_run extract ... --encoder layers --layers <lớp, vd 24 hoặc 12,18,24> --model-id openai/clip-vit-large-patch14 --revision <commit>` rồi `fit` | **Cần tải trọng số** (mạng, dung lượng lớn, ghim revision, ghi hash); chạy CPU chậm hơn nhiều |
| **E4** | Hiệu chuẩn điểm và chọn ngưỡng | Validation riêng (không dùng ADV-06 và test) | `python -m scripts.calibrate_scores --scores val.csv --target-fpr <X>` cho model tốt nhất của E0..E3 | Ngưỡng chọn trên validation; khóa trước khi chấm cuối |
| **E5** | Ghép e571 và mixed-v3 (trung bình hoặc stacking) | Điểm của hai model trên cùng validation | Trung bình điểm hoặc LR trên điểm (fit chỉ trên validation) rồi `compare_models` | Chỉ làm sau khi E0..E4 có số; 86,45% GenImage val là số của mixed gốc `26b888…` (dirty=true), không phải bản fit sạch `7164ee…`; ghi đúng SHA khi trích (xem `docs/ml-data-expansion-20261110.md`) |

Mỗi thí nghiệm so với E0 bằng `python -m scripts.compare_models --a <điểm E0> --b <điểm Ex> --output <json>`, cùng ID, cùng seed (42), 2000 replicate.

### Lưu ý về hiệu chuẩn và ngưỡng (E4)
- Platt và temperature scaling **đơn điệu tăng** nên KHÔNG đổi AUROC hay thứ tự điểm: không tự "sửa" ảnh thật bị gọi AI nếu ngưỡng không đổi. Cải thiện chỉ đến từ đặc trưng/dữ liệu (E1..E3, E5) hoặc từ việc đổi ngưỡng.
- Ngưỡng chọn trên validation GenImage **chưa chắc chuyển sang miền ảnh điện thoại** (điểm trung vị ảnh điện thoại 0,97); kiểm trên tập phát triển ADV-06 và ghi như giới hạn.
- `calibrate_scores` từ chối Platt có hệ số ≤ 0 (điểm tương quan ngược) và ghi cảnh báo cho điểm suy biến; ngưỡng dùng `score >= t`, còn "Ảnh AI" của sản phẩm là `score > high`.
- Ràng buộc 512 chiều nằm ở `models/clip_input.py` (`FEATURE_DIM`) và `models/score.py` (`Scorer`), không phải `models/train.py`; đặc trưng nhiều lớp/ViT-L/14 vì thế không đưa vào `models.score`.

## 4. Tiêu chí báo cáo (mỗi thí nghiệm, trên **cả hai miền**)
1. **Ảnh thật ngoài GenImage** (phát triển: ADV-06; cuối: #116): tỉ lệ ảnh thật bị gọi AI ở ngưỡng 0,5 và ở ngưỡng cao đã khóa, số "Chưa chắc", kèm CI bootstrap theo group và cỡ mẫu.
2. **GenImage** (validation khi chọn, test khi chấm cuối): accuracy, AUROC, recall ảnh AI theo từng nguồn (SD1.4, Midjourney, GLIDE), kèm CI. **Không được tụt đáng kể so với E0** (nêu mức tụt, không đặt ngưỡng cứng).
3. Hiệu A − B kèm CI từ `compare_models`; chỉ gọi là "cải thiện" khi CI không chứa 0, ngược lại ghi "chưa phân biệt được".
4. Hiệu chuẩn: ECE/Brier/NLL trước và sau (E4).
5. Ghi hạn chế: mẫu ảnh điện thoại nhỏ và chủ yếu iPhone 11; bộ ảnh công khai có thể không giống ảnh điện thoại/Zalo; shortcut JPEG/dung lượng (ADV-10) chưa loại trừ; không kết luận "nhận ra dấu vết AI tổng quát".

## 5. Mẫu protocol JSON (Lực khóa trước khi chạy; mỗi protocol chạy một lần)
Theo kiểu `docs/shortcut-adv10.protocol.example.json`. Giá trị `REPLACE_*` do người chạy điền, Lực kiểm hash rồi mới đổi `status` thành `locked`.
```json
{
  "schema_version": 1,
  "status": "proposed",
  "experiment": "E0|E1|E2|E3|E4|E5",
  "code_commit": "REPLACE_WITH_CLEAN_COMMIT",
  "model": {"path": "REPLACE", "sha256": "REPLACE_64_HEX"},
  "baseline_model": {"sha256": "e5718345abf157d3334c3503cdce441892462f19b149e28658d71e0a59b69494"},
  "splits": {
    "labels": {"path": "labels.csv", "sha256": "REPLACE_64_HEX", "has_group_id": true},
    "train": {"sha256": "REPLACE_64_HEX", "n": 0},
    "validation": {"sha256": "REPLACE_64_HEX", "n": 0},
    "final_eval": {
      "genimage_test": {"sha256": "REPLACE_64_HEX", "n": 0},
      "new_phone_116": {"sha256": "REPLACE_64_HEX", "n": 0}
    },
    "development_only": {"adv06": {"sha256": "REPLACE_64_HEX", "n": 0}}
  },
  "seeds": {"train": 42, "augment": 42, "bootstrap": 42, "replicates": 2000},
  "augment": {"p": 0.5, "manifest": "REPLACE_PATH"},
  "thresholds": {"binary": 0.5, "low": 0.3, "high": 0.7, "locked_on": "validation", "target_fpr": "REPLACE"},
  "runtime": {"python": "3.12.14", "pillow": "13.0.0", "pip_freeze_sha256": "REPLACE_64_HEX", "environment": {"python": "REPLACE", "packages_sha256": "REPLACE_64_HEX"}},
  "independent_qa_approved": false,
  "notes": "Model và ngưỡng chọn trên validation; final_eval chấm một lần; ADV-06 chỉ phát triển."
}
```
Trường `runtime.environment` lấy từ `python -m models.run_info` trong đúng venv chạy (PR #135); lượt thật lưu `pip freeze`.

## 6. Thứ tự và điều kiện dừng
1. E0 (đối chứng) → 2. E1, E2 (rẻ) → 3. E4 trên model tốt nhất → 4. E3 (nặng, cần tải) → 5. E5 (chỉ khi có số).
Dừng và báo (không chỉnh) khi: hash/split không khớp protocol; ảnh test lọt vào train/validation (kiểm bằng `group_id` và dHash); GenImage tụt nhiều mà ảnh thật không cải thiện; kết quả cuối lệch kỳ vọng. Lực kiểm chuỗi hash, tính lại số từ điểm đã lưu, ghi lệch.

## 7. Rủi ro
Mẫu nhỏ dễ học vẹt thiết bị; thêm ảnh thật có thể làm tụt nhận diện ảnh AI; nén và dung lượng có thể thành shortcut mới nếu nguồn thật/AI khác nhau; giấy phép dữ liệu phải kiểm trước khi dùng.
