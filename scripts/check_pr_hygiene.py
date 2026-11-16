"""Kiểm vệ sinh PR (CI-2): chỉ đọc, chỉ dùng thư viện chuẩn.

Ba check: (1) commit và thân PR không có dòng attribution bị cấm; (2) thân PR có hai mục
"Kết quả kiểm chứng" và "Giới hạn, rủi ro và việc chưa làm" với nội dung thật, không chỉ chú thích
mẫu; (3) tiêu đề hoặc mục "Task liên quan" có KAN-<số> hoặc #<số>.

Dùng: python -m scripts.check_pr_hygiene --title "..." --body-file body.md --commits-file commits.txt
Với --author dependabot[bot] (đúng chuỗi) bỏ yêu cầu mục nội dung và mã KAN/#; vẫn kiểm dòng bị cấm ở tiêu đề, commit và thân PR (trừ khối <details>).
Thoát 0 nếu đạt, 1 nếu có lỗi, 2 nếu thiếu đầu vào.
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

MIN_CHARS = 20
MIN_WORDS = 4
# Tiền tố tiêu đề đã bỏ dấu và hạ chữ thường; chấp nhận đuôi như "(Coder tự đo)", ":" hay "và việc còn chờ".
RESULT = "ket qua kiem chung"
LIMITS = "gioi han"
TASK = "task lien quan"
LABELS = {
    RESULT: "Kết quả kiểm chứng",
    LIMITS: "Giới hạn, rủi ro và việc chưa làm",
    TASK: "Task liên quan",
}
TASK_REF = re.compile(r"KAN-\d+|(?<![\w&])#\d+", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_INVISIBLE = dict.fromkeys(
    [*range(0x200B, 0x2010), 0x2060, 0xFEFF, 0x00AD, *range(0x202A, 0x202F)]
)
_DASHES = dict.fromkeys([*range(0x2010, 0x2016), 0x2212, 0xFE58, 0xFE63, 0xFF0D], "-")
# Dòng còn nguyên từ mẫu (xem .github/pull_request_template.md): chưa điền.
_PLACEHOLDER = re.compile(
    r"^(```\w*|\*\*Cách reviewer chạy lại:\*\*|.*(→|->)\s*$|.*___.*)$"
)
_HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]*(.*?)[ \t#]*$")
# Dòng bắt đầu bằng cụm bị cấm (cho phép khoảng trắng, ký hiệu, emoji đầu dòng), hoặc đúng dạng trailer
# "Co-Authored-By: Tên <email>" ở giữa dòng. Câu mô tả quy tắc (không có email) không khớp.
_FORBIDDEN_LINE = (
    re.compile(r"^[\W_]*co[-\s_]?authored[-\s_]?by\s*:", re.IGNORECASE),
    re.compile(r"^[\W_]*generated\s+(?:with|by)\s*\W*claude", re.IGNORECASE),
)
_TRAILER_ANYWHERE = re.compile(
    r"co[-\s_]?authored[-\s_]?by\s*:[^<\n]{1,80}<[^<>\s]+@[^<>\s]+>", re.IGNORECASE
)


def _clean(text: str) -> str:
    """NFKC, bỏ ký tự vô hình, quy mọi gạch ngang Unicode về '-', xuống dòng chuẩn."""
    text = unicodedata.normalize("NFKC", text).translate(_INVISIBLE).translate(_DASHES)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _fold(text: str) -> str:
    """Bỏ dấu, đ thành d, chữ thường, gộp khoảng trắng: so khớp tiêu đề không phân biệt dấu/hoa thường."""
    text = unicodedata.normalize(
        "NFKD", _clean(text).replace("đ", "d").replace("Đ", "D")
    )
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


def forbidden_lines(text: str, where: str) -> list[str]:
    found = []
    for line in _clean(text).split("\n"):
        if any(p.search(line) for p in _FORBIDDEN_LINE) or _TRAILER_ANYWHERE.search(
            line
        ):
            found.append(f"{where}: có dòng bị cấm: {line.strip()[:80]!r}")
    return found


def _headings(body: str):
    """(chỉ số dòng, cấp, văn bản đã gấp) của mọi tiêu đề ATX ngoài khối mã và chú thích."""
    lines = _COMMENT.sub("", _clean(body)).split("\n")
    out, fence = [], False
    for k, line in enumerate(lines):
        if re.match(r"^ {0,3}(```|~~~)", line):
            fence = not fence
            continue
        m = None if fence else _HEADING.match(line)
        if m:
            text = re.sub(
                r"^\**\s*(?:\d+\s*[.):-]?\s*)?", "", m.group(2)
            )  # "**", "1.", "2)"
            out.append((k, len(m.group(1)), _fold(text.strip("* "))))
    return lines, out


def section(body: str, key: str) -> str | None:
    """Nội dung dưới tiêu đề khớp `key` (tiền tố, bỏ dấu, hoa thường, `##` hoặc `###`...) tới tiêu đề
    kế tiếp cùng cấp hoặc cao hơn; None nếu không có tiêu đề."""
    lines, heads = _headings(body)
    for n, (k, level, text) in enumerate(heads):
        if text.startswith(key):
            end = next((h[0] for h in heads[n + 1 :] if h[1] <= level), len(lines))
            return "\n".join(lines[k + 1 : end])
    return None


def real_content(text: str) -> str:
    lines = [ln.strip() for ln in _COMMENT.sub("", _clean(text)).split("\n")]
    return " ".join(ln for ln in lines if ln and not _PLACEHOLDER.match(ln))


def _has_substance(text: str) -> bool:
    """Đủ ký tự và ít nhất MIN_WORDS từ, trong đó có từ khác nhau (chặn chuỗi lặp độn chữ)."""
    words = re.findall(r"\w+", real_content(text))
    return (
        len(real_content(text)) >= MIN_CHARS
        and len(words) >= MIN_WORDS
        and len(set(words)) >= 2
    )


# Tác giả PR do GitHub gán; người thường không đặt được tên có ngoặc vuông. Chỉ so đúng chuỗi này.
BOT_AUTHOR = "dependabot[bot]"


_DETAILS = re.compile(r"<details\b.*?</details\s*>", re.DOTALL | re.IGNORECASE)


def check(title: str, body: str, commits: str, author: str = "") -> list[str]:
    bot = author == BOT_AUTHOR
    # Thân PR của bot chứa release notes của thư viện trong <details> (có thể có dòng
    # "Co-authored-by:" của upstream): chỉ bỏ phần đó khi kiểm cấm. Commit của PR vẫn kiểm đủ.
    checked_body = _DETAILS.sub("", _clean(body)) if bot else body
    problems = forbidden_lines(checked_body, "thân PR") + forbidden_lines(
        commits, "commit"
    )
    problems += forbidden_lines(title, "tiêu đề")
    if bot:
        # Miễn mẫu nội dung và mã KAN/#; không miễn kiểm dòng bị cấm ở trên.
        return problems
    for key in (RESULT, LIMITS):
        sec = section(body, key)
        if sec is None:
            problems.append(f"thân PR thiếu mục '{LABELS[key]}'")
        elif not _has_substance(sec):
            problems.append(f"mục '{LABELS[key]}' trống hoặc còn nguyên mẫu")
    task = section(body, TASK) or ""
    if not TASK_REF.search(_clean(title) + "\n" + _COMMENT.sub("", _clean(task))):
        problems.append(
            "không có mã KAN-<số> hoặc #<số> ở tiêu đề hoặc mục 'Task liên quan'"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--title", required=True)
    ap.add_argument("--body-file", type=Path, required=True)
    ap.add_argument("--commits-file", type=Path, required=True)
    ap.add_argument(
        "--author",
        default="",
        help="login tác giả PR (github.event.pull_request.user.login)",
    )
    a = ap.parse_args(argv)
    try:
        body = a.body_file.read_text(encoding="utf-8")
        commits = a.commits_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Không đọc được đầu vào: {exc}", file=sys.stderr)
        return 2
    problems = check(a.title, body, commits, a.author)
    for p in problems:
        print(f"LỖI: {p}")
    print("pr-hygiene: " + ("ĐẠT" if not problems else f"{len(problems)} lỗi"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
