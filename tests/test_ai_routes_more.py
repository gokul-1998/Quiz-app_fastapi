import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_ai_generate_match_success_markdown_wrapped(monkeypatch):
    from routes import ai_routes
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy")

    class FakeResponse:
        def __init__(self, text):
            self.text = text

    class FakeModel:
        def generate_content(self, prompt_text):
            return FakeResponse("""
            Here is your result:
            ```json
            {"question": "Match terms", "answer": "A-1", "options": null}
            ```
            """)

    monkeypatch.setattr(ai_routes.genai, "GenerativeModel", lambda *_a, **_k: FakeModel())

    r = client.post("/ai/generate-card", json={"prompt": "x", "desired_qtype": "match"})
    assert r.status_code == 200
    data = r.json()
    assert data["qtype"] == "match"
    assert data["question"]
    assert data["answer"]


def test_ai_generate_mcq_insufficient_options(monkeypatch):
    from routes import ai_routes

    def fake_generate(prompt: str, qtype: str):
        return ("Q", "A", ["1", "2", "3"])  # less than 4

    monkeypatch.setattr(ai_routes, "_generate_with_gemini", fake_generate)

    r = client.post("/ai/generate-card", json={"prompt": "x", "desired_qtype": "mcq"})
    assert r.status_code == 500
    assert "Failed to generate enough options for MCQ" in r.text
