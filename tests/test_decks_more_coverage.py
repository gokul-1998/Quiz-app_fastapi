import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def auth_headers(t):
    return {"Authorization": f"Bearer {t}"}


def reg_login(client, email):
    client.post("/auth/register", json={"email": email, "password": "Passw0rd!123"})
    r = client.post(
        "/auth/login",
        data={"username": email, "password": "Passw0rd!123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    tok = r.json()["access_token"]
    return tok


def create_deck(client, tok, title="T", visibility="public"):
    r = client.post("/decks/", json={"title": title, "visibility": visibility}, headers=auth_headers(tok))
    return r.json()["id"]


def test_like_unlike_edge_paths(client):
    tok = reg_login(client, "likeedge@example.com")
    # Like nonexistent deck -> 404 (line 277)
    r = client.post("/decks/999999/like", headers=auth_headers(tok))
    assert r.status_code == 404

    # Create deck and ensure unlike when not liked -> 204 (line 290)
    deck_id = create_deck(client, tok, title="D1")
    r = client.delete(f"/decks/{deck_id}/like", headers=auth_headers(tok))
    assert r.status_code == 204


def test_favorite_paths_and_success(client):
    owner = reg_login(client, "favowner@example.com")
    other = reg_login(client, "favother@example.com")
    pub_id = create_deck(client, owner, title="PUB", visibility="public")
    priv_id = create_deck(client, owner, title="PRIV", visibility="private")

    # Private favorite by non-owner -> 403 (line 302)
    r = client.post(f"/decks/{priv_id}/favorite", headers=auth_headers(other))
    assert r.status_code == 403

    # Favorite nonexistent -> 404 (line 299)
    r = client.post("/decks/999999/favorite", headers=auth_headers(other))
    assert r.status_code == 404

    # Favorite public success path -> commit and return (covers 305-308)
    r = client.post(f"/decks/{pub_id}/favorite", headers=auth_headers(other))
    assert r.status_code == 204


def test_list_visibility_filter_branch(client):
    tok = reg_login(client, "visbranch@example.com")
    create_deck(client, tok, title="V1", visibility="public")
    create_deck(client, tok, title="V2", visibility="private")
    # Hit visibility filter true branch (line 190)
    r = client.get("/decks?visibility=public", headers=auth_headers(tok))
    assert r.status_code == 200


def test_get_card_branches(client):
    owner = reg_login(client, "cardb@example.com")
    other = reg_login(client, "cardb2@example.com")
    deck_id = create_deck(client, owner, visibility="private")

    # Deck not found (415)
    r = client.get("/decks/999999/cards/1", headers=auth_headers(owner))
    assert r.status_code == 404

    # Card not found (418)
    r = client.get(f"/decks/{deck_id}/cards/999999", headers=auth_headers(owner))
    assert r.status_code == 404

    # Private 403 for non-owner (421)
    # First add a card to ensure deck has cards
    card_payload = {"qtype": "fillups", "question": "A __ B", "answer": "C"}
    created = client.post(f"/decks/{deck_id}/cards", json=card_payload, headers=auth_headers(owner)).json()
    card_id = created["id"]
    r = client.get(f"/decks/{deck_id}/cards/{card_id}", headers=auth_headers(other))
    assert r.status_code == 403


def test_update_deck_owner_id_branch(client):
    tok = reg_login(client, "updownerbranch@example.com")
    deck_id = create_deck(client, tok)
    r = client.patch(f"/decks/{deck_id}", json={"owner_id": 123, "title": "X"}, headers=auth_headers(tok))
    assert r.status_code == 200


def test_update_card_invalid_options_branch_and_delete_success(client):
    tok = reg_login(client, "updcardbranch@example.com")
    deck_id = create_deck(client, tok)
    # Create mcq card
    payload = {"qtype": "mcq", "question": "Q?", "answer": "A", "options": ["A","B","C","D"]}
    r = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(tok))
    card_id = r.json()["id"]

    # Invalid options path: include empty string to trip line 457
    r = client.patch(
        f"/decks/{deck_id}/cards/{card_id}",
        json={"qtype": "mcq", "options": ["1","2","", "4"]},
        headers=auth_headers(tok),
    )
    assert r.status_code == 400

    # Successful delete path (484-492)
    r = client.delete(f"/decks/{deck_id}/cards/{card_id}", headers=auth_headers(tok))
    assert r.status_code == 204
