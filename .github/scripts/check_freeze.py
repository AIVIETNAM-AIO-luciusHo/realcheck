"""Chặn PR chạm thư mục đóng băng khi freeze đang bật (CI-6, #181).

Chỉ đọc: nhận danh sách file đổi, nhãn của PR và cờ bật, in kết luận, thoát 0 hoặc 1.
Đặt ở .github/scripts/ để chính file này không nằm trong thư mục đóng băng.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

FROZEN_DIRS = ("app/", "nginx/", "models/", "locust/", "scripts/")
FROZEN_FILES = ("docker-compose.yml",)
OVERRIDE_LABEL = "freeze-override"


def parse_enabled(text: str) -> bool:
    """File freeze.yml bật khi có dòng `enabled: true` (không phân biệt hoa thường, bỏ dòng #)."""
    for line in text.splitlines():
        m = re.fullmatch(r"\s*enabled\s*:\s*(\S+)\s*(#.*)?", line, re.IGNORECASE)
        if m:
            return m.group(1).strip("'\"").lower() == "true"
    return False


def frozen_paths(files: list[str]) -> list[str]:
    out = []
    for f in files:
        f = f.strip().lstrip("./")
        if f in FROZEN_FILES or f.startswith(FROZEN_DIRS):
            out.append(f)
    return out


def decide(files: list[str], labels: list[str], enabled: bool) -> tuple[bool, str]:
    hit = frozen_paths(files)
    if not enabled:
        return True, "Freeze đang tắt: không kiểm."
    if not hit:
        return True, "Freeze bật, PR không chạm thư mục đóng băng."
    if OVERRIDE_LABEL in labels:
        return (
            True,
            f"Freeze bật, PR chạm {len(hit)} file đóng băng nhưng có nhãn {OVERRIDE_LABEL}.",
        )
    shown = "\n".join(f"  - {p}" for p in hit[:20])
    more = f"\n  ... và {len(hit) - 20} file nữa" if len(hit) > 20 else ""
    return False, (
        f"Freeze đang bật: PR chạm {len(hit)} file đóng băng.\n{shown}{more}\n"
        f"Chỉ chủ repo gắn nhãn {OVERRIDE_LABEL} mới được ngoại lệ."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--files",
        required=True,
        help="file chứa danh sách đường dẫn đổi, mỗi dòng một đường dẫn",
    )
    ap.add_argument(
        "--freeze-file",
        help="nội dung .github/freeze.yml của nhánh gốc (không phải của PR)",
    )
    args = ap.parse_args(argv)
    with open(args.files, encoding="utf-8") as fh:
        files = [ln for ln in fh.read().splitlines() if ln.strip()]
    enabled = os.environ.get("FREEZE_VAR", "").strip().lower() == "true"
    if args.freeze_file and os.path.exists(args.freeze_file):
        with open(args.freeze_file, encoding="utf-8") as fh:
            enabled = enabled or parse_enabled(fh.read())
    try:
        labels = [str(x) for x in json.loads(os.environ.get("LABELS", "[]"))]
    except ValueError:
        print("LABELS không phải JSON hợp lệ", file=sys.stderr)
        return 2
    ok, msg = decide(files, labels, enabled)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
