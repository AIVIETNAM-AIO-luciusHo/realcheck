"""scripts.add_group_ids (#99): quy tắc nhóm, giữ nguyên cột cũ, từ chối group vắt split."""

import csv
import hashlib

import numpy as np
import pytest
from PIL import Image

from scripts import add_group_ids

HEADER = "filepath,label,source,split,raw_path,norm_version"


def noise(path, seed, size=(64, 64)):
    path.parent.mkdir(parents=True, exist_ok=True)
    pixels = np.random.default_rng(seed).integers(0, 256, (*size, 3), dtype=np.uint8)
    Image.fromarray(pixels).save(path)


def write_labels(root, rows, newline="\n"):
    """rows: (tên, label, source, split, seed ảnh gốc, seed ảnh processed)."""
    lines = [HEADER]
    for name, label, source, split, raw_seed, processed_seed in rows:
        dataset, kind = source.split("_")
        raw = f"raw/{dataset}/{kind}/{name}.png"
        processed = f"processed/{dataset}/{kind}/{name}.jpg"
        noise(root / raw, raw_seed)
        noise(root / processed, processed_seed)
        lines.append(f"{processed},{label},{source},{split},{raw},1")
    path = root / "labels.csv"
    path.write_bytes((newline.join(lines) + newline).encode("utf-8"))
    return path


def run(root):
    labels = root / "labels.csv"
    output = root / "out.csv"
    add_group_ids.main(
        ["--labels", str(labels), "--output", str(output), "--root", str(root)]
    )
    return list(csv.DictReader(output.open(encoding="utf-8"))), output


def test_exact_and_near_duplicates_share_a_group_and_old_columns_are_unchanged(
    tmp_path,
):
    write_labels(
        tmp_path,
        [
            ("a", 0, "genimage_real", "train", 1, 11),
            ("b", 0, "genimage_real", "train", 1, 12),  # cùng byte ảnh gốc với a
            ("c", 1, "genimage_sd14", "val", 3, 13),
            ("d", 1, "genimage_sd14", "val", 4, 13),  # processed gần trùng c
            ("e", 0, "genimage_real", "test", 5, 15),
        ],
        newline="\r\n",
    )
    original = (tmp_path / "labels.csv").read_bytes()
    rows, output = run(tmp_path)
    ids = [row["group_id"] for row in rows]
    assert ids[0] == ids[1] and ids[2] == ids[3]
    assert len(set(ids)) == 3
    raw_a = hashlib.sha256((tmp_path / rows[0]["raw_path"]).read_bytes()).hexdigest()
    assert ids[0] == "g-" + raw_a[:16]
    text = output.read_bytes().decode("utf-8")
    stripped = text.replace(",group_id", "", 1)
    for gid in set(ids):
        stripped = stripped.replace(f",{gid}\r\n", "\r\n")
    assert stripped.encode("utf-8") == original, "bỏ group_id thì khớp từng byte"


def test_group_id_does_not_depend_on_row_order(tmp_path):
    spec = [
        ("a", 0, "genimage_real", "train", 1, 11),
        ("b", 0, "genimage_real", "train", 1, 12),
        ("c", 1, "genimage_sd14", "val", 3, 13),
    ]
    write_labels(tmp_path / "x", spec)
    write_labels(tmp_path / "y", spec[::-1])
    forward, _ = run(tmp_path / "x")
    backward, _ = run(tmp_path / "y")
    by_name = {row["raw_path"]: row["group_id"] for row in forward}
    assert {row["raw_path"]: row["group_id"] for row in backward} == by_name


@pytest.mark.parametrize(
    "second",
    [
        ("b", 0, "genimage_real", "test", 1, 12),  # trùng byte nhưng khác split
        ("b", 1, "genimage_sd14", "train", 1, 12),  # trùng byte nhưng khác nhãn
    ],
)
def test_group_across_split_or_label_is_refused_without_writing(
    tmp_path, capsys, second
):
    write_labels(tmp_path, [("a", 0, "genimage_real", "train", 1, 11), second])
    with pytest.raises(SystemExit) as exit_info:
        run(tmp_path)
    assert exit_info.value.code == 1
    assert "Không ghi file" in capsys.readouterr().err
    assert not (tmp_path / "out.csv").exists()


def test_near_duplicates_are_only_compared_within_one_dataset(tmp_path):
    write_labels(
        tmp_path,
        [
            ("a", 0, "genimage_real", "train", 1, 11),
            ("b", 0, "cifake_real", "test", 2, 11),  # cùng processed, khác bộ dữ liệu
        ],
    )
    rows, _ = run(tmp_path)
    assert rows[0]["group_id"] != rows[1]["group_id"]


def test_refuses_existing_output_or_existing_group_id(tmp_path):
    write_labels(tmp_path, [("a", 0, "genimage_real", "train", 1, 11)])
    (tmp_path / "out.csv").write_text("keep", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(tmp_path)
    assert (tmp_path / "out.csv").read_text(encoding="utf-8") == "keep"
    (tmp_path / "out.csv").unlink()
    _, output = run(tmp_path)
    with pytest.raises(SystemExit):
        add_group_ids.main(
            ["--labels", str(output), "--output", str(tmp_path / "again.csv"),
             "--root", str(tmp_path)]
        )  # fmt: skip
    assert not (tmp_path / "again.csv").exists()
