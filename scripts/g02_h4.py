"""Bộ chạy H4 (bước 0 đến 5 của docs/g02-h4-protocol.md): NHÁP, chỉ chạy trên dữ liệu tổng hợp.

Chưa chạy dữ liệu thật: H4 còn là nháp chờ Lực khóa. `main` từ chối mọi thứ khác `--synthetic`.
Lõi nhận DataFrame đặc trưng và hook đọc ảnh, nên không tự đọc ảnh thật; khi Lực khóa, chỉ
cần nối hook (load = mở ảnh gốc, normalize = lambda im: models.normalize.normalize_image(im).jpeg)
và các số khóa (mức nén, số hoán vị) vào `Params`.

Cột của bảng đặc trưng: id, group_id, label, split (train|validation|test), source
(vd. genimage_glide) và 4 cột PIXEL_FEATURES. Bước 2 đến 4 chỉ dùng train và validation.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from scripts.metadata_audit import MIN_PER_CLASS, PIXEL_FEATURES, SEED, pixel_features

NULL_P99_MAX = 0.60  # mục 3: lát cắt hợp lệ khi null p99 <= 0,60
MIN_VALID_SLICES = 3
DHASH_MAX = 4
FIT_SPLITS = ("train", "validation")  # test không bao giờ vào bước 2 đến 4


@dataclass(frozen=True)
class Params:
    n_perm: int = 1000
    n_boot: int = 2000
    seed: int = SEED
    levels: tuple[int, int, int] = (
        90,
        70,
        40,
    )  # d1 < d2 < d3 theo độ mạnh; Lực chọn, ở đây chỉ để thử
    tol: float = -0.02  # ĐỀ XUẤT, Lực chốt (bước 4 ii)
    min_per_class: int = MIN_PER_CLASS


def a_eff(y, p) -> float:
    a = roc_auc_score(y, p)
    return float(max(a, 1 - a))


def _probe_scores(x_tr, y_tr, x_va) -> np.ndarray:
    probe = HistGradientBoostingClassifier(random_state=SEED)
    probe.fit(x_tr, y_tr)
    return probe.predict_proba(x_va)[:, 1]


def fit_eval(df: pd.DataFrame, label: str = "label") -> tuple[float, np.ndarray]:
    """Fit trên train, đo A_eff trên validation. Trả (A_eff, điểm trên validation)."""
    tr, va = df[df.split == "train"], df[df.split == "validation"]
    p = _probe_scores(tr[list(PIXEL_FEATURES)], tr[label], va[list(PIXEL_FEATURES)])
    return a_eff(va[label], p), p


def counts(df: pd.DataFrame, label: str = "label") -> dict[int, int]:
    va = df[df.split == "validation"][label].value_counts()
    return {0: int(va.get(0, 0)), 1: int(va.get(1, 0))}


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- Bước 0 ---
def step0_reproduce(report_path: str | Path, expected_sha: str) -> dict:
    """Tái lập = SHA256 trùng từng byte; khác thì dừng, không dung sai."""
    got = sha256_file(report_path)
    return {"sha256": got, "expected": expected_sha, "reproduced": got == expected_sha}


# --- Bước 1 ---
def step1_lock(labels_csv: str | Path, df: pd.DataFrame, params: Params) -> dict:
    """Khóa đầu vào: hash labels, số ảnh mỗi lớp mỗi lát cắt trong validation, tham số."""
    return {
        "labels_sha256": sha256_file(labels_csv),
        "params": {**params.__dict__, "levels": list(params.levels)},
        "slice_counts": {n: counts(s) for n, s in real_slices(df).items()}
        | {n: counts(s) for n, s in pseudo_slices(df).items()},
    }


# --- Lát cắt ---
def _dataset(df: pd.DataFrame) -> pd.Series:
    return df["source"].str.split("_").str[0]


def real_slices(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """5 lát cắt thật: GenImage gộp, real vs từng nguồn AI, CIFAKE."""
    df = df[df.split.isin(FIT_SPLITS)]
    g = df[_dataset(df) == "genimage"]
    out = {"genimage_all": g}
    for src in sorted(g.loc[g.label == 1, "source"].unique()):
        out[f"real_vs_{src.split('_', 1)[1]}"] = g[(g.label == 0) | (g.source == src)]
    out["cifake"] = df[_dataset(df) == "cifake"]
    return out


def pseudo_slices(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Ba lát cắt giả khóa trước: G1 ảnh thật GenImage, G2 AI GenImage gộp, G3 CIFAKE gộp."""
    df = df[df.split.isin(FIT_SPLITS)]
    ds = _dataset(df)
    return {
        "G1": df[(ds == "genimage") & (df.label == 0)],
        "G2": df[(ds == "genimage") & (df.label == 1)],
        "G3": df[ds == "cifake"],
    }


def valid_slice(
    s: pd.DataFrame, null_p99: float, params: Params, label: str = "label"
) -> bool:
    c = counts(s, label)
    return min(c.values()) >= params.min_per_class and null_p99 <= NULL_P99_MAX


# --- Bước 2 ---
def permute_by_group(df: pd.DataFrame, rng, label: str = "label") -> pd.Series:
    """Hoán vị nhãn theo group (train và validation cùng lúc); mỗi group một nhãn."""
    first = df.groupby("group_id")[label].first()
    perm = pd.Series(rng.permutation(first.to_numpy()), index=first.index)
    return df["group_id"].map(perm)


def null_distribution(s: pd.DataFrame, params: Params, label: str = "label") -> dict:
    rng = np.random.default_rng(params.seed)
    t = s.assign(_perm=0)
    vals = []
    for _ in range(params.n_perm):
        t["_perm"] = permute_by_group(s, rng, label)
        if t.loc[t.split == "validation", "_perm"].nunique() < 2:
            continue
        vals.append(fit_eval(t, "_perm")[0])
    return {
        "n_perm": len(vals),
        "p95": round(float(np.percentile(vals, 95)), 4),
        "p99": round(float(np.percentile(vals, 99)), 4),
    }


def step2_null(
    slices: dict[str, pd.DataFrame], params: Params, label: str = "label"
) -> dict:
    return {n: null_distribution(s, params, label) for n, s in slices.items()}


# --- Bước 3 ---
def assign_halves(s: pd.DataFrame, rng) -> pd.Series:
    """Chia group thành hai nửa giả (0/1) cân theo số ảnh; nhãn giả gán cả train lẫn validation."""
    sizes = s.groupby("group_id").size()
    order = rng.permutation(len(sizes))
    load, half = [0, 0], {}
    for i in order:
        g = sizes.index[i]
        k = 0 if load[0] <= load[1] else 1
        half[g] = k
        load[k] += int(sizes.iloc[i])
    return s["group_id"].map(half)


def label_halves(
    pseudo: dict[str, pd.DataFrame], params: Params
) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(params.seed + 1)
    return {n: s.assign(pseudo=assign_halves(s, rng)) for n, s in pseudo.items()}


def step3_negative(
    labelled: dict[str, pd.DataFrame], nulls: dict, params: Params
) -> dict:
    """Control âm: A_eff của nhãn giả so với p99 của null (hoán vị nhãn giả) của chính lát cắt."""
    res = {}
    for name, t in labelled.items():
        a, _ = fit_eval(t, "pseudo")
        p99 = nulls[name]["p99"]
        res[name] = {
            "counts": counts(t, "pseudo"),
            "a_eff": round(a, 4),
            "null_p99": p99,
            "valid": valid_slice(t, p99, params, "pseudo"),
            "ok": a <= p99,
        }
    return res


# --- Bước 4 ---
def recompress(img: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=q)
    return Image.open(io.BytesIO(buf.getvalue())).convert("RGB")


def features_from_bytes(data: bytes) -> dict:
    """Dùng đúng pixel_features của probe gốc (qua tệp tạm) để không lệch công thức."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.jpg"
        p.write_bytes(data)
        return pixel_features(str(p))


def compressed_features(
    load: Callable,
    normalize: Callable[[Image.Image], bytes],
    image_id,
    q: int,
    phase: str,
) -> dict:
    """P1: nén ảnh gốc, rồi chuẩn hóa thật. P2: chuẩn hóa rồi nén (tệp cuối là JPEG nén)."""
    img = load(image_id)
    if phase == "P1":
        return features_from_bytes(normalize(recompress(img, q)))
    norm = Image.open(io.BytesIO(normalize(img))).convert("RGB")
    buf = io.BytesIO()
    norm.save(buf, "JPEG", quality=q)
    return features_from_bytes(buf.getvalue())


def cluster_bootstrap(
    y, groups, scores: list[np.ndarray], n_boot: int, seed: int
) -> np.ndarray:
    """Bootstrap theo group, ghép cặp: cùng mẫu group cho mọi điều kiện. Trả mảng (n_boot, n_điều_kiện)."""
    rng = np.random.default_rng(seed)
    idx = (
        pd.Series(np.arange(len(y)))
        .groupby(np.asarray(groups))
        .apply(np.array)
        .tolist()
    )
    out = []
    while len(out) < n_boot:
        pick = np.concatenate([idx[i] for i in rng.integers(0, len(idx), len(idx))])
        if len(set(y[pick])) < 2:
            continue
        out.append([a_eff(y[pick], p[pick]) for p in scores])
    return np.array(out)


def step4_positive(
    labelled: dict[str, pd.DataFrame],
    load: Callable,
    normalize: Callable,
    params: Params,
    phase: str = "P1",
) -> dict:
    """Nén nửa giả "B" (pseudo == 1) ở ba mức; Δ so với nền bước 3, CI 95% bootstrap ghép cặp."""
    res = {}
    for name, t in labelled.items():
        _, base = fit_eval(t, "pseudo")
        va = t[t.split == "validation"]
        y, groups = va["pseudo"].to_numpy(), va["group_id"].to_numpy()
        scores = [base]
        for q in params.levels:
            u = t.copy()
            b = u["pseudo"] == 1
            feats = pd.DataFrame(
                [
                    compressed_features(load, normalize, i, q, phase)
                    for i in u.loc[b, "id"]
                ],
                index=u.index[b],
            )
            u.loc[b, list(PIXEL_FEATURES)] = feats[list(PIXEL_FEATURES)]
            scores.append(fit_eval(u, "pseudo")[1])
        boots = cluster_bootstrap(y, groups, scores, params.n_boot, params.seed)
        delta = boots[:, 1:] - boots[:, [0]]  # Δ(d1..d3)
        lo = lambda v: float(np.percentile(v, 2.5))
        steps = [delta[:, k + 1] - delta[:, k] for k in (0, 1)]
        i_ok = lo(delta[:, 2]) > 0
        ii_ok = all(lo(s) >= params.tol for s in steps)
        res[name] = {
            "phase": phase,
            "delta_point": [
                round(a_eff(y, scores[k + 1]) - a_eff(y, scores[0]), 4)
                for k in range(3)
            ],
            "delta_d3_ci_low": round(lo(delta[:, 2]), 4),
            "step_ci_low": [round(lo(s), 4) for s in steps],
            "i_ok": bool(i_ok),
            "ii_ok": bool(ii_ok),
            "ok": bool(i_ok and ii_ok),
        }
    return res


# --- Bước 5 ---
def dhash(img: Image.Image) -> int:
    g = np.asarray(
        img.convert("L").resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16
    )
    bits = (g[:, 1:] > g[:, :-1]).ravel()
    return int("".join("1" if b else "0" for b in bits), 2)


def near_duplicate_groups(df: pd.DataFrame, hashes: dict, thr: int = DHASH_MAX) -> dict:
    """Cặp ảnh khác split có dHash <= thr. Test được dùng ở đây, và chỉ ở đây, để phát hiện trùng."""
    ids = df["id"].tolist()
    split = dict(zip(df["id"], df["split"], strict=True))
    group = dict(zip(df["id"], df["group_id"], strict=True))
    pairs, bad = [], set()
    for a in range(len(ids)):
        for b in range(a + 1, len(ids)):
            i, j = ids[a], ids[b]
            if split[i] != split[j] and (hashes[i] ^ hashes[j]).bit_count() <= thr:
                pairs.append((i, j))
                bad |= {group[i], group[j]}
    return {"n_pairs": len(pairs), "pairs": pairs, "groups": sorted(bad)}


def nearest_feature_distance(df: pd.DataFrame) -> float:
    """Khoảng cách gần nhất validation-train trong 4 đặc trưng chuẩn hóa. Chỉ báo, không ngưỡng."""
    tr, va = df[df.split == "train"], df[df.split == "validation"]
    cols = list(PIXEL_FEATURES)
    sd = tr[cols].std(ddof=0).replace(0, 1)
    a, b = (tr[cols] / sd).to_numpy(), (va[cols] / sd).to_numpy()
    d = np.sqrt(((b[:, None, :] - a[None, :, :]) ** 2).sum(-1)).min(1)
    return round(float(np.median(d)), 4)


def step5_neardup(df: pd.DataFrame, load: Callable, normalize: Callable) -> dict:
    hashes = {i: dhash(Image.open(io.BytesIO(normalize(load(i))))) for i in df["id"]}
    r = near_duplicate_groups(df, hashes)
    r["feature_nn_median"] = nearest_feature_distance(df)
    r["outcome"] = (
        "rò rỉ gần-trùng" if r["n_pairs"] else "không thấy gần-trùng bằng dHash"
    )
    return r


# --- Tổng hợp ---
def verdict(neg: dict, pos: dict, n_valid: int) -> str:
    if n_valid < MIN_VALID_SLICES:
        return "Không đủ sức"
    if not all(v["ok"] for v in neg.values() if v["valid"]):
        return "Âm hỏng"
    if not all(v["ok"] for v in pos.values()):
        return "Dương hỏng"
    return "Âm đạt, dương đạt"


def run_steps_2_to_4(df, load, normalize, params: Params) -> dict:
    real, pseudo = real_slices(df), pseudo_slices(df)
    labelled = label_halves(pseudo, params)
    nulls = step2_null(real, params) | step2_null(labelled, params, "pseudo")
    neg = step3_negative(labelled, nulls, params)
    valid = {k: v for k, v in labelled.items() if neg[k]["valid"]}
    pos = {
        ph: step4_positive(valid, load, normalize, params, ph) for ph in ("P1", "P2")
    }
    n_valid = len(valid)
    return {
        "null": nulls,
        "negative": neg,
        "positive": pos,
        "n_valid_slices": n_valid,
        "verdict": verdict(neg, pos["P1"], n_valid),  # kết luận dùng P1
    }


def run(df: pd.DataFrame, load: Callable, normalize: Callable, params: Params) -> dict:
    """Bước 2 đến 5; có trùng gần xuyên split thì loại group và lặp bước 2 đến 4 đúng một lần."""
    out = {"first": run_steps_2_to_4(df, load, normalize, params)}
    out["step5"] = step5_neardup(df, load, normalize)
    if out["step5"]["n_pairs"]:
        keep = df[~df["group_id"].isin(out["step5"]["groups"])]
        out["after_removal"] = run_steps_2_to_4(keep, load, normalize, params)
    return out


# --- Dữ liệu tổng hợp ---
def synthetic(n_groups: int = 60, seed: int = 0):
    """Ảnh và bảng đặc trưng tổng hợp (không phải dữ liệu thật). Trả (df, load, normalize)."""
    rng = np.random.default_rng(seed)
    imgs, rows = {}, []

    def make(noise):
        a = rng.normal(128, noise, (48, 48, 3)).clip(0, 255).astype(np.uint8)
        return Image.fromarray(a)

    def norm(im):
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=95)
        return buf.getvalue()

    for ds, label, src in (
        ("genimage", 0, "real"),
        ("genimage", 1, "glide"),
        ("cifake", 0, "real"),
        ("cifake", 1, "fake"),
    ):
        for g in range(n_groups):
            gid = f"{ds}-{src}-{g}"
            split = ("train", "train", "validation")[g % 3]
            for k in range(2):
                i = f"{gid}-{k}"
                imgs[i] = make(20)  # cùng phân phối, không có tín hiệu thật
                feats = features_from_bytes(norm(imgs[i]))
                rows.append(
                    {
                        "id": i,
                        "group_id": gid,
                        "label": label,
                        "split": split,
                        "source": f"{ds}_{src}",
                    }
                    | feats
                )
    return pd.DataFrame(rows), imgs.__getitem__, norm


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--synthetic",
        action="store_true",
        help="chạy thử trên dữ liệu tổng hợp (cách duy nhất hiện có)",
    )
    ap.add_argument("--n-perm", type=int, default=20)
    ap.add_argument("--n-boot", type=int, default=200)
    a = ap.parse_args(argv)
    if not a.synthetic:
        print(
            "H4 chưa được Lực khóa: bộ chạy chỉ cho phép --synthetic.", file=sys.stderr
        )
        return 2
    df, load, norm = synthetic()
    p = Params(n_perm=a.n_perm, n_boot=a.n_boot, min_per_class=20)
    print(json.dumps(run(df, load, norm, p), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
