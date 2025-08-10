from tests.conftest import client  # rely on fixture


def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, email: str, password: str = "Passw0rd!123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    data = r.json()
    return data["access_token"], data["refresh_token"]


def test_private_deck_access_403(client):
    owner_tok, _ = register_and_login(client, "priv_owner@example.com")
    other_tok, _ = register_and_login(client, "priv_viewer@example.com")

    r = client.post(
        "/decks/",
        headers=auth_headers(owner_tok),
        json={"title": "Secret", "visibility": "private"},
    )
    assert r.status_code == 201
    deck_id = r.json()["id"]

    # Non-owner tries to fetch deck -> 403 branch at line 328
    res = client.get(f"/decks/{deck_id}", headers=auth_headers(other_tok))
    assert res.status_code == 403
