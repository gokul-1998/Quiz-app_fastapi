import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_ai_generate_card_mcq_monkeypatch(monkeypatch):
    # Skip if AI router requires API key at import; we mock the generator function
    from routes import ai_routes

    def fake_generate(prompt: str, qtype: str):
        return (
            "What is 2+2?",
            "4",
            ["3", "4", "5", "6"] if qtype == "mcq" else None,
        )

    monkeypatch.setattr(ai_routes, "_generate_with_gemini", fake_generate)

    r = client.post("/ai/generate-card", json={"prompt": "math", "desired_qtype": "mcq"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["qtype"] == "mcq"
    assert data["question"]
    assert data["answer"] == "4"
    assert isinstance(data["options"], list) and len(data["options"]) >= 4


def test_ai_generate_card_fillups(monkeypatch):
    from routes import ai_routes

    def fake_generate(prompt: str, qtype: str):
        return (
            "2 + 2 = ____",
            "4",
            None,
        )

    monkeypatch.setattr(ai_routes, "_generate_with_gemini", fake_generate)

    r = client.post("/ai/generate-card", json={"prompt": "math", "desired_qtype": "fillups"})
    assert r.status_code == 200
    data = r.json()
    assert data["qtype"] == "fillups"
    assert data["options"] is None or data.get("options") is None


def test_ai_generate_card_error(monkeypatch):
    from routes import ai_routes

    def fake_generate(prompt: str, qtype: str):
        raise Exception("boom")

    monkeypatch.setattr(ai_routes, "_generate_with_gemini", fake_generate)

    r = client.post("/ai/generate-card", json={"prompt": "x", "desired_qtype": "mcq"})
    assert r.status_code == 500
    assert "Error generating card" in r.text
