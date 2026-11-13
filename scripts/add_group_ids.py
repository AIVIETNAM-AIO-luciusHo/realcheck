"""Thêm cột group_id vào labels.csv (#99, AC-18).

Quy tắc nhóm (D01): hai ảnh cùng group nếu ảnh gốc trùng byte (SHA256) hoặc ảnh đã chuẩn
hóa gần trùng (dHash lệch <= check_data.NEAR_DUP_BITS bit, chỉ so trong cùng bộ dữ liệu như
check_data); nhóm lấy bắc cầu. group_id = "g-" + 16 ký tự hex đầu của SHA256 ảnh gốc nhỏ
nhất trong group, nên không phụ thuộc tên file hay thứ tự dòng.

Chỉ nối thêm cột vào cuối mỗi dòng: không đổi ảnh, nhãn, split, thứ tự hay kiểu xuống dòng;
bỏ cột group_id thì file khớp từng byte với bản cũ (script tự kiểm). Group vắt qua nhiều
split hoặc lẫn nhãn là lỗi: script dừng, không ghi file, không tự sửa split.

labels.csv có group_id dùng thẳng làm `history` (cột group_id, split) của protocol ADV-08.

Cách chạy (từ thư mục gốc repo, đường dẫn ảnh trong labels tính từ --root):
    python -m scripts.add_group_ids --labels data/labels.csv --output <labels mới> [--root .]
"""

import argparse
import csv
import hashlib
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from scripts.check_data import NEAR_DUP_BITS, dhash

COLUMN = "group_id"


def _lines(text: str) -> tuple[str, list[str], list[str]]:
    """(header, thân từng dòng, ký tự xuống dòng của từng dòng), giữ nguyên byte."""
    lines = text.splitlines(keepends=True)
    bodies = [line.rstrip("\r\n") for line in lines]
    endings = [line[len(body) :] for line, body in zip(lines, bodies)]
    return bodies[0], bodies[1:], endings


def _dataset(source: str) -> str:
    return source.split("_")[0]


def group_ids(rows: list[dict[str, str]], root: Path) -> list[str]:
    """group_id cho từng dòng theo quy tắc ở docstring; ValueError nếu group không hợp lệ."""
    raw_sha = [
        hashlib.sha256((root / row["raw_path"]).read_bytes()).hexdigest()
        for row in rows
    ]
    hashes = []
    for row in rows:
        with Image.open(root / row["filepath"]) as image:
            hashes.append(dhash(image))

    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        parent[find(b)] = find(a)

    first = {}
    for i, digest in enumerate(raw_sha):
        union(first.setdefault(digest, i), i)
    for dataset in sorted({_dataset(row["source"]) for row in rows}):
        index = np.array(
            [i for i, row in enumerate(rows) if _dataset(row["source"]) == dataset]
        )
        values = np.array([hashes[i] for i in index], dtype=np.uint64)
        for a in range(len(index) - 1):
            close = np.bitwise_count(values[a + 1 :] ^ values[a]) <= NEAR_DUP_BITS
            for b in np.nonzero(close)[0]:
                union(int(index[a]), int(index[a + 1 + b]))

    members: dict[int, list[int]] = {}
    for i in range(len(rows)):
        members.setdefault(find(i), []).append(i)
    problems, names = [], {}
    for group in members.values():
        name = "g-" + min(raw_sha[i] for i in group)[:16]
        for key in ("split", "label"):
            if len({rows[i][key] for i in group}) > 1:
                paths = ", ".join(rows[i]["raw_path"] for i in group)
                problems.append(f"{name}: khác {key} trong cùng group ({paths})")
        names.update(dict.fromkeys(group, name))
    if len(set(names.values())) != len(members):
        problems.append("Hai group trùng group_id (16 ký tự hex); cần tăng độ dài")
    if problems:
        raise ValueError("\n".join(problems))
    return [names[i] for i in range(len(rows))]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error(f"Output already exists: {args.output}")

    original = args.labels.read_bytes()
    text = original.decode("utf-8")
    header, bodies, endings = _lines(text)
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if COLUMN in (reader.fieldnames or []):
        parser.error(f"{args.labels} already has {COLUMN}")
    if not rows or len(rows) != len(bodies):
        parser.error("labels.csv cần đúng một dòng CSV mỗi dòng văn bản, có dữ liệu")
    try:
        ids = group_ids(rows, args.root)
    except (OSError, ValueError) as exc:
        print(f"Không ghi file: {exc}", file=sys.stderr)
        sys.exit(1)

    out = header + "," + COLUMN + endings[0]
    out += "".join(f"{b},{g}{e}" for b, g, e in zip(bodies, ids, endings[1:]))
    stripped = header + endings[0] + "".join(b + e for b, e in zip(bodies, endings[1:]))
    if stripped.encode("utf-8") != original:
        print("Không ghi file: bỏ group_id không khớp bản cũ", file=sys.stderr)
        sys.exit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="") as stream:
        stream.write(out)
    multi = len(ids) - len(set(ids))
    print(
        f"Đã ghi {args.output}: {len(ids)} dòng, {len(set(ids))} group "
        f"({multi} ảnh gộp vào group có sẵn); sha256 "
        f"{hashlib.sha256(out.encode('utf-8')).hexdigest()}"
    )
    print(
        f"Không đổi cột cũ: sha256 khi bỏ {COLUMN} = {hashlib.sha256(original).hexdigest()}"
    )


if __name__ == "__main__":
    main()
