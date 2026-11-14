"""Kiểm tra rò rỉ metadata: đoán thật/AI chỉ từ metadata ảnh (T007, bản nháp).

Probe đọc metadata hình ảnh (định dạng, kích thước, mode, EXIF, ICC, bảng lượng tử và
subsampling JPEG); không dùng đường dẫn hay nguồn. Chạy trên ảnh gốc (chẩn đoán) và ảnh
đã chuẩn hóa:
    A_eff = max(AUROC, 1 - AUROC) <= 0.55 với mọi slice hợp lệ.
Ảnh đã chuẩn hóa có metadata hằng số theo thiết kế (A_eff = 0.5 "rỗng"), nên probe post
thêm đặc trưng tầng pixel (PIXEL_FEATURES, D03 proposed): dung lượng JPEG trên mỗi pixel,
dấu khối 8×8, năng lượng tần số cao và nhiễu dư của kênh sáng.
Chính sách 2026-11-12: script này CHỈ CẢNH BÁO khi A_eff vượt ngưỡng (thoát 0); lỗi
dữ liệu (slice không hợp lệ, A_eff NaN, control sai) thoát 1. Việc chặn release là của
scripts/check_release_audit.py đọc báo cáo JSON này.

Probe, protocol và cỡ mẫu tối thiểu (D03/D04) chưa chốt; giá trị dưới đây là tạm.

Cách chạy (từ thư mục gốc repo, sau prepare_data.py):
    python scripts/metadata_audit.py
"""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, JpegImagePlugin
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

LABELS_CSV = Path("data/labels.csv")
OUT_JSON = Path("data/metadata_audit.json")
MAX_A_EFF = 0.55
MIN_PER_CLASS = 100  # tạm, chờ D04
N_BOOT = 1000
SEED = 42
CATEGORICAL = ["format", "mode"]
EXIF_MAKE, EXIF_MODEL = 271, 272
# Khóa do extract() trả về (test_metadata_audit khóa hai bên khớp nhau); release checker dùng
# để suy ra số đặc trưng khi báo cáo cũ thiếu "n_features".
FEATURES = (
    "format", "mode", "width", "height", "aspect", "has_exif", "has_make", "has_model",
    "has_icc", "progressive", "subsampling", "q_luma_mean", "q_chroma_mean",
)  # fmt: skip
PIXEL_FEATURES = ("bytes_per_px", "blockiness", "hf_energy", "noise_std")
BLOCK = 8  # cạnh khối DCT của JPEG
HF_CUTOFF = 0.25  # chu kỳ/pixel; nửa trên của dải tần (Nyquist 0.5)


def extract(path: str) -> dict:
    """Metadata đọc từ bytes ảnh; trường không áp dụng (vd. PNG) để NaN."""
    with Image.open(path) as im:
        q = getattr(im, "quantization", None) or {}
        exif = im.getexif()
        is_jpeg = im.format == "JPEG"
        return {
            "format": im.format,
            "mode": im.mode,
            "width": im.width,
            "height": im.height,
            "aspect": im.width / im.height,
            "has_exif": int(len(exif) > 0),
            "has_make": int(EXIF_MAKE in exif),
            "has_model": int(EXIF_MODEL in exif),
            "has_icc": int("icc_profile" in im.info),
            "progressive": int(bool(im.info.get("progressive"))),
            "subsampling": JpegImagePlugin.get_sampling(im) if is_jpeg else np.nan,
            "q_luma_mean": np.mean(q[0]) if 0 in q else np.nan,
            "q_chroma_mean": np.mean(q[1]) if 1 in q else np.nan,
        }


def _blockiness(y: np.ndarray) -> float:
    """Chênh lệch sáng trung bình qua biên khối 8×8 chia cho trong khối (1 = không có dấu khối)."""
    edge, inner = [], []
    for d in (np.abs(np.diff(y, axis=1)), np.abs(np.diff(y, axis=0)).T):
        at = np.arange(1, d.shape[1] + 1) % BLOCK == 0  # cột j so pixel j với j + 1
        edge.append(d[:, at].ravel())
        inner.append(d[:, ~at].ravel())
    e, i = np.concatenate(edge), np.concatenate(inner)
    if not e.size or not i.size:
        return np.nan
    return float((e.mean() + 1e-6) / (i.mean() + 1e-6))


def pixel_features(path: str) -> dict:
    """Đặc trưng tầng pixel của ảnh (dùng cho ảnh đã chuẩn hóa, nơi metadata là hằng số)."""
    with Image.open(path) as im:
        y = np.asarray(im.convert("L"), dtype=np.float64)
    power = np.abs(np.fft.fft2(y - y.mean())) ** 2
    fy, fx = np.meshgrid(*(np.abs(np.fft.fftfreq(n)) for n in y.shape), indexing="ij")
    total = power.sum()
    laplacian = (
        4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:]
    )
    return {
        "bytes_per_px": Path(path).stat().st_size / y.size,
        "blockiness": _blockiness(y),
        "hf_energy": float(power[np.maximum(fy, fx) > HF_CUTOFF].sum() / total)
        if total > 0
        else 0.0,
        "noise_std": float(laplacian.std()) if laplacian.size else np.nan,
    }


def a_eff(y: np.ndarray, p: np.ndarray) -> float:
    a = roc_auc_score(y, p)
    return max(a, 1 - a)


def evaluate(x: pd.DataFrame, y: pd.Series, split: pd.Series) -> dict:
    """Fit probe trên train, đo A_eff trên test kèm CI bootstrap 95%."""
    tr, te = split == "train", split == "test"
    counts = y[te].value_counts().to_dict()
    if min(counts.get(0, 0), counts.get(1, 0)) < MIN_PER_CLASS:
        return {"valid": False, "test_counts": counts}
    probe = HistGradientBoostingClassifier(
        categorical_features="from_dtype", random_state=SEED
    )
    probe.fit(x[tr], y[tr])
    yt, pt = y[te].to_numpy(), probe.predict_proba(x[te])[:, 1]
    rng = np.random.default_rng(SEED)
    boots = []
    while len(boots) < N_BOOT:
        i = rng.integers(0, len(yt), len(yt))
        if len(set(yt[i])) == 2:
            boots.append(a_eff(yt[i], pt[i]))
    return {
        "valid": True,
        "test_counts": counts,
        "a_eff": round(a_eff(yt, pt), 4),
        "ci95": [round(float(v), 4) for v in np.percentile(boots, [2.5, 97.5])],
    }


def slices(g: pd.DataFrame) -> dict[str, pd.Index]:
    """Tất cả ảnh, và ảnh thật so riêng với từng nguồn AI (khi có nhiều nguồn)."""
    real = g["label"] == 0
    ai_sources = sorted(g.loc[~real, "source"].unique())
    out = {"all": g.index}
    if len(ai_sources) > 1:
        for src in ai_sources:
            out[f"real_vs_{src.split('_', 1)[1]}"] = g.index[
                real | (g["source"] == src)
            ]
    return out


def controls(
    post: pd.DataFrame, raw: pd.DataFrame, y: pd.Series, split: pd.Series
) -> dict:
    """Kiểm tra probe: phải bắt được feature lộ nhãn và không bắt nhãn ngẫu nhiên.

    Control âm chạy trên raw vì feature post đều hằng số, sẽ luôn ra 0.5.
    """
    positive = evaluate(post.assign(control=y), y, split)
    shuffled = pd.Series(np.random.default_rng(SEED).permutation(y), index=y.index)
    negative = evaluate(raw, shuffled, split)
    return {
        "positive": positive,
        "negative": negative,
        "ok": positive.get("a_eff", 0) >= 0.95
        and negative.get("a_eff", 1) <= MAX_A_EFF,
    }


def main() -> None:
    df = pd.read_csv(LABELS_CSV)
    views = {}
    for view, col in (("raw", "raw_path"), ("post", "filepath")):
        rows = [
            extract(p) | (pixel_features(p) if view == "post" else {}) for p in df[col]
        ]
        x = pd.DataFrame(rows, index=df.index)
        views[view] = x.astype({c: "category" for c in CATEGORICAL})

    report, passed, errors, warnings = {}, True, [], []
    for dataset, g in df.groupby(df["source"].str.split("_").str[0]):
        r = {
            "n_features": views["post"].shape[1],
            "constant_features": {},
            "slices": {},
        }
        for view, x in views.items():
            xg = x.loc[g.index]
            r["constant_features"][view] = [
                c for c in xg if xg[c].nunique(dropna=False) <= 1
            ]
            for name, idx in slices(g).items():
                res = evaluate(xg.loc[idx], g.loc[idx, "label"], g.loc[idx, "split"])
                r["slices"].setdefault(name, {})[view] = res
                if view == "post" and not (res["valid"] and res["a_eff"] <= MAX_A_EFF):
                    passed = False
                    if not res["valid"] or math.isnan(res["a_eff"]):
                        errors.append(
                            f"{dataset}/{name}: slice post không hợp lệ hoặc NaN"
                        )
                    else:
                        warnings.append(f"{dataset}/{name}: A_eff {res['a_eff']}")
        r["controls"] = controls(
            views["post"].loc[g.index],
            views["raw"].loc[g.index],
            g["label"],
            g["split"],
        )
        passed &= r["controls"]["ok"]
        if not r["controls"]["ok"]:
            errors.append(f"{dataset}: control dương/âm không hợp lệ")
        report[dataset] = r
    report["gate"] = {"max_a_eff": MAX_A_EFF, "passed": passed}
    OUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"Đã ghi {OUT_JSON}\n")
    print("| Bộ | Slice | Raw A_eff | Post A_eff (CI 95%) |")
    print("|---|---|---|---|")
    for dataset, r in report.items():
        if dataset == "gate":
            continue
        for name, v in r["slices"].items():
            raw, post = v["raw"], v["post"]
            raw_s = raw["a_eff"] if raw["valid"] else "không hợp lệ"
            post_s = (
                f"{post['a_eff']} {post['ci95']}" if post["valid"] else "không hợp lệ"
            )
            print(f"| {dataset} | {name} | {raw_s} | {post_s} |")
        c = r["controls"]
        print(
            f"| {dataset} | controls (+/-) | | {c['positive'].get('a_eff')} / {c['negative'].get('a_eff')} |"
        )
        print(
            f"\n{dataset} – feature hằng số sau chuẩn hóa: {r['constant_features']['post']}\n"
        )
    print(f"Post A_eff <= {MAX_A_EFF}: {'ĐẠT' if passed else 'KHÔNG ĐẠT'}")
    for w in warnings:
        print(f"CẢNH BÁO (release checker sẽ chặn): {w} > {MAX_A_EFF}")
    for e in errors:
        print(f"LỖI: {e}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
