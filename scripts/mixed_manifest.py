"""Manifest có group_id và giấy phép cho bộ mở rộng realcheck_mixed_v3 (#160, không cần ảnh).

Đầu vào là metadata run-v2 (labels.csv + selection.jsonl), labels.csv của bộ chính (cho 1.720
ảnh GenImage val/test cũ, đã có group_id) và metadata.json chính thức của Landscapes HQ
(giấy phép từng ảnh, link ở https://github.com/universome/alis/blob/master/lhq.md).

group_id theo đúng quy tắc D01 của scripts.add_group_ids (trùng SHA256 ảnh gốc hoặc dHash
ảnh chuẩn hóa lệch <= 4 bit trong cùng bộ, bắc cầu), tính trên mọi ảnh của selection và
labels, kể cả ảnh OpenFake chỉ dùng để chấm. Ảnh GenImage cũ dùng 16 ký tự hex trong
group_id của bộ chính thay cho SHA256 (ảnh gốc không đủ trên máy); ảnh trùng byte vẫn bị
bắt qua dHash. Group vắt qua nhiều split hoặc lẫn nhãn: dừng, không ghi file.

Không đổi ảnh, nhãn hay split. Ngoài D01, script đếm prompt dùng chung giữa các split để
báo cáo (không gộp group theo prompt).

Cách chạy (từ thư mục gốc repo):
    python -m scripts.mixed_manifest --run-dir data/metadata/realcheck_mixed_v3/run-v2 \
        --history data/labels.csv --lhq-metadata <metadata.json> --output <manifest.csv>
"""

import argparse
import csv
import hashlib
import io
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scripts.add_group_ids import group_ids_from_hashes

COLUMNS = [
    "filepath", "label", "source", "stratum", "split", "cohort", "raw_sha256",
    "normalized_sha256", "dhash", "group_id", "dataset_license", "image_license",
    "attribution", "upstream",
]  # fmt: skip
DATASET_LICENSE = {
    "TheKernel01/Tiny-GenImage": "CC BY-NC-SA 4.0 (Tiny-GenImage)",
    "OwensLab/CommunityForensics-Small": "CC BY-NC-SA 4.0 (CommunityForensics-Small)",
    "ComplexDataLab/OpenFake": "CC BY-NC 4.0 (OpenFake)",
}
# Giấy phép từng ảnh khi nguồn gốc ghi rõ; còn lại để trống là chưa xác nhận (data/README.md)
IMAGE_LICENSE = {"community/vision": "CC BY-SA 4.0 (VISION)"}
LHQ = "community/landscapeshq"
HISTORY_LICENSE = {
    "genimage_sd14": "chưa xác nhận (nebula/GenImage-arrow)",
}


def _history_rows(labels: list[dict], selected: set[str], history: Path) -> list[dict]:
    """1.720 ảnh GenImage val/test cũ không có trong selection: lấy group_id của bộ chính."""
    by_raw = {r["raw_path"]: r for r in csv.DictReader(history.open(encoding="utf-8"))}
    out = []
    for r in labels:
        if r["filepath"] in selected:
            continue
        key = r["raw_path"].split("realcheck/", 1)[-1]
        old = by_raw.get(key)
        if old is None or (old["split"], old["label"]) != (r["split"], r["label"]):
            raise ValueError(f"{r['filepath']}: không khớp bộ chính qua raw_path {key}")
        out.append(
            {
                "filepath": r["filepath"],
                "label": r["label"],
                "source": r["source"],
                "stratum": "genimage/" + r["source"].split("_", 1)[1],
                "split": r["split"],
                "cohort": "core_genimage",
                "raw_sha256": "",
                "normalized_sha256": "",
                "dhash": r["dhash"],
                "group_key": old["group_id"].removeprefix("g-"),
                "dataset_license": HISTORY_LICENSE.get(
                    r["source"], DATASET_LICENSE["TheKernel01/Tiny-GenImage"]
                ),
                "image_license": "",
                "attribution": "",
                "upstream": f"bộ chính data/labels.csv ({key})",
            }
        )
    return out


def build(run_dir: Path, history: Path, lhq_metadata: Path) -> tuple[list[dict], dict]:
    """Các dòng manifest (thứ tự: labels.csv rồi ảnh chỉ có trong selection) và thống kê."""
    selection = [
        json.loads(line)
        for line in (run_dir / "selection.jsonl").open(encoding="utf-8")
    ]
    labels = list(csv.DictReader((run_dir / "labels.csv").open(encoding="utf-8")))
    lhq = {
        x["filename"]: x
        for x in json.loads(
            lhq_metadata.read_text(encoding="utf-8").replace("NaN", "null")
        )
    }
    by_path = {s["filepath"]: s for s in selection}
    split_of = {r["filepath"]: r["split"] for r in labels}

    rows = []
    for s in sorted(by_path.values(), key=lambda s: s["filepath"] not in split_of):
        if s["stratum"] == LHQ and s["image_name"] not in lhq:
            raise ValueError(
                f"{s['image_name']}: không có trong metadata Landscapes HQ"
            )
        meta = lhq.get(s["image_name"], {}) if s["stratum"] == LHQ else {}
        rows.append(
            {
                "filepath": s["filepath"],
                "label": str(s["label"]),
                "source": s["source"],
                "stratum": s["stratum"],
                "split": split_of.get(s["filepath"], s["split"]),
                "cohort": s["cohort"],
                "raw_sha256": s["raw_sha256"],
                "normalized_sha256": s["normalized_sha256"],
                "dhash": str(s["dhash"]),
                "group_key": s["raw_sha256"],
                "dataset_license": DATASET_LICENSE[s["repo"]],
                "image_license": meta.get("license")
                or IMAGE_LICENSE.get(s["stratum"], ""),
                "attribution": "; ".join(
                    filter(None, (meta.get("author"), meta.get("url")))
                ),
                "upstream": f"{s['repo']}@{s['revision']}/{s['parquet']}"
                f"#rg{s['row_group']}:{s['offset']}",
            }
        )
    rows += _history_rows(labels, set(by_path), history)

    ids = group_ids_from_hashes(
        rows, [r.pop("group_key") for r in rows], [int(r["dhash"]) for r in rows]
    )
    for r, g in zip(rows, ids):
        r["group_id"] = g

    prompts = defaultdict(set)
    for s in selection:
        if (s.get("prompt") or "").strip():
            prompts[s["prompt"].strip()].add(split_of.get(s["filepath"], s["split"]))
    stats = {
        "rows": len(rows),
        "groups": len(set(ids)),
        "lhq_licenses": dict(
            sorted(
                Counter(r["image_license"] for r in rows if r["stratum"] == LHQ).items()
            )
        ),
        "prompts_shared_across_splits": sum(len(v) > 1 for v in prompts.values()),
        "lhq_metadata_sha256": hashlib.sha256(lhq_metadata.read_bytes()).hexdigest(),
    }
    return rows, stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--lhq-metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")
    try:
        rows, stats = build(args.run_dir, args.history, args.lhq_metadata)
    except (OSError, ValueError, KeyError) as exc:
        print(f"Không ghi file: {exc}", file=sys.stderr)
        sys.exit(1)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.open("xb").write(data)
    stats["manifest_sha256"] = hashlib.sha256(data).hexdigest()
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
