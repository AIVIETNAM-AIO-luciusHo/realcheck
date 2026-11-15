"""So hai file điểm (model A và model B) trên CÙNG ảnh, có cặp và bootstrap theo nhóm (ADV-12, #144).

    python -m scripts.compare_models --a scores_e571.csv --b scores_candidate.csv [--output so_sanh.json]

Mỗi CSV: `sample_id,label,score[,group_id,source]` (label 0 = thật, 1 = AI; score trong [0, 1]).
Không có `group_id` thì mỗi ảnh là một nhóm; không có `source` thì mọi ảnh là nguồn "(none)" (không tách slice).
Hai file phải có đúng cùng tập `sample_id` (và cùng label, group_id, source cho từng ID); ID trùng,
điểm NaN/ngoài [0, 1], nhãn không hợp lệ hoặc nhóm mang hai nhãn bị từ chối (thoát 2).

Số đo theo từng slice (`__all__` là tổng, và từng `source`; source tên "all" là slice riêng): AUROC (tự tính, ties nửa trọng số), tỉ lệ ảnh thật bị gọi AI
ở ngưỡng nhị phân (`score >= binary`) và ở ngưỡng cao đã khóa (`score > high`, kết luận "Ảnh AI"), recall ảnh AI
ở hai ngưỡng đó, số ảnh "Chưa chắc" (`low <= score <= high`, giống models.train.metrics). Hiệu A - B kèm khoảng
tin cậy 95% bootstrap THEO NHÓM (cùng một bộ trọng số cho A và B nên có cặp; phân tầng theo nhãn; seed cố định).
Chỉ dùng numpy; không đọc ảnh, không chạy model. Đây là công cụ phát triển: không dùng để chọn ngưỡng trên test.
"""

import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

REQUIRED = ("sample_id", "label", "score")
METRICS = (
    "auroc",
    "fpr_binary",
    "fpr_high",
    "recall_binary",
    "recall_high",
    "uncertain_rate",
)
NO_SOURCE = "(none)"
TOTAL_SLICE = "__all__"  # slice tổng; một source tên "all" là slice riêng, không bị gộp
CHUNK = 250  # số replicate mỗi lượt, để ma trận trọng số không quá lớn


def read_scores(path: Path) -> dict[str, dict]:
    """{sample_id: {label, score, group_id, source}}; ValueError nếu file hỏng."""
    try:
        with Path(path).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or any(
                c not in reader.fieldnames for c in REQUIRED
            ):
                raise ValueError(f"{path}: cần cột {', '.join(REQUIRED)}")
            rows: dict[str, dict] = {}
            for n, row in enumerate(reader, 2):
                sid = (row["sample_id"] or "").strip()
                if not sid:
                    raise ValueError(f"{path}:{n}: sample_id rỗng")
                if sid in rows:
                    raise ValueError(f"{path}:{n}: sample_id trùng: {sid}")
                if row["label"] not in ("0", "1"):
                    raise ValueError(
                        f"{path}:{n}: label phải là 0 hoặc 1, nhận {row['label']!r}"
                    )
                try:
                    score = float(row["score"])
                except (TypeError, ValueError):
                    raise ValueError(f"{path}:{n}: score không phải số") from None
                if not math.isfinite(score) or not 0 <= score <= 1:
                    raise ValueError(
                        f"{path}:{n}: score {row['score']!r} không hữu hạn hoặc ngoài [0, 1]"
                    )
                rows[sid] = {
                    "label": int(row["label"]),
                    "score": score,
                    "group_id": (row.get("group_id") or "").strip() or sid,
                    "source": (row.get("source") or "").strip() or NO_SOURCE,
                }
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise ValueError(f"không đọc được {path}: {exc}") from exc
    if not rows:
        raise ValueError(f"{path}: không có dòng dữ liệu")
    return rows


def align(a: dict[str, dict], b: dict[str, dict]) -> list[str]:
    """Danh sách ID đã sắp xếp; ValueError nếu hai file lệch ID hoặc lệch label/group/source."""
    if a.keys() != b.keys():
        only_a, only_b = sorted(a.keys() - b.keys()), sorted(b.keys() - a.keys())
        raise ValueError(
            f"hai file khác tập sample_id: chỉ có ở A {len(only_a)} (vd {only_a[:3]}), "
            f"chỉ có ở B {len(only_b)} (vd {only_b[:3]})"
        )
    ids = sorted(a)
    for sid in ids:
        for key in ("label", "group_id", "source"):
            if a[sid][key] != b[sid][key]:
                raise ValueError(
                    f"{sid}: {key} khác nhau giữa A ({a[sid][key]!r}) và B ({b[sid][key]!r})"
                )
    groups: dict[str, int] = {}
    for sid in ids:
        if groups.setdefault(a[sid]["group_id"], a[sid]["label"]) != a[sid]["label"]:
            raise ValueError(f"nhóm {a[sid]['group_id']!r} mang hai nhãn khác nhau")
    return ids


def weighted_metrics(
    y, p, w, low: float, binary: float, high: float
) -> dict[str, np.ndarray]:
    """Số đo cho từng hàng trọng số w (R, n); NaN khi mẫu số bằng 0 (vd thiếu một lớp)."""
    w = np.atleast_2d(np.asarray(w, dtype=np.float64))
    real, ai = y == 0, y == 1
    n_real, n_ai = w @ real, w @ ai
    with np.errstate(divide="ignore", invalid="ignore"):
        order = np.argsort(p, kind="stable")
        starts = np.r_[0, np.flatnonzero(np.diff(p[order])) + 1]
        pos = np.add.reduceat(w[:, order] * ai[order], starts, axis=1)
        neg = np.add.reduceat(w[:, order] * real[order], starts, axis=1)
        below = np.cumsum(neg, axis=1) - neg
        return {
            "auroc": (pos * (below + neg / 2)).sum(axis=1)
            / (pos.sum(axis=1) * neg.sum(axis=1)),
            "fpr_binary": (w @ ((p >= binary) & real)) / n_real,
            "fpr_high": (w @ ((p > high) & real)) / n_real,
            "recall_binary": (w @ ((p >= binary) & ai)) / n_ai,
            "recall_high": (w @ ((p > high) & ai)) / n_ai,
            "uncertain_rate": (w @ ((p >= low) & (p <= high))) / w.sum(axis=1),
            "uncertain_count": w @ ((p >= low) & (p <= high)),
        }


def group_weights(groups: list[str], y, replicates: int, seed: int) -> np.ndarray:
    """(replicates, n): số lần mỗi ảnh được chọn khi lấy mẫu lại cả nhóm, phân tầng theo nhãn."""
    y = np.asarray(y)
    rng = np.random.default_rng(seed)
    weights = np.zeros((replicates, len(groups)), dtype=np.float64)
    for label in (0, 1):
        samples = [i for i in range(len(groups)) if y[i] == label]
        names = sorted({groups[i] for i in samples})
        if not names:
            continue
        local = {g: k for k, g in enumerate(names)}
        draws = rng.integers(0, len(names), (replicates, len(names)))
        offsets = np.arange(replicates)[:, None] * len(names)
        counts = np.bincount(
            (draws + offsets).ravel(), minlength=replicates * len(names)
        )
        counts = counts.reshape(replicates, len(names))
        weights[:, samples] = counts[:, [local[groups[i]] for i in samples]]
    return weights


def _num(v) -> float | None:
    return None if v is None or not np.isfinite(v) else float(v)


def compare_slice(y, pa, pb, groups, args) -> dict:
    ones = np.ones((1, len(y)))
    args3 = (args.low, args.binary, args.high)
    point = {k: weighted_metrics(y, p, ones, *args3) for k, p in (("A", pa), ("B", pb))}
    weights = group_weights(groups, y, args.replicates, args.seed)
    boot = {"A": [], "B": []}
    for start in range(0, args.replicates, CHUNK):
        chunk = weights[start : start + CHUNK]
        for key, p in (("A", pa), ("B", pb)):
            boot[key].append(weighted_metrics(y, p, chunk, *args3))
    boot = {
        k: {m: np.concatenate([c[m] for c in v]) for m in v[0]} for k, v in boot.items()
    }
    out: dict = {
        "n": len(y),
        "n_real": int((y == 0).sum()),
        "n_ai": int((y == 1).sum()),
        "n_groups": len(set(groups)),
    }
    for key in ("A", "B"):
        out[key] = {m: _num(point[key][m][0]) for m in (*METRICS, "uncertain_count")}
        out[key]["uncertain_count"] = round(point[key]["uncertain_count"][0])
    out["paired_A_minus_B"] = {}
    for m in (*METRICS, "uncertain_count"):
        delta = point["A"][m][0] - point["B"][m][0]
        diff = boot["A"][m] - boot["B"][m]
        ci = None
        if np.isfinite(diff).all() and len(set(groups)) >= 2:
            ci = [float(v) for v in np.percentile(diff, [2.5, 97.5])]
        out["paired_A_minus_B"][m] = {"delta": _num(delta), "ci95": ci}
    return out


def compare(a: dict, b: dict, args) -> dict:
    ids = align(a, b)
    y = np.array([a[s]["label"] for s in ids])
    pa = np.array([a[s]["score"] for s in ids])
    pb = np.array([b[s]["score"] for s in ids])
    groups = [a[s]["group_id"] for s in ids]
    sources = np.array([a[s]["source"] for s in ids])
    if TOTAL_SLICE in set(sources):
        raise ValueError(
            f"source không được đặt tên {TOTAL_SLICE!r} (dành cho slice tổng)"
        )
    slices = {TOTAL_SLICE: np.ones(len(ids), dtype=bool)}
    for src in sorted(set(sources)):
        if src != NO_SOURCE:
            slices[src] = sources == src
    return {
        "slices": {
            name: compare_slice(
                y[m], pa[m], pb[m], [g for g, k in zip(groups, m) if k], args
            )
            for name, m in slices.items()
        }
    }


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="So sánh hai file điểm trên cùng ảnh (ADV-12)"
    )
    ap.add_argument("--a", type=Path, required=True, help="điểm model A (e571)")
    ap.add_argument("--b", type=Path, required=True, help="điểm model B (ứng viên)")
    ap.add_argument("--low", type=float, default=0.3)
    ap.add_argument("--binary", type=float, default=0.5)
    ap.add_argument("--high", type=float, default=0.7)
    ap.add_argument("--replicates", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", type=Path, help="ghi JSON; mặc định in ra màn hình")
    args = ap.parse_args(argv)
    if (
        not (0 <= args.low < args.high <= 1 and 0 < args.binary < 1)
        or args.replicates < 1
    ):
        print("LỖI: ngưỡng hoặc số replicate không hợp lệ", file=sys.stderr)
        return 2
    try:
        report = compare(read_scores(args.a), read_scores(args.b), args)
    except ValueError as exc:
        print(f"LỖI: {exc}", file=sys.stderr)
        return 2
    report = {
        "inputs": {
            "a_sha256": sha256_file(args.a),
            "b_sha256": sha256_file(args.b),
            "thresholds": {"low": args.low, "binary": args.binary, "high": args.high},
            "replicates": args.replicates,
            "seed": args.seed,
        },
        **report,
        "note": "Công cụ phát triển ADV-12: không chọn ngưỡng hay model trên test; kết quả không thay QA độc lập.",
    }
    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.output:
        try:
            args.output.write_text(text + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"LỖI: không ghi được {args.output}: {exc}", file=sys.stderr)
            return 2
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
