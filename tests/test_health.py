from app.main import create_app


def test_health_503_khi_chua_co_scorer(client_no_model):
    r = client_no_model.get("/health")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "model_ready": False}


def test_health_200_khi_co_scorer(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_ready": True}


def test_scorer_duoc_luu_o_app_state(app_ready):
    assert callable(app_ready.state.scorer)
    assert create_app().state.scorer is None


def test_docs_va_openapi_tra_200(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "/health" in spec.json()["paths"]
