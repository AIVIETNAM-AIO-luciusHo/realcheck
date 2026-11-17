"""GET /metrics (#162, #164): hợp đồng, cardinality, không lộ dữ liệu, không qua Nginx."""

import io
import re
import threading
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from prometheus_client.parser import text_string_to_metric_families

from app.main import create_app
from app.schemas import ErrorCode
from app.settings import Settings


def _jpeg(size=(400, 400), exif=None):
    buf = io.BytesIO()
    kw = {}
    if exif:
        e = Image.Exif()
        e[0x010F] = exif
        kw["exif"] = e
    Image.effect_noise(size, 60).convert("RGB").save(buf, "JPEG", **kw)
    return buf.getvalue()


def _post(client, data, name="a.jpg", **kw):
    return client.post("/v1/analyze", files={"file": (name, data, "image/jpeg")}, **kw)


def _samples(client):
    out = {}
    for fam in text_string_to_metric_families(client.get("/metrics").text):
        for s in fam.samples:
            out[(s.name, tuple(sorted(s.labels.items())))] = s.value
    return out


def _get(samples, name, **labels):
    return samples.get((name, tuple(sorted(labels.items()))), 0)


def test_dinh_dang_va_metric_co_mat(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")
    names = {s[0] for s in _samples(client)}
    for n in (
        "realcheck_model_ready",
        "realcheck_inference_slots_in_use",
        "realcheck_api_errors_total",
    ):
        assert n in names
    assert _get(_samples(client), "realcheck_model_ready") == 1


def test_model_ready_gauge_khi_chua_co_scorer(client_no_model):
    assert _get(_samples(client_no_model), "realcheck_model_ready") == 0


def test_dem_theo_nhom_status(client):
    assert _post(client, _jpeg()).status_code == 200
    assert _post(client, b"").status_code == 400
    assert _post(client, b"khong phai anh").status_code == 400
    s = _samples(client)
    route = "/v1/analyze"
    assert _get(s, "realcheck_requests_total", route=route, status_class="2xx") == 1
    assert _get(s, "realcheck_requests_total", route=route, status_class="4xx") == 2
    assert _get(s, "realcheck_requests_total", route=route, status_class="5xx") == 0
    assert _get(s, "realcheck_request_duration_seconds_count", route=route) == 3


def test_service_busy_va_slot_ve_0():
    gate, started = threading.Event(), threading.Event()

    def slow(image):
        started.set()
        gate.wait(5)
        return 0.5

    client = TestClient(create_app(scorer=slow, settings=Settings(inference_slots=1)))
    t = threading.Thread(target=_post, args=(client, _jpeg()))
    t.start()
    assert started.wait(5)
    assert _get(_samples(client), "realcheck_inference_slots_in_use") == 1
    assert _post(client, _jpeg()).status_code == 503
    gate.set()
    t.join(5)
    s = _samples(client)
    busy = ErrorCode.SERVICE_BUSY.value
    assert _get(s, "realcheck_api_errors_total", code=busy) == 1
    assert (
        _get(s, "realcheck_requests_total", route="/v1/analyze", status_class="5xx")
        == 1
    )
    assert _get(s, "realcheck_inference_slots_in_use") == 0


def test_cardinality_khong_tang_theo_duong_dan(client):
    for path in ("/health", "/x", f"/{uuid.uuid4()}"):
        client.get(path)
    _samples(client)  # làm nóng series của /metrics
    before = len(_samples(client))
    for i in range(200):
        client.get(f"/x{i}")
        client.get(f"/{uuid.uuid4()}")
    s = _samples(client)
    routes = {dict(k[1]).get("route") for k in s if "route" in dict(k[1])}
    assert routes <= {"/v1/analyze", "/health", "/metrics", "other"}
    assert len(s) == before  # 400 đường dẫn lạ không thêm series nào


def test_khong_lo_du_lieu_nguoi_dung(client):
    rid = str(uuid.uuid4())
    _post(
        client,
        _jpeg(exif="ZZTESTCAM"),
        name="SECRET_IMG_001.jpg",
        headers={"X-Request-ID": rid},
    )
    body = client.get("/metrics").text
    for bad in (
        "SECRET",
        "IMG_001",
        "ZZTESTCAM",
        rid,
        "/home/",
        "/models/",
        "C:\\",
        ".joblib",
    ):
        assert bad not in body
    labels = set(re.findall(r"(\w+)=\"", body))
    assert labels <= {
        "route",
        "status_class",
        "code",
        "le",
        "version",
        "major",
        "minor",
        "patchlevel",
        "implementation",
    }


def test_hai_app_cung_tien_trinh_khong_trung_registry():
    a, b = create_app(), create_app()
    assert a.state.metrics.registry is not b.state.metrics.registry


def test_nginx_khong_chuyen_metrics_cho_api():
    conf = Path("nginx/nginx.conf").read_text(encoding="utf-8")
    assert "metrics" not in conf
    assert (
        "location ~ ^/(health|docs|openapi\\.json)$" in conf
    )  # /metrics rơi vào location / (UI)


def _err(client, code):
    return _get(_samples(client), "realcheck_api_errors_total", code=code.value)


def test_loi_404_405_422_va_500_deu_duoc_dem(client):
    client.get("/khong-co")
    assert _err(client, ErrorCode.NOT_FOUND) == 1
    client.get("/v1/analyze")  # GET vào route chỉ cho POST
    assert _err(client, ErrorCode.METHOD_NOT_ALLOWED) == 1
    client.post("/v1/analyze")  # thiếu file
    assert _err(client, ErrorCode.MISSING_FILE) == 1
    client.post("/v1/analyze", files={"other": ("a.jpg", b"x", "image/jpeg")})
    assert _err(client, ErrorCode.MISSING_FILE) == 2


def test_loi_422_khong_phai_thieu_file_va_500(monkeypatch):
    def boom(image):
        raise RuntimeError("hỏng")

    app = create_app(scorer=boom)
    client = TestClient(app, raise_server_exceptions=False)
    client.post(
        "/v1/analyze", content=b"x", headers={"content-type": "application/json"}
    )
    assert (
        _err(client, ErrorCode.INVALID_REQUEST) + _err(client, ErrorCode.MISSING_FILE)
        == 1
    )

    app.add_api_route("/boom", lambda: 1 / 0)
    client.get("/boom")
    assert _err(client, ErrorCode.INTERNAL_ERROR) == 1


def test_loi_khong_lam_tang_series_theo_duong_dan(client):
    client.get("/a")
    _samples(client)  # làm nóng series của /metrics
    n = len(_samples(client))
    for i in range(50):
        client.get(f"/lạ-{i}")
    assert len(_samples(client)) == n
