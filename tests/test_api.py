import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from db import Base, get_db


@pytest.fixture(scope="session")
def test_engine():
    # Use a temporary SQLite file DB for the whole test session
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


@pytest.fixture(scope="session")
def TestingSessionLocal(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def override_db(TestingSessionLocal):
    def _get_db() -> Generator:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def user_and_token(client):
    email = "testuser@example.com"
    password = "Passw0rd!123"
    # Register (idempotent: ignore if exists)
    client.post("/auth/register", json={"email": email, "password": password})
    # Login
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    token = data["access_token"]
    return {"email": email, "token": token}


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_deck_card_flow(client, user_and_token):
    token = user_and_token["token"]

    # Create a public deck with tags
    deck_payload = {
        "title": "python",
        "description": "coding in python",
        "tags": "python,programming",
        "visibility": "public",
    }
    r = client.post("/decks/", json=deck_payload, headers=auth_headers(token))
    assert r.status_code == 201, r.text
    deck = r.json()
    deck_id = deck["id"]
    assert deck["visibility"] == "public"

    # Add an MCQ card (cards inherit deck visibility; no visibility in schema)
    card_payload = {
        "qtype": "mcq",
        "question": "Capital of France?",
        "answer": "Paris",
        "options": ["Paris", "London", "Berlin", "Rome"],
    }
    r = client.post(f"/decks/{deck_id}/cards", json=card_payload, headers=auth_headers(token))
    assert r.status_code == 201, r.text
    card = r.json()
    assert card["qtype"] == "mcq"
    assert "visibility" not in card  # removed from schema

    # List decks and ensure card_count and favourite work
    r = client.get("/decks?page=1&size=10", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    decks = r.json()
    assert any(d["id"] == deck_id for d in decks)
    d0 = next(d for d in decks if d["id"] == deck_id)
    assert d0["card_count"] == 1
    assert d0["favourite"] is False

    # Favorite the deck
    r = client.post(f"/decks/{deck_id}/favorite", headers=auth_headers(token))
    assert r.status_code in (200, 201, 204), r.text

    # Verify favourite flag now true
    r = client.get("/decks?page=1&size=10", headers=auth_headers(token))
    decks = r.json()
    d0 = next(d for d in decks if d["id"] == deck_id)
    assert d0["favourite"] is True

    # List cards in deck (should return one)
    r = client.get(f"/decks/{deck_id}/cards", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    cards = r.json()
    assert len(cards) == 1

    # Get single card
    cid = card["id"]
    r = client.get(f"/decks/{deck_id}/cards/{cid}", headers=auth_headers(token))
    assert r.status_code == 200, r.text
    one = r.json()
    assert one["id"] == cid

    # Unfavorite
    r = client.delete(f"/decks/{deck_id}/favorite", headers=auth_headers(token))
    assert r.status_code in (200, 204), r.text

    # Verify favourite flag false again
    r = client.get("/decks?page=1&size=10", headers=auth_headers(token))
    decks = r.json()
    d0 = next(d for d in decks if d["id"] == deck_id)
    assert d0["favourite"] is False
