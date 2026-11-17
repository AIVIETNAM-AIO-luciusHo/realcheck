"""scripts.mixed_manifest (#160): group_id theo D01 từ metadata, giấy phép Landscapes HQ."""

import csv
import json

import pytest

from scripts import mixed_manifest

LABELS = (
    "filepath,label,source,split,raw_path,norm_version,dhash,file_size,raw_file_size"
)


def sel(name, label, source, stratum, split, cohort, sha, dhash, **extra):
    return {
        "filepath": f"new/{name}.jpg", "label": label, "source": source,
        "stratum": stratum, "split": split, "cohort": cohort, "raw_sha256": sha * 64,
        "normalized_sha256": "n" * 64, "dhash": dhash,
        "repo": "OwensLab/CommunityForensics-Small", "revision": "r",
        "parquet": "data/x.parquet", "row_group": "0", "offset": "1", **extra,
    }  # fmt: skip


def write(tmp_path, selection, old_dhash=2**63):
    run = tmp_path / "run"
    run.mkdir()
    (run / "selection.jsonl").write_text(
        "".join(json.dumps(s) + "\n" for s in selection), encoding="utf-8"
    )
    lines = [LABELS]
    lines += [
        f"{s['filepath']},{s['label']},{s['source']},{s['split']},raw,1,{s['dhash']},1,1"
        for s in selection
        if s["cohort"] in ("expanded_train", "new_validation")
    ]
    lines.append(
        f"old/a.jpg,0,genimage_real,val,realcheck/data/raw/a.png,1,{old_dhash},1,1"
    )
    (run / "labels.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    history = tmp_path / "history.csv"
    history.write_text(
        "filepath,label,source,split,raw_path,norm_version,group_id\n"
        "data/processed/a.jpg,0,genimage_real,val,data/raw/a.png,1,g-00000000000000aa\n",
        encoding="utf-8",
    )
    lhq = tmp_path / "lhq.json"
    lhq.write_text(
        json.dumps(
            [{"filename": "0000001.png", "author": "A", "url": "https://u/1",
              "license": "Unsplash License [https://unsplash.com/license]"}]
        ).replace('"A"', '"A", "description": NaN'),
        encoding="utf-8",
    )  # fmt: skip
    return run, history, lhq


def run_main(tmp_path, args):
    out = tmp_path / "manifest.csv"
    mixed_manifest.main([*map(str, args), "--output", str(out)])
    return list(csv.DictReader(out.open(encoding="utf-8")))


def cli(run, history, lhq):
    return ["--run-dir", run, "--history", history, "--lhq-metadata", lhq]


def test_manifest_has_groups_licenses_and_history_group_ids(tmp_path, capsys):
    run, history, lhq = write(
        tmp_path,
        [
            sel("t", "0", "community_real", "community/landscapeshq", "train",
                "expanded_train", "a", 0, image_name="0000001.png"),
            sel("v", "0", "community_real", "community/vision", "val",
                "new_validation", "b", 2**40 - 1),
            sel("e", "1", "community_ai", "community/ai", "test", "core_test", "c",
                2**62 - 1),
        ],
    )  # fmt: skip
    rows = run_main(tmp_path, cli(run, history, lhq))
    by = {r["filepath"]: r for r in rows}
    assert list(rows[0]) == mixed_manifest.COLUMNS
    assert len(rows) == 4 and len({r["group_id"] for r in rows}) == 4
    assert by["new/t.jpg"]["group_id"] == "g-" + "a" * 16
    assert by["new/t.jpg"]["image_license"].startswith("Unsplash License")
    assert by["new/t.jpg"]["attribution"] == "A; https://u/1"
    assert by["new/v.jpg"]["image_license"] == "CC BY-SA 4.0 (VISION)"
    assert by["new/e.jpg"]["split"] == "test" and by["new/e.jpg"]["image_license"] == ""
    assert by["old/a.jpg"]["group_id"] == "g-00000000000000aa"
    assert (
        by["old/a.jpg"]["raw_sha256"] == ""
        and "realcheck" not in by["old/a.jpg"]["upstream"]
    )
    stats = json.loads(capsys.readouterr().out)
    assert stats["groups"] == 4 and stats["lhq_licenses"] == {
        "Unsplash License [https://unsplash.com/license]": 1
    }


def test_near_duplicate_across_train_and_validation_is_refused(tmp_path):
    run, history, lhq = write(
        tmp_path,
        [
            sel("t", "0", "community_real", "community/coco", "train", "expanded_train",
                "a", 0),
            sel("v", "0", "community_real", "community/coco", "val", "new_validation",
                "b", 0b1111),
        ],
    )  # fmt: skip
    with pytest.raises(SystemExit) as exc:
        run_main(tmp_path, cli(run, history, lhq))
    assert exc.value.code == 1 and not (tmp_path / "manifest.csv").exists()


def test_old_genimage_row_is_compared_with_new_rows_by_dhash(tmp_path):
    run, history, lhq = write(
        tmp_path,
        [
            sel("t", "0", "genimage_real", "tiny/real", "train", "expanded_train", "a",
                5, repo="TheKernel01/Tiny-GenImage"),
        ],
        old_dhash=5,
    )  # fmt: skip
    with pytest.raises(SystemExit):
        run_main(tmp_path, cli(run, history, lhq))


def test_unknown_landscapes_hq_image_is_refused(tmp_path):
    run, history, lhq = write(
        tmp_path,
        [
            sel("t", "0", "community_real", "community/landscapeshq", "train",
                "expanded_train", "a", 0, image_name="0999999.png"),
        ],
    )  # fmt: skip
    with pytest.raises(SystemExit):
        run_main(tmp_path, cli(run, history, lhq))


def test_shared_prompt_across_splits_is_counted_not_grouped(tmp_path, capsys):
    run, history, lhq = write(
        tmp_path,
        [
            sel("t", "1", "community_ai", "community/ai", "train", "expanded_train",
                "a", 0, prompt="a dog"),
            sel("v", "1", "community_ai", "community/ai", "val", "new_validation",
                "b", 2**63 - 1, prompt="a dog"),
        ],
    )  # fmt: skip
    rows = run_main(tmp_path, cli(run, history, lhq))
    assert len({r["group_id"] for r in rows}) == 3
    assert json.loads(capsys.readouterr().out)["prompts_shared_across_splits"] == 1
