import pytest
from fastapi.testclient import TestClient

from app import gemini
from app.main import app


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    def forbidden_client(*args, **kwargs):
        raise AssertionError("Tests must substitute the provider or use a mock transport")

    monkeypatch.setattr(gemini.genai, "Client", forbidden_client)
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
