# ADV-12d: giấy phép, group_id và kiểm dữ liệu bộ mở rộng (#160)

**Người làm và chạy:** Loan, 17/11/2026, máy macOS arm64, Python 3.12.14, Pillow 13.0.0. **Chưa có người tính lại độc lập.** Bộ kiểm: `realcheck_mixed_v3` run-v2 (#54, [ADV-09](data-review-adv09.md)); bốn việc chuyển từ ADV-09 mục 4, 6, 7, 7a. Không đổi ảnh, nhãn, split, model hay ngưỡng; không train, không chấm model.

| # | Việc | Trạng thái |
|---|---|---|
| 1 | Giấy phép Landscapes HQ | **Xong**: tra được giấy phép từng ảnh cho 415/415 ảnh |
| 2 | `group_id` và chia validation theo group | **Xong** theo D01: 14.525 group, 0 group vắt split; manifest mới |
| 3 | `check_data`, metadata audit, dHash trên ảnh | **Một phần**: mẫu 392 ảnh; metadata audit chưa làm |
| 4 | Kiểm tay nhãn "thật" LAION/Pexels | **Xong lượt một người xem**: 119/119 ảnh; "có thể AI" LAION 23/51, Pexels 25/68 |

Manifest: [`data/metadata/realcheck_mixed_v3/adv12d/`](../data/metadata/realcheck_mixed_v3/adv12d/README.md), SHA256 `1700ec92ad3ace6dad0aab85ae7c72daadd3350e860bf084668a02c8a8531c5a`.

## 1. Giấy phép Landscapes HQ

Trang chính thức [`lhq.md`](https://github.com/universome/alis/blob/master/lhq.md) ghi: mỗi ảnh có một trong các giấy phép Unsplash License, CC BY 2.0, CC BY-NC 2.0, Public Domain Mark, CC0, US Government Work, tra theo `metadata.json`; cả bộ phát hành theo CC BY 2.0. README của repo ghi các giấy phép đó "cho phép phân phối và dùng cho nghiên cứu".

Đã tải `metadata.json` từ link chính thức (SHA256 `a7a0a3a9…295b`, 90.000 dòng) và ghép theo `image_name` của CommunityForensics-Small (tên file LHQ, ví dụ `0073703.png`). **415/415 ảnh có trong metadata:**

| Giấy phép từng ảnh | Train | Validation |
|---|---:|---:|
| Unsplash License | 250 | 45 |
| CC BY 2.0 | 54 | 7 |
| CC BY-NC 2.0 | 44 | 8 |
| Public Domain Mark | 3 | 1 |
| CC0 | 2 | 1 |

**Kết luận đề xuất (Lực duyệt):** cả năm loại đều cho phép dùng nghiên cứu phi thương mại; CC BY và CC BY-NC cần ghi công (cột `attribution` có tác giả và URL). Nhóm lấy ảnh qua CommunityForensics-Small (CC BY-NC-SA 4.0, chỉ nghiên cứu phi thương mại), nên điều kiện chặt nhất vẫn là phi thương mại, chia sẻ cùng giấy phép, không phát hành lại ảnh, như `data/README.md` đã ghi. **Giới hạn:** việc ghép dựa vào tên file, chưa so pixel ảnh CommunityForensics với ảnh LHQ gốc.

## 2. group_id và chia validation

`scripts.mixed_manifest` áp đúng quy tắc D01 (`scripts.add_group_ids.group_ids_from_hashes`) lên SHA256 ảnh gốc và dHash ảnh chuẩn hóa của selection, cho cả 1.880 ảnh OpenFake chỉ dùng chấm và 1.720 ảnh GenImage val/test cũ (dùng `group_id` của `data/labels.csv`; ảnh trùng byte vẫn bị bắt qua dHash vì cùng bộ `genimage`).

- **14.525 ảnh thành 14.525 group**: không có cặp nào trùng SHA256 hay dHash lệch ≤ 4 bit trong cùng bộ, kể cả giữa ảnh train mới và GenImage val/test cũ. 0 group vắt split, 0 group lẫn nhãn.
- Vì vậy validation nguồn mới (chia theo ảnh ở run-v2) **đã khớp chia theo group D01**; không cần chuyển ảnh nào.
- **Ngoài D01 (không gộp group, chờ Lực quyết):** 7 prompt có ảnh ở cả train và validation, gồm 16 ảnh, đều là `community_ai` (7 ảnh ở validation), ví dụ "a person on skis on a snowy slope" sinh bằng hai model khác nhau. Cùng prompt không phải cùng ảnh, nhưng là lineage nội dung. Nếu tính là cùng group thì 7 ảnh validation này cần chuyển hoặc loại.
- Cân bằng trên toàn manifest theo quy tắc `check_data` (40–60% ảnh AI): mọi bộ và cohort đều trong khoảng (community 44,8% / 45,2%; openfake train và validation 58,8%, sát cận trên). GenImage có ADM, Wukong, SD1.5 **chỉ ở train**: `check_data` trên cả bộ sẽ báo "thiếu nguồn" ở val/test do thiết kế, không phải lỗi dữ liệu.

## 3. Kiểm trên ảnh (mẫu)

Ảnh gốc của bộ mới là 8,5 GB nằm trong 272 row group parquet (khoảng 44 GB phải đọc), nên chỉ kiểm **mẫu theo cụm**: tất cả ảnh đã chọn trong 8 row group OpenFake có nhiều ảnh LAION/Pexels nhất (51 LAION, 68 Pexels, 113 AI), 100 ảnh COCO ngẫu nhiên (seed 42) trong `HFCF_small_132` và 60 ảnh AI ngẫu nhiên trong `HFCF_small_52`. Mẫu **không đại diện ngẫu nhiên** cho cả bộ; không có ảnh FFHQ, VISION, Landscapes HQ.

| Phép kiểm (392 ảnh) | Kết quả |
|---|---|
| SHA256 ảnh gốc tải từ HF so `raw_sha256` | 392/392 khớp |
| Chuẩn hóa lại bằng `models.normalize.normalize_image`, SHA256 so `normalized_sha256` | 392/392 khớp từng byte |
| dHash ảnh chuẩn hóa so `dhash` | 392/392 khớp |
| `scripts.check_data` (labels mini, `group_id` từ manifest) | Bước 1, 2, 3, 4, 5 đạt; bước 6 lỗi `community train` 36% AI do cách lấy mẫu (100 thật / 60 AI), toàn bộ là 44,8% |

Trước đây ADV-09 chỉ tính lại dHash cho ảnh Tiny-GenImage; đây là lần đầu metadata OpenFake và CommunityForensics được tính lại từ ảnh. Lần chạy đầu `check_data` báo lỗi kích thước cả 392 ảnh vì `EXPECTED_SIZE` chỉ có `genimage` và `cifake`; nhánh này thêm `community` và `openfake` (256×256, cùng `normalize_image`) kèm test.

**Chưa làm: metadata audit trên bộ mới.** Lý do: `scripts/metadata_audit.py` cần ảnh gốc và ảnh chuẩn hóa của cả bộ và đo trên split `test` (bộ mới train/validation không có test; OpenFake chỉ dùng chấm có 1.880 ảnh), mẫu 392 ảnh không đủ 100 ảnh mỗi lớp mỗi slice. Bao giờ: khi có máy giữ đủ ảnh (máy Kiệt đã có) và Lực chốt slice cho bộ mới; probe pixel nên dùng protocol H4 (`docs/g02-h4-protocol.md`) thay vì chạy riêng.

## 4. Kiểm tay nhãn "thật" LAION/Pexels

Mẫu 119 ảnh thật (51 LAION, 68 Pexels) từ mục 3; xem từng ảnh ở bản lớn (cạnh dài tối đa 1.600 px) trước khi đọc caption, chọn "thật", "có thể AI" hoặc "không chắc". Người xem: Loan, một người, bằng mắt. Ảnh không đưa vào Git.

| Nguồn | Đã xem | Thật | Có thể AI | Không chắc | Tỉ lệ "có thể AI" (Wilson 95%) |
|---|---:|---:|---:|---:|---|
| LAION | 51/51 | 27 | 23 | 1 | 45% (32–59%) |
| Pexels | 68/68 | 42 | 25 | 1 | 37% (26–49%) |

- **"Có thể AI" gộp ảnh do AI sinh với ảnh ghép, chỉnh sửa hoặc nén nặng**; chưa tách. Caption cho thấy ít nhất 4/23 là ảnh ghép hoặc đã chỉnh (ảnh chia đôi, so sánh hai ảnh), nhiều ảnh là ảnh người nổi tiếng hoặc sự kiện chất lượng thấp. Vì vậy chỉ ghi được: **khoảng một nửa mẫu LAION và hơn một phần ba mẫu Pexels không được người xem coi là ảnh chụp gốc rõ ràng**, không ghi "45% hay 37% là ảnh AI". Ảnh Pexels là ảnh stock thường đã chỉnh màu chuyên nghiệp, nên tỉ lệ ở Pexels dễ bị đẩy lên bởi ảnh chỉnh sửa.
- Hệ quả nếu được xác nhận: nhãn "thật" của LAION và Pexels không sạch; nên báo kết quả riêng theo nguồn, và cân nhắc tách hai nguồn này khỏi ảnh thật khi train. Đề xuất, Lực quyết.
- **Chưa làm:** tách AI và ảnh ghép/chỉnh trong 48 ảnh "có thể AI"; người xem thứ hai (đề xuất Kiệt) xem độc lập 48 ảnh đó. Lý do: cần người xem độc lập. Bao giờ: khi Kiệt nhận; ghi lại khi đóng #160.
- Giới hạn: một người xem; mẫu theo cụm 8 row group; ảnh AI tốt có thể qua mắt người. COCO "trước 2019 nên là ảnh thật" vẫn là giả định chưa kiểm.

## Tái lập

```bash
python -m scripts.mixed_manifest --run-dir data/metadata/realcheck_mixed_v3/run-v2 \
    --history data/labels.csv --lhq-metadata <metadata.json> --output <manifest.csv>
python -m scripts.check_data --labels <labels mini của mẫu>
```

Bước tải mẫu (đọc row group bằng `huggingface_hub` 0.36.0 + `pyarrow` 21.0.0, so SHA256, chuẩn hóa lại) dùng script cục bộ trên máy Loan, chưa đưa vào repo (việc 8 của ADV-09, "script tải tái lập được", chưa làm); danh sách 392 ảnh mẫu theo `raw_sha256` có thể gửi khi cần.
