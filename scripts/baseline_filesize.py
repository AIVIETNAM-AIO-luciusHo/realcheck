"""Baseline chỉ dùng dung lượng file để đoán thật/AI (D4).

Nếu baseline trên ảnh đã chuẩn hóa cao hơn hẳn 50% thì định dạng file vẫn
lộ nhãn và phải làm lại bước chuẩn hóa. Chạy trên cả ảnh gốc để so sánh, và
so riêng ảnh thật với từng công cụ AI để biết nguồn nào lộ nhãn.

Dùng balanced accuracy (đoán mò = 50% kể cả khi hai lớp lệch số lượng).

Cách chạy (từ thư mục gốc repo, sau prepare_data.py):
    python scripts/baseline_filesize.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score
from sklearn.tree import DecisionTreeClassifier

LABELS_CSV = Path("data/labels.csv")
OUT_JSON = Path("data/baseline_filesize.json")
WARN_ACC = 0.60  # ngưỡng cảnh báo tạm, kế hoạch chưa ấn định


def evaluate(df: pd.DataFrame, kb_col: str) -> dict:
    """Train trên split train, báo balanced accuracy trên val và test."""
    x = np.log(df[[kb_col]].to_numpy())
    y = df["label"].to_numpy()
    tr, va, te = ((df["split"] == s).to_numpy() for s in ("train", "val", "test"))
    models = {
        "logreg": LogisticRegression(class_weight="balanced"),
        # Cây nông bắt được quan hệ không đơn điệu (vd. AI vừa quá nhỏ vừa quá lớn)
        "tree_depth3": DecisionTreeClassifier(
            max_depth=3, class_weight="balanced", random_state=42
        ),
    }
    out = {}
    for name, m in models.items():
        m.fit(x[tr], y[tr])
        out[name] = {
            "val_acc": round(balanced_accuracy_score(y[va], m.predict(x[va])), 4),
            "test_acc": round(balanced_accuracy_score(y[te], m.predict(x[te])), 4),
        }
    return out


def raw_stats(df: pd.DataFrame) -> dict:
    """Định dạng và kích thước ảnh gốc theo nguồn, để thấy thiên lệch ban đầu."""
    stats = {}
    for source, g in df.groupby("source"):
        fmts, sides = [], []
        for p in g["raw_path"]:
            with Image.open(p) as im:
                fmts.append(im.format)
                sides.append(min(im.size))
        stats[source] = {
            "formats": pd.Series(fmts).value_counts().to_dict(),
            "median_short_side": int(np.median(sides)),
            "median_kb": round(g["raw_kb"].median(), 1),
        }
    return stats


def comparisons(g: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Tất cả ảnh, và ảnh thật so riêng với từng nguồn AI (khi có nhiều nguồn)."""
    real = g["label"] == 0
    ai_sources = sorted(g.loc[~real, "source"].unique())
    out = {"all": g}
    if len(ai_sources) > 1:
        for src in ai_sources:
            out[f"real_vs_{src.split('_', 1)[1]}"] = g[real | (g["source"] == src)]
    return out


def main() -> None:
    df = pd.read_csv(LABELS_CSV)
    for kind, col in (("raw", "raw_path"), ("processed", "filepath")):
        df[f"{kind}_kb"] = df[col].map(lambda p: Path(p).stat().st_size / 1024)

    results = {}
    for dataset, g in df.groupby(df["source"].str.split("_").str[0]):
        results[dataset] = {
            "n": g["split"].value_counts().to_dict(),
            "baseline": {
                name: {kind: evaluate(c, f"{kind}_kb") for kind in ("raw", "processed")}
                for name, c in comparisons(g).items()
            },
            "raw_stats": raw_stats(g),
        }
    OUT_JSON.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print(f"Đã ghi {OUT_JSON}\n")
    print("Balanced accuracy trên test (50% = đoán mò)\n")
    print("| Bộ | So sánh | Mô hình | Ảnh gốc | Đã chuẩn hóa |")
    print("|---|---|---|---|---|")
    for dataset, r in results.items():
        for name, kinds in r["baseline"].items():
            for model in kinds["raw"]:
                raw = kinds["raw"][model]["test_acc"]
                proc = kinds["processed"][model]["test_acc"]
                flag = " ⚠" if proc > WARN_ACC else ""
                print(f"| {dataset} | {name} | {model} | {raw} | {proc}{flag} |")


if __name__ == "__main__":
    main()
