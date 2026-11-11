"""ADV-09: Tiny-GenImage identity overlap between a new dataset and protected splits."""

import csv

import pytest

from scripts import check_tiny_overlap as cto


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.mark.parametrize(
    ("name", "identity"),
    [
        ("data/raw/genimage/glide/glide_train-00003_0042.png", ("train-00003", 42)),
        ("real_validation-00001_1998.jpg", ("validation-00001", 1998)),
        ("sd14_data-00004_0001.png", None),  # GenImage-arrow, not Tiny-GenImage
        ("cifake_real_00001.jpg", None),
    ],
)
def test_identity_comes_from_the_shard_and_row(name, identity):
    assert cto.tiny_identity(name) == identity


def test_overlap_counts_only_protected_splits(tmp_path, capsys):
    protected = write_csv(
        tmp_path / "a.csv",
        [
            {"filepath": "p/real_train-00000_0001.jpg", "split": "val"},
            {"filepath": "p/glide_train-00002_0007.png", "split": "test"},
            {"filepath": "p/real_train-00000_0002.jpg", "split": "train"},
        ],
    )
    candidates = write_csv(
        tmp_path / "b.csv",
        [
            {"filepath": "x/real_train-00000_0001.png"},  # same image as a val row
            {"filepath": "x/adm_train-00002_0007.jpg"},  # same shard row as a test row
            {"filepath": "x/real_train-00000_0002.jpg"},  # only in train: allowed
            {"filepath": "x/coco_123.jpg"},
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        cto.main(["--protected", str(protected), "--candidates", str(candidates)])
    assert exit_info.value.code == 1
    assert "{'val': 1, 'test': 1}" in capsys.readouterr().out


def test_no_overlap_exits_zero_and_bad_input_exits_two(tmp_path):
    protected = write_csv(
        tmp_path / "a.csv", [{"filepath": "real_train-00000_0001.jpg", "split": "val"}]
    )
    candidates = write_csv(
        tmp_path / "b.csv", [{"filepath": "real_train-00009_0001.jpg"}]
    )
    for argv, code in (
        (["--protected", str(protected), "--candidates", str(candidates)], 0),
        (
            ["--protected", str(protected), "--candidates", str(tmp_path / "none.csv")],
            2,
        ),
        (
            [
                "--protected",
                str(protected),
                "--candidates",
                str(candidates),
                "--candidate-column",
                "x",
            ],
            2,
        ),
    ):
        with pytest.raises(SystemExit) as exit_info:
            cto.main(argv)
        assert exit_info.value.code == code


def test_verify_sha_reports_identical_and_different_bytes(tmp_path, capsys):
    (tmp_path / "real_train-00000_0001.jpg").write_bytes(b"same")
    (tmp_path / "c_real_train-00000_0001.jpg").write_bytes(b"same")
    (tmp_path / "real_train-00000_0002.jpg").write_bytes(b"one")
    (tmp_path / "c_real_train-00000_0002.jpg").write_bytes(b"two")
    protected = write_csv(
        tmp_path / "a.csv",
        [
            {"filepath": str(tmp_path / "real_train-00000_0001.jpg"), "split": "val"},
            {"filepath": str(tmp_path / "real_train-00000_0002.jpg"), "split": "test"},
        ],
    )
    candidates = write_csv(
        tmp_path / "b.csv",
        [
            {"filepath": str(tmp_path / "c_real_train-00000_0001.jpg")},
            {"filepath": str(tmp_path / "c_real_train-00000_0002.jpg")},
        ],
    )
    with pytest.raises(SystemExit):
        cto.main(
            [
                "--protected",
                str(protected),
                "--candidates",
                str(candidates),
                "--verify-sha",
            ]
        )
    assert "{'sha256 khớp': 1, 'sha256 khác': 1}" in capsys.readouterr().out
