import pytest
from fastapi.testclient import TestClient

from app.main import create_app


def _fake_scorer(image):
    return 0.5


@pytest.fixture
def app_ready():
    return create_app(scorer=_fake_scorer)


@pytest.fixture
def client(app_ready):
    return TestClient(app_ready)


@pytest.fixture
def client_no_model():
    return TestClient(create_app())
