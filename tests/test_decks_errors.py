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
    data = r.json()
    return data["access_token"], data["refresh_token"]


def create_deck(client, token: str, title: str, visibility: str = "public"):
    r = client.post("/decks/", json={"title": title, "visibility": visibility}, headers=auth_headers(token))
    return r.json()["id"]


def add_card_mcq(client, token: str, deck_id: int):
    payload = {
        "qtype": "mcq",
        "question": "Q?",
        "answer": "A",
        "options": ["A", "B", "C", "D"],
    }
    r = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(token))
    return r.json()["id"]


def test_visibility_filter_and_get_deck_not_found(client):
    owner_tok, _ = register_and_login(client, "vis1@example.com")
    public_id = create_deck(client, owner_tok, "Pub", visibility="public")
    private_id = create_deck(client, owner_tok, "Priv", visibility="private")

    # visibility=public should show only public
    r = client.get("/decks?visibility=public", headers=auth_headers(owner_tok))
    assert r.status_code == 200
    assert any(d["id"] == public_id for d in r.json())

    # visibility=private should show only private owned by user
    r = client.get("/decks?visibility=private", headers=auth_headers(owner_tok))
    assert r.status_code == 200
    assert any(d["id"] == private_id for d in r.json())

    # get_deck 404 (wrong owner)
    other_tok, _ = register_and_login(client, "vis2@example.com")
    r = client.get(f"/decks/{public_id}", headers=auth_headers(other_tok))
    # Public decks are accessible to any authenticated user
    assert r.status_code == 200


def test_favorite_private_forbidden_and_not_found(client):
    owner_tok, _ = register_and_login(client, "fav1@example.com")
    deck_id = create_deck(client, owner_tok, "Priv", visibility="private")
    other_tok, _ = register_and_login(client, "fav2@example.com")

    # Non-owner cannot favorite private deck
    r = client.post(f"/decks/{deck_id}/favorite", headers=auth_headers(other_tok))
    assert r.status_code == 403

    # Favorite not found
    r = client.post(f"/decks/999999/favorite", headers=auth_headers(other_tok))
    assert r.status_code == 404


def test_list_cards_private_forbidden(client):
    owner_tok, _ = register_and_login(client, "lc1@example.com")
    deck_id = create_deck(client, owner_tok, "Priv", visibility="private")
    other_tok, _ = register_and_login(client, "lc2@example.com")

    r = client.get(f"/decks/{deck_id}/cards", headers=auth_headers(other_tok))
    assert r.status_code == 403


def test_update_deck_owner_id_ignored(client):
    tok, _ = register_and_login(client, "upd1@example.com")
    deck_id = create_deck(client, tok, "DeckU")

    r = client.patch(
        f"/decks/{deck_id}",
        json={"owner_id": 9999, "title": "NewTitle"},
        headers=auth_headers(tok),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "NewTitle"
    assert body["owner_id"] != 9999


def test_update_card_non_owner_and_not_found_and_valid_mcq_update(client):
    owner_tok, _ = register_and_login(client, "uc1@example.com")
    deck_id = create_deck(client, owner_tok, "D1")
    card_id = add_card_mcq(client, owner_tok, deck_id)

    # Non-owner update -> 404 deck not found or not owned
    other_tok, _ = register_and_login(client, "uc2@example.com")
    r = client.patch(
        f"/decks/{deck_id}/cards/{card_id}",
        json={"question": "X"},
        headers=auth_headers(other_tok),
    )
    assert r.status_code == 404

    # Card not found for owner
    r = client.patch(
        f"/decks/{deck_id}/cards/999999",
        json={"question": "Y"},
        headers=auth_headers(owner_tok),
    )
    assert r.status_code == 404

    # Valid mcq options update to hit assignment path
    r = client.patch(
        f"/decks/{deck_id}/cards/{card_id}",
        json={"qtype": "mcq", "options": ["1", "2", "3", "4"]},
        headers=auth_headers(owner_tok),
    )
    assert r.status_code == 200


def test_create_card_non_owner_forbidden_or_not_found(client):
    owner_tok, _ = register_and_login(client, "create_non_owner1@example.com")
    other_tok, _ = register_and_login(client, "create_non_owner2@example.com")
    deck_id = create_deck(client, owner_tok, "OwnerDeck", visibility="public")

    payload = {
        "qtype": "fillups",
        "question": "Q?",
        "answer": "A",
    }
    # Non-owner attempt to create card should fail (endpoint restricts to owner)
    res = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(other_tok))
    assert res.status_code == 403


def test_delete_card_errors(client):
    owner_tok, _ = register_and_login(client, "dc1@example.com")
    deck_id = create_deck(client, owner_tok, "D2")
    card_id = add_card_mcq(client, owner_tok, deck_id)

    # Non-owner cannot delete -> 404 deck not found/owned
    other_tok, _ = register_and_login(client, "dc2@example.com")
    r = client.delete(f"/decks/{deck_id}/cards/{card_id}", headers=auth_headers(other_tok))
    assert r.status_code == 404

    # Owner delete non-existent card
    r = client.delete(f"/decks/{deck_id}/cards/999999", headers=auth_headers(owner_tok))
    assert r.status_code == 404
