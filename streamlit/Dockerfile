# Giao diện Streamlit RealCheck. Build từ gốc repo: docker build -t realcheck-ui streamlit
# Chạy cùng API và Nginx: docker compose up (xem nginx/README.md).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 10001 realcheck
USER realcheck

# UI gọi API qua gateway, không gọi thẳng container API; báo cáo đánh giá mount chỉ đọc.
ENV REALCHECK_API_URL=http://nginx \
    REALCHECK_EVAL_REPORT=/reports/evaluation.json

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"]

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
