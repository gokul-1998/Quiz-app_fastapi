import pytest
from fastapi.testclient import TestClient

def get_auth_headers(client: TestClient) -> dict:
    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"deckapiuser_{random_suffix}@example.com"
    password = "testpassword"
    client.post("/auth/register", json={"email": email, "password": password})
    login_response = client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def test_list_my_decks(client: TestClient):
    headers = get_auth_headers(client)
    # Create public and private decks for this user
    client.post("/decks/", json={"title": "My Public Deck", "visibility": "public"}, headers=headers)
    client.post("/decks/", json={"title": "My Private Deck", "visibility": "private"}, headers=headers)
    resp = client.get("/decks/my", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    titles = [d["title"] for d in data]
    assert "My Public Deck" in titles
    assert "My Private Deck" in titles


def test_list_decks_all_and_visibility(client: TestClient):
    headers1 = get_auth_headers(client)
    headers2 = get_auth_headers(client)
    # User1 creates public and private decks
    client.post("/decks/", json={"title": "User1 Public", "visibility": "public"}, headers=headers1)
    client.post("/decks/", json={"title": "User1 Private", "visibility": "private"}, headers=headers1)
    # User2 creates public and private decks
    client.post("/decks/", json={"title": "User2 Public", "visibility": "public"}, headers=headers2)
    client.post("/decks/", json={"title": "User2 Private", "visibility": "private"}, headers=headers2)

    # User1 lists /decks/ (should see all public decks and their own private deck)
    resp1 = client.get("/decks/", headers=headers1)
    assert resp1.status_code == 200
    titles1 = [d["title"] for d in resp1.json()]
    assert "User1 Public" in titles1
    assert "User1 Private" in titles1
    assert "User2 Public" in titles1
    assert "User2 Private" not in titles1

    # User2 lists /decks/ (should see all public decks and their own private deck)
    resp2 = client.get("/decks/", headers=headers2)
    assert resp2.status_code == 200
    titles2 = [d["title"] for d in resp2.json()]
    assert "User2 Public" in titles2
    assert "User2 Private" in titles2
    assert "User1 Public" in titles2
    assert "User1 Private" not in titles2


def test_list_public_decks(client: TestClient):
    headers = get_auth_headers(client)
    client.post("/decks/", json={"title": "Public Deck X", "visibility": "public"}, headers=headers)
    resp = client.get("/decks/public", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert any(d["title"] == "Public Deck X" for d in data)
