"""Giao diện RealCheck, trang Kiểm tra ảnh. Chỉ gọi API, không dùng model trực tiếp.

Cách chạy (từ thư mục gốc repo):
    streamlit run streamlit/app.py
"""

import html
import io
from dataclasses import dataclass

from api_client import API_URL, Analysis, ApiError, analyze, api_status
from PIL import Image, ImageOps

import streamlit as st

PREVIEW_SIZE = (700, 700)
MIN_SHORT_SIDE = 256
THRESHOLD_LOW, THRESHOLD_HIGH = 0.3, 0.7  # tạm, chờ D08; chỉ để vẽ thang điểm
LEAN_THRESHOLD = (
    0.5  # tách "Chưa chắc" theo hướng nghiêng, cùng ngưỡng accuracy khi train
)

STYLE = """
<style>
[data-testid="stMainBlockContainer"] { max-width: 1120px; padding-top: 2.5rem; }
/* Menu ⋮ chỉ giữ nút đổi theme; test id này theo Streamlit 1.66, nâng bản phải kiểm lại */
[data-testid="stMainMenuDivider"],
[data-testid="stMainMenuItem-print"],
[data-testid="stMainMenuItem-recordScreencast"],
[data-testid="stMainMenuList"] ~ * { display: none; }
.rc-tagline { opacity: .75; margin: -.6rem 0 1rem; font-size: 1.05rem; }
.rc-card { border-radius: 12px; padding: 1rem 1.1rem; height: 100%; }
.rc-card b { display: block; font-size: 1.05rem; margin-bottom: .25rem; }
.rc-card span { font-size: .92rem; opacity: .85; }
.rc-verdict { border-left: 5px solid; margin-bottom: .4rem; }
.rc-verdict b { font-size: 1.45rem; }
.rc-real { background: rgba(34, 160, 90, .14); border-color: rgb(34, 160, 90); }
.rc-lean-real { background: rgba(34, 160, 90, .06); border-color: rgba(34, 160, 90, .5); }
.rc-lean-ai { background: rgba(230, 130, 30, .07); border-color: rgba(230, 130, 30, .5); }
.rc-ai { background: rgba(230, 130, 30, .16); border-color: rgb(230, 130, 30); }
.rc-score { display: flex; align-items: baseline; gap: .5rem; margin-top: .9rem; }
.rc-score strong { font-size: 2.3rem; line-height: 1.1; }
.rc-gauge { position: relative; display: flex; gap: 2px; margin: 1.1rem 0 .25rem; }
.rc-gauge div.rc-zone { padding: .3rem .1rem; text-align: center; font-size: .75rem;
  line-height: 1.15; display: flex; align-items: center; justify-content: center; }
.rc-gauge > .rc-real { background: rgba(34, 160, 90, .55); border-radius: 8px 0 0 8px; }
.rc-gauge > .rc-lean-real { background: rgba(34, 160, 90, .25); }
.rc-gauge > .rc-lean-ai { background: rgba(230, 130, 30, .28); }
.rc-gauge > .rc-ai { background: rgba(230, 130, 30, .6); border-radius: 0 8px 8px 0; }
.rc-gauge-large { margin-bottom: .4rem; }
.rc-gauge-large .rc-gauge div.rc-zone { padding: .35rem .2rem; font-size: .8rem; font-weight: 600; }
.rc-pin { position: absolute; top: -.6rem; width: 0; height: 0;
  transform: translateX(-50%); border-left: .42rem solid transparent;
  border-right: .42rem solid transparent; border-top: .55rem solid currentColor; }
.rc-ticks { position: relative; height: 1.2rem; font-size: .75rem; opacity: .7; }
.rc-ticks span { position: absolute; transform: translateX(-50%); }
.rc-ticks span:first-child { transform: none; }
.rc-ticks span:last-child { transform: translateX(-100%); }
</style>
"""
LOW_CONFIDENCE = (
    "Phân loại: Chưa chắc. Độ chắc chắn thấp, nên đối chiếu thêm nguồn ảnh."
)
LEVEL_REAL = ("rc-real", "Ảnh thật", "Ảnh có nhiều đặc điểm giống ảnh chụp thật.")
LEVEL_LEAN_REAL = ("rc-lean-real", "Dự đoán thật", LOW_CONFIDENCE)
LEVEL_LEAN_AI = ("rc-lean-ai", "Dự đoán AI", LOW_CONFIDENCE)
LEVEL_AI = ("rc-ai", "Ảnh AI", "Ảnh có nhiều đặc điểm giống ảnh do AI tạo.")


def display_level(result: Analysis) -> tuple[str, str, str]:
    """Hiển thị 4 mức; API vẫn trả 3 verdict, chỉ "uncertain" được tách theo điểm."""
    if result.verdict == "uncertain":
        return LEVEL_LEAN_AI if result.score >= LEAN_THRESHOLD else LEVEL_LEAN_REAL
    return LEVEL_AI if result.verdict == "likely_ai" else LEVEL_REAL


@dataclass(frozen=True)
class Preview:
    image: Image.Image
    format: str
    width: int
    height: int


def make_preview(data: bytes) -> Preview | None:
    """Ảnh xem trước; không đọc được thì None, việc kiểm tra hợp lệ là của API."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            image_format = im.format or "?"
            image = ImageOps.exif_transpose(im)
            width, height = image.size
            image.thumbnail(PREVIEW_SIZE)
            return Preview(image.convert("RGB"), image_format, width, height)
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return None


@st.cache_data(ttl=15, show_spinner=False)
def cached_api_status() -> str:
    return api_status()


def request_analysis() -> None:
    # Bỏ qua cú bấm đến khi đang gửi, để một lần bấm chỉ có một POST
    if not st.session_state.get("sending"):
        st.session_state.pending = True


def score_scale(labels: tuple[str, ...], pin: str = "") -> str:
    """Thanh 4 vùng theo ngưỡng, mốc hiển thị theo %."""
    edges = (0, THRESHOLD_LOW, LEAN_THRESHOLD, THRESHOLD_HIGH, 1)
    levels = (LEVEL_REAL, LEVEL_LEAN_REAL, LEVEL_LEAN_AI, LEVEL_AI)
    zones = "".join(
        f'<div class="rc-zone {level[0]}" style="width:{(end - start) * 100}%">{label}</div>'
        for level, label, start, end in zip(levels, labels, edges, edges[1:])
    )
    ticks = "".join(f'<span style="left:{e * 100}%">{e:.0%}</span>' for e in edges)
    return (
        '<div class="rc-gauge" role="img" aria-label="Thang điểm AI">'
        f'{zones}{pin}</div><div class="rc-ticks">{ticks}</div>'
    )


def show_score_gauge(score: float) -> None:
    pin = f'<div class="rc-pin" style="left:{score * 100}%"></div>'
    labels = ("Thật", LEVEL_LEAN_REAL[1], LEVEL_LEAN_AI[1], "AI")
    st.html(
        f'<div class="rc-score"><strong>{score:.0%}</strong><span>Điểm AI</span></div>'
        + score_scale(labels, pin)
    )


def show_analysis(result: Analysis) -> None:
    css_class, label, meaning = display_level(result)
    st.html(
        f'<div class="rc-card rc-verdict {css_class}"><b>{label}</b>'
        f"<span>{meaning}</span></div>"
    )
    show_score_gauge(result.score)
    st.caption(
        "Càng gần 100% càng giống ảnh AI. Đây không phải xác suất chắc chắn ảnh là giả."
    )

    with st.container(border=True):
        st.markdown("**:material/lightbulb: Lý do**")
        st.html(f"<p>{html.escape(result.reason)}</p>")
        st.markdown("**:material/photo_camera: Thông tin máy chụp (EXIF)**")
        st.html(f"<p>{html.escape(result.exif)}</p>")
        st.caption("EXIF chỉ là thông tin phụ, thiếu EXIF không chứng minh ảnh là AI.")

    st.warning(
        "Kết quả chỉ để tham khảo. Mô hình có thể sai, nhất là với ảnh đã bị nén "
        "hoặc ảnh từ công cụ AI mới, và không phát hiện ảnh thật bị chỉnh sửa.",
        icon=":material/info:",
    )
    details = f"Thời gian xử lý: {result.elapsed_seconds:.1f} giây"
    if result.request_id:
        details += f" · Mã yêu cầu: `{result.request_id}`"
    st.caption(details)


def show_error(error: ApiError) -> None:
    st.error(error.message, icon=":material/error:")
    if error.request_id:
        st.caption(f"Mã yêu cầu khi báo lỗi: `{error.request_id}`")


def show_intro() -> None:
    labels = tuple(
        level[1] for level in (LEVEL_REAL, LEVEL_LEAN_REAL, LEVEL_LEAN_AI, LEVEL_AI)
    )
    st.html(f'<div class="rc-gauge-large">{score_scale(labels)}</div>')
    st.markdown("##### Cách hoạt động")
    upload, analyze_step, read = st.columns(3)
    upload.markdown(
        "**:material/upload: 1. Tải ảnh lên**  \nJPEG hoặc PNG, tối đa 5 MB, "
        f"cạnh ngắn từ {MIN_SHORT_SIDE} px."
    )
    analyze_step.markdown(
        "**:material/psychology: 2. Phân tích**  \nCLIP đọc đặc trưng ảnh, "
        "Logistic Regression cho điểm từ 0% đến 100%."
    )
    read.markdown(
        "**:material/fact_check: 3. Đọc kết quả**  \nXem kết luận, điểm AI, lý do "
        "và thông tin máy chụp."
    )


def show_file_facts(name: str, size: int, preview: Preview | None) -> None:
    facts = [
        f"{size / 1_000_000:.2f} MB" if size >= 100_000 else f"{size / 1000:.1f} KB"
    ]
    if preview:
        facts = [preview.format, f"{preview.width} × {preview.height} px", *facts]
    st.html(f"<b>{html.escape(name)}</b><br>{html.escape(' · '.join(facts))}")
    if preview and min(preview.width, preview.height) < MIN_SHORT_SIDE:
        st.warning(
            f"Cạnh ngắn của ảnh nhỏ hơn {MIN_SHORT_SIDE} px nên có thể bị từ chối.",
            icon=":material/warning:",
        )


def check_image_page() -> None:
    st.title("Kiểm tra ảnh")
    st.html(
        '<p class="rc-tagline">Xem một bức ảnh có giống ảnh do AI tạo hay không.</p>'
    )
    uploaded = st.file_uploader(
        f"Chọn ảnh JPEG hoặc PNG, tối đa 5 MB, cạnh ngắn từ {MIN_SHORT_SIDE} px",
        type=["jpg", "jpeg", "png"],
    )
    state = st.session_state
    if uploaded is None:
        state.fingerprint, state.outcome, state.pending = None, None, False
        show_intro()
        return

    data = uploaded.getvalue()
    # Theo từng lần tải lên, không theo nội dung: đổi file luôn xóa kết quả cũ
    fingerprint = uploaded.file_id
    if state.get("fingerprint") != fingerprint:
        state.fingerprint, state.outcome, state.pending = fingerprint, None, False

    pending = state.get("pending", False)
    left, right = st.columns([5, 6], gap="large")
    with left:
        preview = make_preview(data)
        if preview is None:
            st.info("Không xem trước được ảnh này. Bạn vẫn có thể gửi để kiểm tra.")
        else:
            st.image(preview.image, width="stretch")
        show_file_facts(uploaded.name, len(data), preview)
    with right:
        st.button(
            "Kiểm tra ảnh",
            type="primary",
            width="stretch",
            icon=":material/search:",
            disabled=pending or isinstance(state.get("outcome"), Analysis),
            on_click=request_analysis,
        )
        if pending:
            state.sending = True
            try:
                with st.spinner("Đang phân tích ảnh..."):
                    state.outcome = analyze(uploaded.name, data, uploaded.type)
            finally:
                state.sending, state.pending = False, False
            st.rerun()
        outcome = state.get("outcome")
        if isinstance(outcome, Analysis):
            show_analysis(outcome)
        elif isinstance(outcome, ApiError):
            show_error(outcome)
        else:
            st.caption("Bấm nút để gửi ảnh đi phân tích.")


st.set_page_config(
    page_title="RealCheck", page_icon=":material/image_search:", layout="wide"
)
st.html(STYLE)
with st.sidebar:
    st.markdown("## RealCheck")
    st.caption("Phát hiện ảnh do AI tạo bằng CLIP + Logistic Regression.")
page = st.navigation(
    [
        st.Page(check_image_page, title="Kiểm tra ảnh", icon=":material/image_search:"),
        st.Page(
            "pages/1_Ket_qua_danh_gia.py",
            title="Kết quả đánh giá",
            icon=":material/analytics:",
            url_path="ket-qua-danh-gia",
        ),
    ]
)
with st.sidebar:
    status = cached_api_status()
    if status == "ready":
        st.badge("Hệ thống sẵn sàng", icon=":material/check_circle:", color="green")
    else:
        st.badge("Hệ thống chưa sẵn sàng", icon=":material/error:", color="orange")
        if status == "not_ready":
            st.caption("API đã chạy nhưng mô hình chưa sẵn sàng.")
        else:
            st.caption(f"Chưa kết nối được API tại `{API_URL}`.")
page.run()
