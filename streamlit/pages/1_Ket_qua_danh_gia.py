"""Trang Kết quả đánh giá: chỉ đọc tệp báo cáo, không chạy suy luận và không có số mẫu."""

import json
import os
from pathlib import Path

import altair as alt
import pandas as pd

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = Path(
    os.environ.get("REALCHECK_EVAL_REPORT", REPO_ROOT / "artifacts" / "evaluation.json")
)
LABELS_CSV = REPO_ROOT / "data" / "labels.csv"
AUDIT_JSON = REPO_ROOT / "data" / "metadata_audit.json"

ACCURACY_TARGET = 0.90
LABELS = ["Ảnh thật", "Ảnh AI"]
RATE_FIELDS = ("accuracy", "precision", "recall", "decided_accuracy")
SOURCE_NAMES = {
    "genimage_real": "Ảnh thật (ImageNet)",
    "genimage_sd14": "Stable Diffusion v1.4",
    "genimage_midjourney": "Midjourney",
    "genimage_glide": "GLIDE",
}
AUDIT_SLICES = {
    "all": "Tất cả nguồn",
    "real_vs_sd14": "Thật so với SD v1.4",
    "real_vs_midjourney": "Thật so với Midjourney",
    "real_vs_glide": "Thật so với GLIDE",
}


def is_rate(value: object) -> bool:
    return type(value) in (int, float) and 0 <= value <= 1


def is_count(value: object) -> bool:
    return type(value) is int and value >= 0


def valid_group(g: object) -> bool:
    """Số đo của một nhóm ảnh trong bảng: tên, N, accuracy, số ảnh Chưa chắc."""
    return (
        isinstance(g, dict)
        and isinstance(g.get("name"), str)
        and is_count(g.get("n"))
        and g["n"] > 0
        and is_rate(g.get("accuracy"))
        and is_count(g.get("uncertain_n"))
        and g["uncertain_n"] <= g["n"]
    )


def valid_metrics(m: object) -> bool:
    """Số đo hợp lệ: tỷ lệ trong [0, 1] và các số đếm khớp với N."""
    if not isinstance(m, dict) or not is_count(m.get("n")) or m["n"] == 0:
        return False
    cm = m.get("confusion_matrix")
    cm_ok = (
        isinstance(cm, list)
        and len(cm) == 2
        and all(isinstance(row, list) and len(row) == 2 for row in cm)
        and all(is_count(v) for row in cm for v in row)
        and sum(map(sum, cm)) == m["n"]
    )
    uncertain_ok = is_count(m.get("uncertain_n")) and m["uncertain_n"] <= m["n"]
    return cm_ok and uncertain_ok and all(is_rate(m.get(f)) for f in RATE_FIELDS)


def valid_report(r: object) -> bool:
    if not isinstance(r, dict):
        return False
    versions = [r.get(k) for k in ("dataset", "model", "profile")]
    versions_ok = all(
        isinstance(v, dict)
        and isinstance(v.get("version"), str)
        and isinstance(v.get("hash"), str)
        for v in versions
    )
    th = r.get("thresholds")
    thresholds_ok = isinstance(th, dict) and all(
        is_rate(th.get(k)) for k in ("binary", "low", "high")
    )
    groups_ok = all(
        isinstance(r.get(key, []), list) and all(map(valid_group, r.get(key, [])))
        for key in ("by_source", "ood")
    )
    return versions_ok and thresholds_ok and valid_metrics(r.get("test")) and groups_ok


def load_report() -> dict | None:
    """Đọc báo cáo; ném ValueError nếu tệp có nhưng sai định dạng."""
    if not REPORT_PATH.is_file():
        return None
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if not valid_report(report):
        raise ValueError("sai định dạng")
    return report


def percent(rate: float) -> str:
    return f"{rate:.1%}"


def count(n: int) -> str:
    """Số đếm theo cách viết của báo cáo nhóm, ví dụ 3.000."""
    return f"{n:,}".replace(",", ".")


def show_confusion_matrix(cm: list[list[int]]) -> None:
    cells = pd.DataFrame(
        [
            {"Thực tế": LABELS[i], "Dự đoán": LABELS[j], "Số ảnh": cm[i][j]}
            for i in range(2)
            for j in range(2)
        ]
    )
    gap = alt.Scale(paddingInner=0.02)
    base = alt.Chart(cells).encode(
        x=alt.X(
            "Dự đoán:N",
            sort=LABELS,
            scale=gap,
            axis=alt.Axis(labelAngle=0, orient="top"),
        ),
        y=alt.Y("Thực tế:N", sort=LABELS, scale=gap),
    )
    heat = base.mark_rect(cornerRadius=4).encode(
        color=alt.Color(
            "Số ảnh:Q",
            scale=alt.Scale(range=["#cde2fb", "#104281"], domainMin=0),
            legend=None,
        ),
        tooltip=["Thực tế:N", "Dự đoán:N", "Số ảnh:Q"],
    )
    threshold = cells["Số ảnh"].max() / 2
    text = base.mark_text(fontSize=18, fontWeight="bold").encode(
        text="Số ảnh:Q",
        color=alt.condition(
            alt.datum["Số ảnh"] > threshold, alt.value("white"), alt.value("#1f2937")
        ),
    )
    st.altair_chart((heat + text).properties(height=240), width="stretch")
    st.markdown(
        f"- **Gọi oan:** {count(cm[0][1])} ảnh thật bị đoán là ảnh AI.\n"
        f"- **Bỏ sót:** {count(cm[1][0])} ảnh AI bị đoán là ảnh thật."
    )
    with st.expander("Xem dạng bảng"):
        st.dataframe(
            cells.pivot(index="Thực tế", columns="Dự đoán", values="Số ảnh"),
            width="stretch",
        )


def show_metrics(m: dict) -> None:
    accuracy, precision, recall, uncertain = st.columns(4)
    accuracy.metric(
        "Accuracy",
        percent(m["accuracy"]),
        help="Đoán đúng bao nhiêu % tổng số ảnh.",
        border=True,
    )
    precision.metric(
        "Precision",
        percent(m["precision"]),
        help="Trong các ảnh bị gọi là ảnh AI, bao nhiêu % đúng là ảnh AI.",
        border=True,
    )
    recall.metric(
        "Recall",
        percent(m["recall"]),
        help="Trong tất cả ảnh AI, mô hình bắt được bao nhiêu %.",
        border=True,
    )
    uncertain.metric(
        "Tỷ lệ Chưa chắc",
        percent(m["uncertain_n"] / m["n"]),
        help="Số ảnh rơi vào vùng Chưa chắc trên toàn bộ ảnh test.",
        border=True,
    )
    if m["accuracy"] >= ACCURACY_TARGET:
        st.badge(
            f"Đạt mục tiêu accuracy ≥ {ACCURACY_TARGET:.0%}",
            icon=":material/check_circle:",
            color="green",
        )
    else:
        st.badge(
            f"Chưa đạt mục tiêu accuracy ≥ {ACCURACY_TARGET:.0%}",
            icon=":material/warning:",
            color="orange",
        )
    decided_n = m["n"] - m["uncertain_n"]
    st.caption(
        f"Tính trên toàn bộ {count(m['n'])} ảnh, gồm cả {count(m['uncertain_n'])} ảnh Chưa chắc. "
        f"Riêng {count(decided_n)} ảnh đã có kết luận (độ phủ {percent(decided_n / m['n'])}): "
        f"accuracy {percent(m['decided_accuracy'])}; số này không thay thế accuracy toàn bộ."
    )


def show_groups(groups: list[dict], first_column: str) -> None:
    st.dataframe(
        pd.DataFrame(
            [
                {
                    first_column: g["name"],
                    "Số ảnh": g["n"],
                    "Accuracy": g["accuracy"] * 100,
                    "Chưa chắc": g["uncertain_n"] / g["n"] * 100,
                }
                for g in groups
            ]
        ),
        column_config={
            "Accuracy": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100
            ),
            "Chưa chắc": st.column_config.NumberColumn(format="%.1f%%", width="small"),
        },
        hide_index=True,
        width="stretch",
    )


def show_report(r: dict) -> None:
    st.subheader("Kết quả trên tập test")
    show_metrics(r["test"])

    matrix, groups = st.columns([4, 7], gap="large")
    with matrix:
        st.markdown("##### Confusion matrix")
        show_confusion_matrix(r["test"]["confusion_matrix"])
    with groups:
        st.markdown("##### Theo từng nguồn ảnh")
        if r.get("by_source"):
            show_groups(r["by_source"], "Nguồn")
        else:
            st.info("Báo cáo chưa có số đo theo từng nguồn.")
        st.markdown("##### Ảnh ngoài bộ dữ liệu chính")
        if r.get("ood"):
            show_groups(r["ood"], "Bộ ảnh")
        else:
            st.info("Chưa có số đo cho ảnh ngoài bộ dữ liệu chính.")

    st.subheader("Phiên bản được đánh giá")
    th = r["thresholds"]
    st.markdown(
        f"Ngưỡng tính accuracy: **{th['binary']}**. "
        f"Vùng Chưa chắc: từ **{th['low']}** đến **{th['high']}**."
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Thành phần": name,
                    "Phiên bản": r[key]["version"],
                    "Hash": r[key]["hash"],
                }
                for name, key in (
                    ("Dữ liệu", "dataset"),
                    ("Mô hình", "model"),
                    ("Chuẩn hóa ảnh", "profile"),
                )
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def show_model_tab() -> None:
    try:
        report = load_report()
    except (OSError, ValueError):
        st.error(
            "Báo cáo đánh giá không đọc được hoặc sai định dạng "
            "nên không hiển thị số đo.",
            icon=":material/error:",
        )
        return
    if report is None:
        st.info("Chưa có số đo: mô hình chưa được đánh giá.", icon=":material/info:")
        st.caption(
            f"Mục tiêu dự án: accuracy từ {ACCURACY_TARGET:.0%} trên tập test GenImage. "
            "Đây là mục tiêu, chưa phải kết quả."
        )
        return
    show_report(report)


def show_dataset() -> None:
    labels = pd.read_csv(LABELS_CSV)
    genimage = labels[labels["source"].isin(SOURCE_NAMES)]
    total, real, ai, tools = st.columns(4)
    total.metric("Tổng ảnh GenImage", count(len(genimage)), border=True)
    real.metric("Ảnh thật", count(int((genimage["label"] == 0).sum())), border=True)
    ai.metric("Ảnh AI", count(int((genimage["label"] == 1).sum())), border=True)
    tools.metric(
        "Công cụ AI",
        genimage.loc[genimage["label"] == 1, "source"].nunique(),
        border=True,
    )
    table = (
        pd.crosstab(genimage["source"], genimage["split"])
        .reindex(index=list(SOURCE_NAMES), columns=["train", "val", "test"])
        .rename(index=SOURCE_NAMES)
    )
    table["Tổng"] = table.sum(axis=1)
    st.dataframe(table.rename_axis("Nguồn"), width="stretch")
    st.caption(
        "Mọi ảnh được cắt về 256×256 rồi mới nén JPEG chất lượng 95, để mô hình không "
        "học định dạng file. CIFAKE chỉ dùng chạy thử, không tính vào kết quả."
    )


def show_audit() -> None:
    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    gate = audit["gate"]
    if gate["passed"]:
        st.badge(
            f"Đạt: AUROC sau chuẩn hóa không vượt {gate['max_a_eff']}",
            icon=":material/check_circle:",
            color="green",
        )
    else:
        st.badge(
            f"Không đạt: AUROC sau chuẩn hóa vượt {gate['max_a_eff']}",
            icon=":material/warning:",
            color="orange",
        )
    slices = audit["genimage"]["slices"]
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "So sánh": title,
                    "Ảnh gốc": slices[key]["raw"]["a_eff"],
                    "Đã chuẩn hóa": slices[key]["post"]["a_eff"],
                }
                for key, title in AUDIT_SLICES.items()
            ]
        ),
        column_config={
            "Ảnh gốc": st.column_config.NumberColumn(format="%.2f"),
            "Đã chuẩn hóa": st.column_config.NumberColumn(format="%.2f"),
        },
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "Đoán thật hay AI chỉ từ thông tin file (định dạng, kích thước, mức nén, EXIF). "
        "AUROC 0.50 nghĩa là ngang đoán mò, tức thông tin file không lộ đáp án. "
        "Kết quả này không chứng minh trong nội dung ảnh hết mọi dấu hiệu dễ học nhầm."
    )


def show_data_tab() -> None:
    st.subheader("Bộ dữ liệu")
    try:
        show_dataset()
    except (OSError, ValueError, KeyError):
        st.info("Chưa đọc được thông tin bộ dữ liệu.", icon=":material/info:")
    st.subheader("Kiểm tra rò rỉ metadata")
    try:
        show_audit()
    except (OSError, ValueError, KeyError, TypeError):
        st.info("Chưa đọc được kết quả kiểm tra.", icon=":material/info:")


st.title("Kết quả đánh giá")
model_tab, data_tab = st.tabs(
    [":material/model_training: Mô hình", ":material/dataset: Dữ liệu"]
)
with model_tab:
    show_model_tab()
with data_tab:
    show_data_tab()
