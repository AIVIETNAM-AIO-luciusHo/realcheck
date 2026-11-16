import pytest

from scripts import check_pr_hygiene as h

TEMPLATE_BODY = """## Task liên quan

- **Jira:** KAN-
- **Task spec:** T___

## Kết quả kiểm chứng

<!-- Dán lệnh đã chạy và kết quả thật. -->

```text
ruff check .            →
pytest -v               →  ___ passed, ___ failed, ___ skipped
```

**Cách reviewer chạy lại:**

## Giới hạn, rủi ro và việc chưa làm

<!-- Nói thẳng điều chưa kiểm được. -->

## Phần theo loại thay đổi
"""

GOOD_BODY = """## Task liên quan

- **Jira:** KAN-91

## Kết quả kiểm chứng

```text
ruff check .            →  All checks passed
pytest -v               →  1175 passed, 0 failed, 0 skipped
```

**Cách reviewer chạy lại:** pytest -q

## Giới hạn, rủi ro và việc chưa làm

Chưa chạy trên Python 3.12.14; số trên là tự đo, chưa ai tính lại.

## Phần theo loại thay đổi
"""
CLEAN_COMMITS = "feat: add metrics\n\nDetails.\n"


def test_vuot():
    assert h.check("feat: add metrics (#162)", GOOD_BODY, CLEAN_COMMITS) == []
    assert h.check("docs: x", GOOD_BODY, CLEAN_COMMITS) == []  # KAN-91 trong mục Task


def test_truot_co_authored_by_trong_commit():
    bad = CLEAN_COMMITS + "\nCo-Authored-By: Someone <a@b.c>\n"
    p = h.check("feat: x (#1)", GOOD_BODY, bad)
    assert len(p) == 1 and p[0].startswith("commit")


@pytest.mark.parametrize(
    "line",
    [
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
        "co-authored-by: x",
    ],
)
def test_truot_dong_cam_trong_than_pr(line):
    p = h.check("feat: x (#1)", GOOD_BODY + "\n" + line + "\n", CLEAN_COMMITS)
    assert any(x.startswith("thân PR: có dòng bị cấm") for x in p)


def test_truot_con_nguyen_mau():
    p = h.check("feat: x (#1)", TEMPLATE_BODY, CLEAN_COMMITS)
    assert any(RESULT in x and "nguyên mẫu" in x for x in p for RESULT in [h.RESULT])
    assert any(h.LIMITS in x for x in p)


def test_truot_thieu_muc():
    body = GOOD_BODY.replace("## Giới hạn, rủi ro và việc chưa làm", "## Khác")
    assert any("thiếu mục" in x for x in h.check("feat: x (#1)", body, CLEAN_COMMITS))


def test_truot_khong_co_ma_task():
    body = GOOD_BODY.replace("KAN-91", "KAN-")
    assert any("KAN-<số>" in x for x in h.check("feat: x", body, CLEAN_COMMITS))
    assert h.check("feat: x #12", body, CLEAN_COMMITS) == []


def test_ma_task_trong_chu_thich_khong_tinh():
    body = GOOD_BODY.replace("KAN-91", "<!-- KAN-91 -->")
    assert any("KAN-<số>" in x for x in h.check("feat: x", body, CLEAN_COMMITS))


def test_main_ma_thoat(tmp_path, capsys):
    b, c = tmp_path / "b.md", tmp_path / "c.txt"
    b.write_text(GOOD_BODY, encoding="utf-8")
    c.write_text(CLEAN_COMMITS, encoding="utf-8")
    args = ["--title", "feat: x (#1)", "--body-file", str(b), "--commits-file", str(c)]
    assert h.main(args) == 0
    c.write_text("Co-Authored-By: x\n", encoding="utf-8")
    assert h.main(args) == 1
    assert (
        h.main(
            [
                "--title",
                "t",
                "--body-file",
                str(tmp_path / "none"),
                "--commits-file",
                str(c),
            ]
        )
        == 2
    )


def test_tieu_de_muc_co_duoi_ghi_chu():
    body = GOOD_BODY.replace(h.RESULT, h.RESULT + " (Coder tự đo)")
    assert h.check("feat: x (#1)", body, CLEAN_COMMITS) == []
