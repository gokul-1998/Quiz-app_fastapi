import pytest

def auth_headers(token: str):
    return {"Authorization": f"Bearer {token}"}


def register_and_login(client, email: str = "likeuser@example.com", password: str = "Passw0rd!123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    return data["access_token"], data["refresh_token"]


def create_deck(client, token: str, title: str, visibility: str = "public", tags: str | None = None):
    payload = {"title": title, "visibility": visibility}
    if tags is not None:
        payload["tags"] = tags
    r = client.post("/decks/", json=payload, headers=auth_headers(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def test_like_unlike_and_ordering(client):
    token, _ = register_and_login(client, "order1@example.com")
    # Create three public decks
    d1 = create_deck(client, token, "Deck A", tags="python")
    d2 = create_deck(client, token, "Deck B", tags="python")
    d3 = create_deck(client, token, "Deck C", tags="python")

    # New user to add likes
    token2, _ = register_and_login(client, "order2@example.com")

    # Like counts: d1 -> 1 like, d2 -> 2 likes, d3 -> 0 likes
    client.post(f"/decks/{d1}/like", headers=auth_headers(token))
    client.post(f"/decks/{d2}/like", headers=auth_headers(token))
    client.post(f"/decks/{d2}/like", headers=auth_headers(token2))

    # Verify liked flag for current user on listing
    r = client.get("/decks?page=1&size=10&search=Deck", headers=auth_headers(token))
    assert r.status_code == 200
    decks = r.json()
    # Expect order by like_count desc: d2 (2), d1 (1), d3 (0)
    ids = [d["id"] for d in decks if d["title"].startswith("Deck ")]
    assert ids[:3] == [d2, d1, d3]

    # liked flags for current user (token): liked d1 and d2
    liked_flags = {d["id"]: d.get("liked", False) for d in decks}
    assert liked_flags.get(d1) is True
    assert liked_flags.get(d2) is True
    assert liked_flags.get(d3) in (False, None)

    # like_count values
    like_counts = {d["id"]: d.get("like_count", 0) for d in decks}
    assert like_counts.get(d2) == 2
    assert like_counts.get(d1) == 1
    assert like_counts.get(d3, 0) >= 0

    # Unlike deck d1 and confirm change
    client.delete(f"/decks/{d1}/like", headers=auth_headers(token))
    r = client.get("/decks?page=1&size=10&search=Deck", headers=auth_headers(token))
    decks = r.json()
    like_counts = {d["id"]: d.get("like_count", 0) for d in decks}
    assert like_counts.get(d1) == 0


def test_pagination_and_tag_combo(client):
    token, _ = register_and_login(client, "pagetag@example.com")
    # Create 15 decks, half with tag "algos", half with "db"
    for i in range(1, 16):
        tag = "algos" if i % 2 == 0 else "db"
        create_deck(client, token, f"PT Deck {i}", tags=tag, visibility="public")

    # Page 1 size 5
    r = client.get("/decks?page=1&size=5&search=PT%20Deck", headers=auth_headers(token))
    assert r.status_code == 200
    assert len(r.json()) == 5
    assert r.headers.get("X-Total-Count") is not None
    assert r.headers.get("X-Total-Pages") is not None

    # Filter by tag "algos"
    r = client.get("/decks?tag=algos&search=PT%20Deck&page=1&size=100", headers=auth_headers(token))
    decks = r.json()
    assert all("algos" in (d.get("tags") or "") for d in decks)


def test_private_access_rules(client):
    # owner creates private deck
    token_owner, _ = register_and_login(client, "owner@example.com")
    deck_id = create_deck(client, token_owner, "Private Deck", visibility="private")

    # another user attempts to list and access cards
    token_other, _ = register_and_login(client, "other@example.com")

    # Private deck should not be visible to other user unless owner or public
    r = client.get("/decks?page=1&size=50&search=Private", headers=auth_headers(token_other))
    assert all(d["id"] != deck_id for d in r.json())

    # Owner can see it
    r = client.get("/decks?page=1&size=50&search=Private", headers=auth_headers(token_owner))
    assert any(d["id"] == deck_id for d in r.json())
