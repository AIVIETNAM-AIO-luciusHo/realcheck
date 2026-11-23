# Manifest bộ realcheck_mixed_v3 có group_id và giấy phép (#160)

Một dòng mỗi ảnh cho **14.525 ảnh**: 12.645 dòng `labels.csv` của [run-v2](../run-v2/README.md) (10.925 ảnh mới train/validation và 1.720 ảnh GenImage val/test cũ) cùng 1.880 ảnh OpenFake chỉ dùng chấm (`core_test`, `reddit_test`). Chỉ metadata, không ảnh. Không đổi ảnh, nhãn hay split của run-v2; run-v2 giữ nguyên.

Tạo bằng (từ gốc repo):

```bash
python -m scripts.mixed_manifest --run-dir data/metadata/realcheck_mixed_v3/run-v2 \
    --history data/labels.csv --lhq-metadata <metadata.json của Landscapes HQ> \
    --output data/metadata/realcheck_mixed_v3/adv12d/manifest.csv
```

`metadata.json` của Landscapes HQ lấy từ link chính thức trong [lhq.md](https://github.com/universome/alis/blob/master/lhq.md) (Yandex Disk), SHA256 `a7a0a3a9931189cd3b7bf01db4fdad8ed20d5deeaee1dc7623eb435ee51b295b`, 90.000 dòng; không đưa vào Git. Chạy lại cho cùng SHA256 manifest (`SHA256SUMS`).

## Cột

| Cột | Nội dung |
|---|---|
| `filepath`, `label`, `source`, `split` | Như run-v2 (`split` của ảnh chỉ dùng chấm là `test`) |
| `stratum`, `cohort` | Nguồn con (`community/landscapeshq`, `openfake/laion`, …) và nhóm của selection; ảnh GenImage cũ ghi `genimage/<nguồn>`, cohort `core_genimage` |
| `raw_sha256`, `normalized_sha256`, `dhash` | Từ selection. Ảnh GenImage cũ để trống hai hash (ảnh gốc không đủ trên máy; định danh qua `group_id` của bộ chính) |
| `group_id` | Quy tắc D01 của `scripts.add_group_ids`: trùng SHA256 ảnh gốc hoặc dHash ảnh chuẩn hóa lệch ≤ 4 bit trong cùng bộ, bắc cầu; `g-` + 16 ký tự hex SHA256 ảnh gốc nhỏ nhất. Ảnh GenImage cũ giữ `group_id` của `data/labels.csv` |
| `dataset_license` | Giấy phép của bộ phát hành (Tiny-GenImage CC BY-NC-SA 4.0, CommunityForensics-Small CC BY-NC-SA 4.0, OpenFake CC BY-NC 4.0); SD1.4 cũ (`nebula/GenImage-arrow`) chưa xác nhận |
| `image_license` | Giấy phép từng ảnh khi có nguồn: Landscapes HQ theo `metadata.json`, VISION CC BY-SA 4.0. **Trống là chưa xác nhận từng ảnh** (COCO, FFHQ theo Flickr; LAION, Pexels; ảnh AI theo `dataset_license`) |
| `attribution` | Tác giả và URL gốc (Landscapes HQ), để ghi công CC BY |
| `upstream` | `repo@revision/parquet#rg<row group>:<offset>`; ảnh GenImage cũ trỏ về dòng của bộ chính |

## Kết quả và giới hạn

Báo cáo kiểm: [docs/data-review-adv12d.md](../../../../docs/data-review-adv12d.md). Tóm tắt: 14.525 ảnh thành 14.525 group (không có ảnh trùng byte hay gần trùng nào), không group vắt split hay lẫn nhãn. `group_id` không gộp theo prompt: 7 prompt ảnh AI có ảnh ở cả train và validation (báo cáo, mục 2).
