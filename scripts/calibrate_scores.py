"""Hiệu chuẩn điểm model trên file VALIDATION và chọn ngưỡng theo mục tiêu tỉ lệ ảnh thật bị gọi AI (ADV-12, #144).

    python -m scripts.calibrate_scores --scores validation_scores.csv --target-fpr 0.05 [--bins 15] [--output f.json]

CSV: `sample_id,label,score` (label 0 = thật, 1 = AI; score trong [0, 1]). Hai cách hiệu chuẩn; temperature luôn đơn điệu tăng,
Platt chỉ đơn điệu tăng khi hệ số `a > 0` (nếu điểm tương quan NGƯỢC với nhãn thì `a <= 0`, đảo thứ tự: bị TỪ CHỐI,
thoát 2). Khi đơn điệu tăng thì thứ tự điểm và AUROC không đổi (hiệu chuẩn không tự "sửa" ảnh thật bị gọi AI nếu
ngưỡng không đổi):
- Platt: hồi quy logistic một chiều trên logit(score) (gần như không điều chuẩn, C = 1e10);
- temperature scaling: `sigmoid(logit(score) / T)`, tìm T > 0 làm NLL nhỏ nhất.
In ECE (15 bin cùng độ rộng), Brier và NLL trước và sau. Ngưỡng: nhỏ nhất `t` sao cho tỉ lệ ảnh thật có
`score >= t` không vượt `--target-fpr`, kèm FPR và recall đạt được; ngưỡng báo cả ở điểm gốc và điểm đã hiệu chuẩn.
CHỌN TRÊN VALIDATION, KHÔNG DÙNG CHO ĐÁNH GIÁ CUỐI: không chạy file này trên test, không dùng validation đã chọn
ngưỡng để báo độ chính xác cuối. Ngưỡng chọn trên validation GenImage chưa chắc chuyển sang miền ảnh điện thoại.
Quy tắc ngưỡng ở đây là `score >= t`; kết luận "Ảnh AI" của sản phẩm dùng `score > high`. Điểm suy biến (không đổi,
chỉ 0 và 1, T chạm cận tìm kiếm, ngưỡng nằm trên mọi điểm) ghi vào `warnings` của JSON và stderr. Chỉ đọc CSV, không
chạy model. Thoát 0, hoặc 2 khi dữ liệu/tham số/đầu ra sai.
"""

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.linear_model import LogisticRegression

EPS = 1e-6  # chặn điểm 0 hoặc 1 khỏi logit vô hạn
NOTE = (
    "Chọn trên validation, không dùng cho đánh giá cuối: ngưỡng và tham số hiệu chuẩn phải khóa "
    "trước khi chấm test hoặc cohort độc lập."
)


def read_scores(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """(y, p). ValueError nếu cột thiếu, ID trùng, nhãn ngoài 0/1, điểm NaN/ngoài [0, 1] hoặc thiếu một lớp."""
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or any(
                c not in reader.fieldnames for c in ("sample_id", "label", "score")
            ):
                raise ValueError(f"{path}: cần cột sample_id, label, score")
            seen, ys, ps = set(), [], []
            for n, row in enumerate(reader, 2):
                sid = (row["sample_id"] or "").strip()
                if not sid or sid in seen:
                    raise ValueError(f"{path}:{n}: sample_id rỗng hoặc trùng")
                seen.add(sid)
                if row["label"] not in ("0", "1"):
                    raise ValueError(f"{path}:{n}: label phải là 0 hoặc 1")
                try:
                    score = float(row["score"])
                except (TypeError, ValueError):
                    raise ValueError(f"{path}:{n}: score không phải số") from None
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError(
                        f"{path}:{n}: score không hữu hạn hoặc ngoài [0, 1]"
                    )
                ys.append(int(row["label"]))
                ps.append(score)
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"không đọc được {path}: {exc}") from exc
    y, p = np.array(ys), np.array(ps)
    if len(set(ys)) < 2:
        raise ValueError(f"{path}: cần cả hai lớp (thật và AI)")
    return y, p


def logit(p: np.ndarray) -> np.ndarray:
    q = np.clip(p, EPS, 1 - EPS)
    return np.log(q / (1 - q))


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-z))


def nll(y: np.ndarray, p: np.ndarray) -> float:
    q = np.clip(p, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def ece(y: np.ndarray, p: np.ndarray, bins: int = 15) -> float:
    """Expected calibration error, bin cùng độ rộng; điểm bằng 1 vào bin cuối."""
    index = np.minimum((p * bins).astype(int), bins - 1)
    total = 0.0
    for b in range(bins):
        m = index == b
        if m.any():
            total += m.sum() / len(p) * abs(y[m].mean() - p[m].mean())
    return float(total)


def fit_platt(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """(a, b) với p' = sigmoid(a * logit(p) + b)."""
    model = LogisticRegression(C=1e10, max_iter=1000).fit(logit(p)[:, None], y)
    return float(model.coef_[0, 0]), float(model.intercept_[0])


def fit_temperature(y: np.ndarray, p: np.ndarray) -> float:
    """T > 0 làm NLL của sigmoid(logit(p) / T) nhỏ nhất (tìm trên log T trong [e^-4, e^4])."""
    z = logit(p)
    result = minimize_scalar(
        lambda log_t: nll(y, sigmoid(z / math.exp(log_t))),
        bounds=(-4, 4),
        method="bounded",
        options={"xatol": 1e-8},
    )
    return float(math.exp(result.x))


def pick_threshold(y: np.ndarray, p: np.ndarray, target_fpr: float) -> dict:
    """Ngưỡng nhỏ nhất (gọi AI khi score >= t) sao cho FPR <= target; nếu không điểm nào đạt thì t > mọi điểm."""
    real, ai = y == 0, y == 1
    candidates = np.unique(p)
    for t in candidates:
        fpr = float(((p >= t) & real).sum() / real.sum())
        if fpr <= target_fpr:
            break
    else:
        t = math.nextafter(float(candidates[-1]), math.inf)
    return {
        "threshold": float(t),
        "fpr": float(((p >= t) & real).sum() / real.sum()),
        "recall": float(((p >= t) & ai).sum() / ai.sum()),
    }


def metrics(y: np.ndarray, p: np.ndarray, bins: int) -> dict:
    return {"ece": ece(y, p, bins), "brier": brier(y, p), "nll": nll(y, p)}


def calibrate(y: np.ndarray, p: np.ndarray, target_fpr: float, bins: int = 15) -> dict:
    if p.min() == p.max():
        raise ValueError(
            "mọi điểm bằng nhau: không hiệu chuẩn được (kiểm model hoặc file điểm)"
        )
    a, b = fit_platt(y, p)
    if not a > 0:
        raise ValueError(
            f"Platt ra hệ số a = {a:.6g} <= 0: điểm không tương quan dương với nhãn (có thể đảo nhãn hoặc điểm), "
            "hiệu chuẩn sẽ đảo thứ tự; từ chối"
        )
    warnings_out: list[str] = []
    if set(np.unique(p).tolist()) <= {0.0, 1.0}:
        warnings_out.append(
            "điểm chỉ gồm 0 và 1: logit bị kẹp, hiệu chuẩn không đáng tin"
        )
    temp = fit_temperature(y, p)
    if abs(math.log(temp)) > 4 - 1e-3:
        warnings_out.append(
            f"T = {temp:.4g} chạm cận tìm kiếm [e^-4, e^4]: kết quả temperature không đáng tin"
        )
    z = logit(p)
    platt_p, temp_p = sigmoid(a * z + b), sigmoid(z / temp)
    chosen = pick_threshold(y, p, target_fpr)
    raw = chosen["threshold"]
    if raw > 1.0:
        warnings_out.append(
            "không ngưỡng nào đạt mục tiêu FPR trên điểm hiện có: ngưỡng thực nằm trên mọi điểm "
            "(không ảnh nào được gọi AI); raw_score kẹp về 1.0 chỉ để hiển thị"
        )
    raw = min(max(raw, 0.0), 1.0)
    at = float(logit(np.array([raw]))[0])
    return {
        "n": len(y),
        "n_real": int((y == 0).sum()),
        "n_ai": int((y == 1).sum()),
        "bins": bins,
        "before": metrics(y, p, bins),
        "platt": {"a": a, "b": b, "after": metrics(y, platt_p, bins)},
        "temperature": {"T": temp, "after": metrics(y, temp_p, bins)},
        "threshold": {
            "target_fpr": target_fpr,
            "raw_score": raw,
            "platt_score": float(sigmoid(a * at + b)),
            "temperature_score": float(sigmoid(at / temp)),
            "fpr": chosen["fpr"],
            "recall": chosen["recall"],
            "rule": 'score >= t; kết luận "Ảnh AI" của sản phẩm dùng score > high',
        },
        "warnings": warnings_out,
        "note": NOTE,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hiệu chuẩn điểm trên validation (ADV-12)")
    ap.add_argument(
        "--scores",
        type=Path,
        required=True,
        help="CSV validation: sample_id,label,score",
    )
    ap.add_argument(
        "--target-fpr",
        type=float,
        required=True,
        help="mục tiêu tỉ lệ ảnh thật bị gọi AI",
    )
    ap.add_argument("--bins", type=int, default=15)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args(argv)
    if not 0 <= args.target_fpr <= 1 or args.bins < 1:
        print("LỖI: --target-fpr phải trong [0, 1] và --bins >= 1", file=sys.stderr)
        return 2
    try:
        y, p = read_scores(args.scores)
        report = calibrate(y, p, args.target_fpr, args.bins)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        try:
            args.output.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"LỖI: không ghi được {args.output}: {exc}", file=sys.stderr)
            return 2
    else:
        print(text)
    for warning in report["warnings"]:
        print(f"CẢNH BÁO: {warning}", file=sys.stderr)
    print(f"LƯU Ý: {NOTE}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
