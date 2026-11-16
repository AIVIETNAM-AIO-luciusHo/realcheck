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
    assert any(h.LABELS[h.RESULT] in x and "nguyên mẫu" in x for x in p)
    assert any(h.LABELS[h.LIMITS] in x for x in p)


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
    body = GOOD_BODY.replace(h.LABELS[h.RESULT], h.LABELS[h.RESULT] + " (Coder tự đo)")
    assert h.check("feat: x (#1)", body, CLEAN_COMMITS) == []


def test_cau_mo_ta_quy_tac_khong_bi_coi_la_vi_pham():
    mo_ta = (
        "- cấm `Co-Authored-By:` và 'Generated with [Claude Code]' trong commit và PR\n"
        'Quy tắc "Co-Authored-By: ..." được kiểm bằng regex.\n'
    )
    assert h.check("feat: x (#1)", GOOD_BODY + "\n" + mo_ta, CLEAN_COMMITS) == []


@pytest.mark.parametrize(
    "line",
    [
        "Co-Authored-By: A <a@b.c>",
        "  - Co-authored-by: A",
        "> 🤖 Generated with [Claude Code](u)",
    ],
)
def test_dong_that_dau_dong_van_bi_bat(line):
    assert h.check("feat: x (#1)", GOOD_BODY + "\n" + line + "\n", CLEAN_COMMITS)
    assert h.check("feat: x (#1)", GOOD_BODY, CLEAN_COMMITS + line + "\n")


def test_ci_ok_phu_thuoc_pr_hygiene_va_chi_chay_tren_pull_request():
    from pathlib import Path

    import yaml

    wf = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    assert wf["jobs"]["ci-ok"]["needs"] == ["lint", "test", "pr-hygiene"]
    assert wf["jobs"]["pr-hygiene"]["if"] == "github.event_name == 'pull_request'"
    assert {"edited", "ready_for_review"} <= set(wf[True]["pull_request"]["types"])
    assert not Path(".github/workflows/pr-hygiene.yml").exists()
    assert "pull_request_target" not in str(wf)


# --- nới khớp tiêu đề: thân hợp lệ không bị trượt oan --------------------------------------------
RESULT_H = "Kết quả kiểm chứng"
LIMITS_H = "Giới hạn, rủi ro và việc chưa làm"


def _with(result_heading=RESULT_H, limits_heading=LIMITS_H, prefix="## "):
    return (
        "## Task liên quan\n\n- **Jira:** KAN-91\n\n"
        f"{prefix}{result_heading}\n\nChạy ruff và pytest: 1175 passed, 0 skipped, tự đo.\n\n"
        f"{prefix}{limits_heading}\n\nChưa kiểm trên Python 3.12.14; số trên chưa ai tính lại.\n"
    )


@pytest.mark.parametrize(
    ("result_heading", "limits_heading", "prefix"),
    [
        (
            "kết quả kiểm chứng",
            "giới hạn, rủi ro và việc chưa làm",
            "## ",
        ),  # hoa thường
        ("Ket qua kiem chung", "Gioi han, rui ro va viec chua lam", "## "),  # không dấu
        ("KẾT QUẢ KIỂM CHỨNG", "GIỚI HẠN", "## "),
        (
            "Kết quả kiểm chứng (Coder tự đo)",
            "Giới hạn và việc còn chờ",
            "## ",
        ),  # đuôi ngoặc, #127
        (
            "Kết quả kiểm chứng:",
            "Giới hạn và phần còn lại",
            "## ",
        ),  # dấu hai chấm, #156
        ("3. Kết quả kiểm chứng", "4) Giới hạn, rủi ro", "## "),  # đánh số
        ("**Kết quả kiểm chứng**", "**Giới hạn**", "### "),  # đậm, cấp 3
        ("Kết quả kiểm chứng", "Giới hạn", "#### "),
    ],
)
def test_bien_the_tieu_de_hop_le_van_vuot(result_heading, limits_heading, prefix):
    assert (
        h.check("docs: x", _with(result_heading, limits_heading, prefix), CLEAN_COMMITS)
        == []
    )


def test_muc_con_khong_cat_ngan_noi_dung_muc_cha():
    body = (
        "## Task liên quan\n\nKAN-5\n\n## Kết quả kiểm chứng\n\n### Kiểm ZIP thật\n\n"
        "Đã giải nén và kiểm hash từng file: khớp.\n\n## Giới hạn\n\nChưa chạy trên máy khác.\n"
    )
    assert h.check("feat: x", body, CLEAN_COMMITS) == []


def test_na_kem_ly_do_duoc_chap_nhan_con_na_tron_thi_khong():
    ok = _with().replace(
        "Chưa kiểm trên Python 3.12.14; số trên chưa ai tính lại.",
        "N/A: PR chỉ sửa tài liệu, không có rủi ro mới.",
    )
    assert h.check("docs: x", ok, CLEAN_COMMITS) == []
    bad = _with().replace(
        "Chưa kiểm trên Python 3.12.14; số trên chưa ai tính lại.", "N/A"
    )
    assert any("trống" in x for x in h.check("docs: x", bad, CLEAN_COMMITS))


# --- đường vòng: vẫn phải bắt ---------------------------------------------------------------------
@pytest.mark.parametrize(
    "line",
    [
        "Co-Authored-By: A <a@b.c>",
        "co-authored-by: A <a@b.c>",
        "   Co-Authored-By: A",  # khoảng trắng đầu dòng
        "\tCo-Authored-By: A",
        "> - Co-Authored-By: A",  # ký hiệu đầu dòng
        "Co\u2011Authored\u2011By: A <a@b.c>",  # gạch nối không ngắt
        "Co\u200bAuthored-By: A",  # ký tự vô hình
        "Ｃｏ-Ａｕｔｈｏｒｅｄ-Ｂｙ: A",  # chữ toàn góc
        "Co-Authored-By : A",  # khoảng trắng trước dấu hai chấm
        "Coauthored-by: A",
        "Co authored by: A",
        "fix: x. Co-Authored-By: Claude <noreply@anthropic.com>",  # trailer lệch dòng, có email
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
        "Generated with Claude Code",
        "GENERATED WITH  [CLAUDE CODE]",
        "Generated\u200b with Claude Code",
        "Generated by Claude",
    ],
)
def test_duong_vong_bi_bat_o_than_pr_va_commit(line):
    assert h.check("feat: x (#1)", GOOD_BODY + "\n" + line + "\n", CLEAN_COMMITS)
    assert h.check("feat: x (#1)", GOOD_BODY, CLEAN_COMMITS + "\n" + line + "\n")
    assert h.check(
        "feat: x (#1)", GOOD_BODY, CLEAN_COMMITS + "\r\n" + line + "\r\n"
    )  # CRLF


@pytest.mark.parametrize(
    "heading_block",
    [
        "<!--\n## Kết quả kiểm chứng\n-->\n",  # tiêu đề nằm trong chú thích
        "```\n## Kết quả kiểm chứng\n```\n",  # tiêu đề nằm trong khối mã
    ],
)
def test_tieu_de_gia_trong_chu_thich_hoac_khoi_ma_khong_tinh(heading_block):
    body = (
        "## Task liên quan\n\nKAN-1\n\n"
        + heading_block
        + "\n## Giới hạn\n\nChưa kiểm trên máy khác nên chưa chắc.\n"
    )
    assert any("thiếu mục" in x for x in h.check("feat: x", body, CLEAN_COMMITS))


@pytest.mark.parametrize(
    "filler",
    [
        "x" * 40,
        "........................",
        "-----------------------",
        "a a a a a a a a a a",
        "TBD",
        "todo todo",
    ],
)
def test_muc_doen_chu_khong_noi_dung_van_bi_bat(filler):
    body = _with().replace(
        "Chưa kiểm trên Python 3.12.14; số trên chưa ai tính lại.", filler
    )
    assert any("trống" in x for x in h.check("docs: x", body, CLEAN_COMMITS))


def test_chu_thich_khong_tinh_la_noi_dung():
    body = _with().replace(
        "Chưa kiểm trên Python 3.12.14; số trên chưa ai tính lại.",
        "<!-- Chưa kiểm trên Python 3.12.14 nên chưa chắc -->",
    )
    assert any("trống" in x for x in h.check("docs: x", body, CLEAN_COMMITS))


def test_thieu_han_muc_van_bi_bat():
    body = "## Task liên quan\n\nKAN-1\n\n## Giới hạn\n\nChưa kiểm trên máy khác nên chưa chắc.\n"
    assert any(h.LABELS[h.RESULT] in x for x in h.check("feat: x", body, CLEAN_COMMITS))


@pytest.mark.parametrize("title", ["feat: x kan-12", "fix: y (#44)", "fix #5"])
def test_ma_task_chap_nhan_bien_the(title):
    body = _with().replace("KAN-91", "KAN-")
    assert h.check(title, body, CLEAN_COMMITS) == []


def test_cau_mo_ta_quy_tac_co_ca_hai_cum_van_khong_do():
    desc = "- cấm `Co-Authored-By:` và `Generated with [Claude Code]` trong commit\n"
    assert h.check("feat: x (#1)", GOOD_BODY + "\n" + desc, CLEAN_COMMITS) == []


# --- Miễn cho tác giả dependabot[bot] (C-36) ---
DEPENDABOT_BODY = """Bumps [fastapi](https://github.com/fastapi/fastapi) from 0.162.0 to 0.163.0.
<details>
<summary>Release notes</summary>
<p>Some notes.</p>
</details>

Dependabot will resolve any conflicts with this PR as long as you don't alter it yourself.
You can trigger a rebase of this PR by commenting `@dependabot rebase`.
"""
DEPENDABOT_COMMITS = (
    "chore(deps): bump fastapi from 0.162.0 to 0.163.0\n\n"
    "Signed-off-by: dependabot[bot] <support@github.com>\n"
)
BOT = "dependabot[bot]"


def test_bot_that_vuot_khong_can_muc_va_ma_task():
    assert (
        h.check("chore(deps): bump fastapi", DEPENDABOT_BODY, DEPENDABOT_COMMITS, BOT)
        == []
    )


def test_cung_noi_dung_do_nguoi_thuong_van_truot():
    assert h.check(
        "chore(deps): bump fastapi", DEPENDABOT_BODY, DEPENDABOT_COMMITS, "luciusHo"
    )
    assert h.check(
        "chore(deps): bump fastapi", DEPENDABOT_BODY, DEPENDABOT_COMMITS
    )  # không author


@pytest.mark.parametrize(
    "author",
    [
        "Dependabot[bot]",
        "dependabot[bot] ",
        "dependabot",
        "dependabot[bot]x",
        "xdependabot[bot]",
        "app/dependabot",
        "",
    ],
)
def test_chi_khop_dung_chuoi_tac_gia(author):
    assert h.check("chore: x", DEPENDABOT_BODY, DEPENDABOT_COMMITS, author)


def test_ten_bot_trong_tieu_de_hay_than_khong_duoc_mien():
    body = "Opened by dependabot[bot]\n" + DEPENDABOT_BODY
    assert h.check(
        "dependabot[bot]: bump fastapi", body, DEPENDABOT_COMMITS, "luciusHo"
    )


@pytest.mark.parametrize(
    ("title", "body", "commits"),
    [
        (
            "chore(deps): bump x",
            DEPENDABOT_BODY + "\nCo-Authored-By: A <a@b.c>\n",
            DEPENDABOT_COMMITS,
        ),
        (
            "chore(deps): bump x",
            DEPENDABOT_BODY,
            DEPENDABOT_COMMITS + "\nCo-Authored-By: Claude <noreply@anthropic.com>\n",
        ),
        (
            "chore(deps): bump x",
            DEPENDABOT_BODY
            + "\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n",
            DEPENDABOT_COMMITS,
        ),
        ("Generated with Claude: bump", DEPENDABOT_BODY, DEPENDABOT_COMMITS),
    ],
)
def test_bot_van_bi_cam_attribution(title, body, commits):
    assert h.check(title, body, commits, BOT)


def test_main_author_qua_tham_so(tmp_path, capsys):
    (tmp_path / "b.md").write_text(DEPENDABOT_BODY, encoding="utf-8")
    (tmp_path / "c.txt").write_text(DEPENDABOT_COMMITS, encoding="utf-8")
    base = [
        "--title",
        "chore(deps): bump",
        "--body-file",
        str(tmp_path / "b.md"),
        "--commits-file",
        str(tmp_path / "c.txt"),
    ]
    assert h.main([*base, "--author", BOT]) == 0
    assert h.main(base) == 1
    assert h.main([*base, "--author", "luciusHo"]) == 1


def test_workflow_lay_tac_gia_tu_user_login_qua_bien_moi_truong():
    from pathlib import Path

    wf = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )
    assert "PR_AUTHOR: ${{ github.event.pull_request.user.login }}" in wf
    assert '--author "$PR_AUTHOR"' in wf
    assert "github.actor" not in wf


UPSTREAM_NOTES = DEPENDABOT_BODY.replace(
    "<p>Some notes.</p>",
    "<p>Changelog</p>\n<ul>\n<li>fix\n</ul>\nCo-authored-by: Upstream Dev <dev@example.com>\n"
    "Generated with Claude Code\n",
)


def test_release_notes_co_authored_trong_details_khong_lam_bot_truot():
    assert "Co-authored-by: Upstream" in UPSTREAM_NOTES
    assert h.check("chore(deps): bump x", UPSTREAM_NOTES, DEPENDABOT_COMMITS, BOT) == []


def test_nguoi_thuong_van_loi_voi_cung_than_co_co_authored():
    problems = h.check(
        "chore(deps): bump x", UPSTREAM_NOTES, DEPENDABOT_COMMITS, "luciusHo"
    )
    assert any("thân PR" in p for p in problems)


@pytest.mark.parametrize(
    "commits",
    [
        DEPENDABOT_COMMITS + "\nCo-Authored-By: A <a@b.c>\n",
        DEPENDABOT_COMMITS + "\nGenerated with Claude Code\n",
    ],
)
def test_commit_cua_bot_co_attribution_van_loi_du_than_co_details(commits):
    assert any(
        "commit" in p
        for p in h.check("chore(deps): bump x", UPSTREAM_NOTES, commits, BOT)
    )


def test_bot_co_dong_cam_ngoai_details_van_loi():
    body = DEPENDABOT_BODY + "\nCo-authored-by: A <a@b.c>\n"
    assert any(
        "thân PR" in p
        for p in h.check("chore(deps): bump x", body, DEPENDABOT_COMMITS, BOT)
    )


def test_details_viet_hoa_va_nhieu_dong_van_duoc_bo():
    body = "Bumps x.\n<DETAILS>\n<summary>n</summary>\nCo-authored-by: A <a@b.c>\n</DETAILS >\n"
    assert h.check("chore(deps): bump x", body, DEPENDABOT_COMMITS, BOT) == []
