"""Test tích hợp qua gateway thật (G05, T026): chỉ được thu thập khi đặt REALCHECK_GATEWAY_URL.

Không đặt biến thì thư mục này bị bỏ qua hoàn toàn (không skip, không tính test), nên CI nhẹ không đổi.
Chạy: REALCHECK_GATEWAY_URL=http://localhost python -m pytest tests/integration --junitxml=artifacts/ui-gateway.xml
"""

import os

GATEWAY = os.environ.get("REALCHECK_GATEWAY_URL", "").rstrip("/")

collect_ignore_glob = [] if GATEWAY else ["test_*.py"]

if GATEWAY:
    # streamlit/api_client.py đọc biến này lúc import; đặt trước khi AppTest nạp trang.
    os.environ["REALCHECK_API_URL"] = GATEWAY
