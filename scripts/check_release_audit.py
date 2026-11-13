"""Release checker cho audit metadata: chặn (thoát 1) báo cáo của metadata_audit.py.

metadata_audit.py chỉ cảnh báo (chính sách 2026-11-12); script này mới là cổng release:
    python scripts/check_release_audit.py [--fail-on-vacuous] [data/metadata_audit.json]
Chặn khi: post A_eff > 0.55; thiếu slice hoặc slice thiếu một lớp; A_eff NaN hoặc ngoài [0.5, 1.0] (báo cáo hỏng); control
dương/âm không hợp lệ. Mọi đặc trưng post hằng số ("rỗng", vacuous: A_eff = 0.5 không
chứng minh dữ liệu sạch) mặc định chỉ CẢNH BÁO MẠNH và in "vacuous": true; thêm
--fail-on-vacuous để chặn. Thoát 0 đạt, 1 bị chặn, 2 thiếu hoặc hỏng đầu vào.
"""

import json
import sys
from pathlib import Path

try:  # chạy bằng đường dẫn script (python scripts/...) hoặc như module trong gói scripts
    from metadata_audit import FEATURES
except ImportError:
    from scripts.metadata_audit import FEATURES

MAX_A_EFF = 0.55
MIN_POSITIVE = 0.95  # control dương phải bắt được feature lộ nhãn


def _aeff_ok(v) -> bool:
    """A_eff = max(AUROC, 1 - AUROC) luôn trong [0.5, 1]; ngoài khoảng là báo cáo hỏng."""
    return isinstance(v, (int, float)) and 0.5 - 1e-9 <= v <= 1 + 1e-9


def problems(report: dict) -> list[str]:
    out = []
    datasets = {k: v for k, v in report.items() if k != "gate"}
    if not datasets:
        return ["báo cáo không có bộ dữ liệu nào"]
    for ds, r in datasets.items():
        sl = r["slices"]
        if "all" not in sl:
            out.append(f"{ds}: thiếu slice 'all'")
        for name, v in sl.items():
            post = v["post"]
            counts = post.get("test_counts", {})
            if not post["valid"] or not all(counts.get(c, 0) > 0 for c in ("0", "1")):
                out.append(f"{ds}/{name}: slice thiếu hoặc thiếu một lớp")
            elif not _aeff_ok(post.get("a_eff")):
                out.append(
                    f"{ds}/{name}: A_eff {post.get('a_eff')} ngoài [0.5, 1.0] hoặc "
                    "không hữu hạn (báo cáo hỏng)"
                )
            elif post["a_eff"] > MAX_A_EFF:
                out.append(f"{ds}/{name}: A_eff {post['a_eff']} > {MAX_A_EFF}")
        c = r["controls"]
        pos, neg = c["positive"].get("a_eff"), c["negative"].get("a_eff")
        if not _aeff_ok(pos) or pos < MIN_POSITIVE:
            out.append(f"{ds}: control dương không hợp lệ ({pos})")
        if not _aeff_ok(neg) or neg > MAX_A_EFF:
            out.append(f"{ds}: control âm không hợp lệ ({neg})")
    return out


def vacuous(report: dict) -> list[str]:
    """Bộ dữ liệu có mọi đặc trưng post hằng số: A_eff = 0.5 do rỗng, không do sạch."""
    return [
        ds
        for ds, r in report.items()
        if ds != "gate"
        # báo cáo cũ không có n_features: dùng danh sách đặc trưng của metadata_audit.py
        and len(r["constant_features"]["post"]) >= r.get("n_features", len(FEATURES))
    ]


def main(argv: list[str]) -> int:
    strict = "--fail-on-vacuous" in argv
    args = [a for a in argv if a != "--fail-on-vacuous"]
    path = Path(args[0] if args else "data/metadata_audit.json")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        found = problems(report)
        empty = vacuous(report)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"Không đọc được báo cáo audit {path}: {exc!r}")
        return 2
    for ds in empty:
        print(
            f"CẢNH BÁO MẠNH: {ds}: mọi đặc trưng post đều hằng số; A_eff = 0.5 "
            "KHÔNG chứng minh dữ liệu sạch"
        )
    if strict and empty:
        found.append("vacuous (--fail-on-vacuous)")
    for p in found:
        print(f"CHẶN: {p}")
    print(json.dumps({"vacuous": bool(empty), "blocked": bool(found)}))
    if found:
        verdict = "BỊ CHẶN"
    elif empty:
        verdict = (
            "ĐẠT NHƯNG RỖNG (A_eff = 0,5 vì mọi đặc trưng là hằng số; "
            "không chứng minh dữ liệu sạch)"
        )
    else:
        verdict = "ĐẠT"
    print(f"Release audit: {verdict}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
