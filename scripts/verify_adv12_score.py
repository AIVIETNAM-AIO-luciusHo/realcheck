"""Kiểm tay: model e571 THẬT chấm một ảnh tham chiếu ra đúng điểm mong đợi (ADV-12, E0).

Cần CLIP cache offline (HF_HUB_OFFLINE=1). Không chạy trong pytest vì G01 cấm test bị skip.
Thoát 0 nếu |điểm - expected| <= tolerance, 1 nếu lệch, 2 nếu lỗi đầu vào hoặc nạp model.
"""

import argparse
import math
import sys
from pathlib import Path

from PIL import Image


def within_tolerance(got: float, expected: float, tolerance: float) -> bool:
    return (
        all(math.isfinite(v) for v in (got, expected, tolerance))
        and tolerance >= 0
        and abs(got - expected) <= tolerance
    )


def score_image(model: Path, image: Path) -> float:
    from models.score import load_scorer  # nạp torch/CLIP chỉ khi chạy thật

    with Image.open(image) as im:
        im.load()
        return float(load_scorer(model)(im))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--expected", type=float, required=True)
    ap.add_argument("--tolerance", type=float, default=1e-6)
    args = ap.parse_args(argv)
    if not (math.isfinite(args.tolerance) and args.tolerance >= 0):
        print("--tolerance phải hữu hạn và không âm", file=sys.stderr)
        return 2
    try:
        got = score_image(args.model, args.image)
    except Exception as exc:  # noqa: BLE001 - mọi lỗi nạp model/ảnh đều là lỗi đầu vào
        print(f"Không chấm được: {exc}", file=sys.stderr)
        return 2
    ok = within_tolerance(got, args.expected, args.tolerance)
    print(
        f"score={got!r} expected={args.expected!r} diff={abs(got - args.expected):.3g} "
        f"tolerance={args.tolerance:g} -> {'KHỚP' if ok else 'LỆCH'}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
