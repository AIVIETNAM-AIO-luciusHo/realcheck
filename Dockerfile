# API RealCheck: FastAPI + CLIP/Logistic Regression chạy CPU.
# Build từ gốc repo: docker build -t realcheck-api .
# Cách chạy và cách cung cấp model: app/README.md, mục "Chạy bằng Docker".
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# torch lấy từ index CPU để không kéo bản CUDA; cùng phiên bản với models/requirements-ml.txt.
COPY requirements.txt ./
COPY models/requirements-ml.txt requirements-ml.txt
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.15.0 \
    && pip install -r requirements.txt -r requirements-ml.txt

COPY app/ app/
COPY models/*.py models/

RUN useradd --create-home --uid 10001 realcheck
USER realcheck

# Model và trọng số CLIP không nằm trong image; mount vào hai đường dẫn này lúc chạy.
ENV REALCHECK_MODEL_PATH=/models/clip_probe.joblib \
    HF_HOME=/hf-cache \
    HF_HUB_OFFLINE=1

EXPOSE 8000

# /health trả 503 khi chưa có model nên container báo unhealthy; start-period tính cả warmup CLIP.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
