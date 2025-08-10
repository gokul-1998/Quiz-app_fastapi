import os
import json
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_ai_missing_api_key(monkeypatch):
    from routes import ai_routes
    # Ensure key is missing
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    # Ensure we call through real function which will error on missing key

    r = client.post("/ai/generate-card", json={"prompt": "x", "desired_qtype": "fillups"})
    # Since _generate_with_gemini checks key at runtime, we expect 500
    assert r.status_code == 500
    assert "GOOGLE_API_KEY not set" in r.text


def test_ai_invalid_json_from_model(monkeypatch):
    from routes import ai_routes
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")

    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def generate_content(self, prompt_text):
            # Return non-JSON text
            return FakeResponse("not a json block")

    monkeypatch.setattr(ai_routes.genai, "GenerativeModel", lambda *_args, **_kwargs: FakeModel())

    r = client.post("/ai/generate-card", json={"prompt": "x", "desired_qtype": "fillups"})
    assert r.status_code == 500
    assert "Gemini did not return valid JSON" in r.text


def test_ai_exception_in_model(monkeypatch):
    from routes import ai_routes
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")

    class FakeModel:
        def generate_content(self, prompt_text):
            raise RuntimeError("network down")

    monkeypatch.setattr(ai_routes.genai, "GenerativeModel", lambda *_args, **_kwargs: FakeModel())

    r = client.post("/ai/generate-card", json={"prompt": "x", "desired_qtype": "mcq"})
    assert r.status_code == 500
    assert "Failed to generate content" in r.text
