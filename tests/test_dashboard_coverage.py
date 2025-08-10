from typing import List


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


def create_deck(client, token: str, title: str, tags: str = None, visibility: str = "public") -> int:
    payload = {"title": title, "visibility": visibility}
    if tags is not None:
        payload["tags"] = tags
    r = client.post("/decks/", json=payload, headers=auth_headers(token))
    return r.json()["id"]


def add_cards(client, token: str, deck_id: int, n: int):
    for i in range(n):
        payload = {
            "qtype": "mcq",
            "question": f"Q{i}?",
            "answer": "A",
            "options": ["A", "B", "C", "D"],
        }
        client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(token))


def test_dashboard_endpoints_cover_branches(client):
    owner_tok, _ = register_and_login(client, "dash1@example.com")
    other_tok, _ = register_and_login(client, "dash2@example.com")

    # Create a mix of public/private decks with tags
    d1 = create_deck(client, owner_tok, "Algebra 1", tags="math,algebra", visibility="public")
    d2 = create_deck(client, owner_tok, "Biology", tags="science,biology", visibility="public")
    d3 = create_deck(client, owner_tok, "Private Chem", tags="science,chemistry", visibility="private")

    # Add cards to influence counts and random selections
    add_cards(client, owner_tok, d1, 6)
    add_cards(client, owner_tok, d2, 5)
    add_cards(client, owner_tok, d3, 2)

    # Hit dashboard root
    r = client.get("/dashboard/", headers=auth_headers(owner_tok))
    assert r.status_code == 200
    body = r.json()
    assert "popular_decks" in body and "stats" in body and "recent_activities" in body

    # Discover without filters (for other user, excludes own decks)
    r = client.get("/dashboard/discover", headers=auth_headers(other_tok))
    assert r.status_code == 200
    body = r.json()
    assert "decks" in body and isinstance(body["decks"], list)

    # Discover with subject filter and min_cards
    r = client.get(
        "/dashboard/discover",
        params={"subject": "math", "min_cards": 5},
        headers=auth_headers(other_tok),
    )
    assert r.status_code == 200
    decks = r.json()["decks"]
    # Should include Algebra deck
    assert any(d["title"] == "Algebra 1" for d in decks)

    # Subjects endpoint should aggregate tags
    r = client.get("/dashboard/subjects", headers=auth_headers(owner_tok))
    assert r.status_code == 200
    subs = r.json()
    assert "subjects" in subs and len(subs["subjects"]) >= 2

    # Quick test requires at least 5 cards and excludes current user decks
    r = client.get("/dashboard/quick-test", headers=auth_headers(other_tok))
    assert r.status_code == 200
    qt = r.json()["quick_test_decks"]
    # Since other_tok is different user, should list owner decks meeting criteria
    assert all(deck["card_count"] >= 5 for deck in qt)
