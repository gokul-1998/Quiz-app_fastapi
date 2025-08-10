import pytest

def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, email: str, password: str = "Passw0rd!123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return data["access_token"], data["refresh_token"]


def create_deck(client, token: str, title: str, visibility: str = "public"):
    r = client.post("/decks/", json={"title": title, "visibility": visibility}, headers=auth_headers(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def add_card_mcq(client, token: str, deck_id: int):
    payload = {
        "qtype": "mcq",
        "question": "Capital?",
        "answer": "Paris",
        "options": ["Paris", "London", "Berlin", "Rome"],
    }
    r = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(token))
    assert r.status_code in (200, 201)
    return r.json()["id"]


def add_card_fillups(client, token: str, deck_id: int):
    payload = {
        "qtype": "fillups",
        "question": "2+2=__",
        "answer": "4",
    }
    r = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(token))
    assert r.status_code in (200, 201)
    return r.json()["id"]


def test_update_card_invalid_options_for_non_mcq(client):
    tok, _ = register_and_login(client, "edge1@example.com")
    d = create_deck(client, tok, "Edge Deck")
    cid = add_card_fillups(client, tok, d)

    # Providing options while qtype remains non-mcq should 400
    r = client.patch(
        f"/decks/{d}/cards/{cid}",
        json={"options": ["a", "b", "c", "d"]},
        headers=auth_headers(tok),
    )
    assert r.status_code == 400
    assert "Options are only valid for mcq" in r.text


def test_update_card_switch_to_mcq_requires_options(client):
    tok, _ = register_and_login(client, "edge2@example.com")
    d = create_deck(client, tok, "Edge Deck2")
    cid = add_card_fillups(client, tok, d)

    # Switch to mcq without options -> 400
    r = client.patch(
        f"/decks/{d}/cards/{cid}",
        json={"qtype": "mcq"},
        headers=auth_headers(tok),
    )
    assert r.status_code == 400
    assert "mcq requires 'options'" in r.text


def test_update_card_mcq_invalid_options_list(client):
    tok, _ = register_and_login(client, "edge3@example.com")
    d = create_deck(client, tok, "Edge Deck3")
    cid = add_card_mcq(client, tok, d)

    # Provide fewer than 4 options -> 400
    r = client.patch(
        f"/decks/{d}/cards/{cid}",
        json={"qtype": "mcq", "options": ["one", "two", "three"]},
        headers=auth_headers(tok),
    )
    assert r.status_code == 400


def test_update_card_clear_options_when_not_mcq(client):
    tok, _ = register_and_login(client, "edge4@example.com")
    d = create_deck(client, tok, "Edge Deck4")
    cid = add_card_mcq(client, tok, d)

    # Change to fillups; options should be cleared
    r = client.patch(
        f"/decks/{d}/cards/{cid}",
        json={"qtype": "fillups", "answer": "4", "question": "2+2=__"},
        headers=auth_headers(tok),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["qtype"] == "fillups"
    assert body.get("options") in (None, [])
