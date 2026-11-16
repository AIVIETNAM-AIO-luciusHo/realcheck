"""Kiểm vệ sinh PR (CI-2): chỉ đọc, chỉ dùng thư viện chuẩn.

Ba check: (1) commit và thân PR không có dòng attribution bị cấm; (2) thân PR có hai mục
"Kết quả kiểm chứng" và "Giới hạn, rủi ro và việc chưa làm" với nội dung thật, không chỉ chú thích
mẫu; (3) tiêu đề hoặc mục "Task liên quan" có KAN-<số> hoặc #<số>.

Dùng: python -m scripts.check_pr_hygiene --title "..." --body-file body.md --commits-file commits.txt
Thoát 0 nếu đạt, 1 nếu có lỗi, 2 nếu thiếu đầu vào.
"""

import argparse
import re
import sys
from pathlib import Path

FORBIDDEN = (
    re.compile(r"^[\W_]*co-authored-by\s*:", re.IGNORECASE),
    re.compile(r"^[\W_]*generated with\s*\[?claude code", re.IGNORECASE),
)
RESULT = "Kết quả kiểm chứng"
LIMITS = "Giới hạn, rủi ro và việc chưa làm"
TASK = "Task liên quan"
TASK_REF = re.compile(r"KAN-\d+|(?<![\w&])#\d+")
MIN_CHARS = 20
# Dòng còn nguyên từ mẫu (xem .github/pull_request_template.md): chưa điền.
_PLACEHOLDER = re.compile(
    r"^(```\w*|\*\*Cách reviewer chạy lại:\*\*|.*(→|->)\s*$|.*___.*)$"
)


def forbidden_lines(text: str, where: str) -> list[str]:
    return [
        f"{where}: có dòng bị cấm: {line.strip()[:80]!r}"
        for line in text.splitlines()
        if any(p.search(line) for p in FORBIDDEN)
    ]


def section(body: str, title: str) -> str | None:
    """Nội dung dưới tiêu đề `## title` tới tiêu đề `## ` kế tiếp; None nếu không có tiêu đề (cho phép đuôi như "(Coder tự đo)")."""
    m = re.search(rf"^##\s+{re.escape(title)}\b.*$", body, re.MULTILINE)
    if not m:
        return None
    rest = body[m.end() :]
    nxt = re.search(r"^##\s", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def real_content(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    lines = [ln.strip() for ln in text.splitlines()]
    return " ".join(ln for ln in lines if ln and not _PLACEHOLDER.match(ln))


def check(title: str, body: str, commits: str) -> list[str]:
    problems = forbidden_lines(body, "thân PR") + forbidden_lines(commits, "commit")
    for name in (RESULT, LIMITS):
        sec = section(body, name)
        if sec is None:
            problems.append(f"thân PR thiếu mục '{name}'")
        elif len(real_content(sec)) < MIN_CHARS:
            problems.append(f"mục '{name}' trống hoặc còn nguyên mẫu")
    task = section(body, TASK) or ""
    if not TASK_REF.search(
        title + "\n" + re.sub(r"<!--.*?-->", "", task, flags=re.DOTALL)
    ):
        problems.append(
            "không có mã KAN-<số> hoặc #<số> ở tiêu đề hoặc mục 'Task liên quan'"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--title", required=True)
    ap.add_argument("--body-file", type=Path, required=True)
    ap.add_argument("--commits-file", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        body = a.body_file.read_text(encoding="utf-8")
        commits = a.commits_file.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Không đọc được đầu vào: {exc}", file=sys.stderr)
        return 2
    problems = check(a.title, body, commits)
    for p in problems:
        print(f"LỖI: {p}")
    print("pr-hygiene: " + ("ĐẠT" if not problems else f"{len(problems)} lỗi"))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
