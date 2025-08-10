import json


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
    assert r.status_code == 201
    return r.json()["id"]


def add_card(client, token: str, deck_id: int, q: str = "Q?", a: str = "A") -> int:
    payload = {
        "qtype": "fillups",
        "question": q,
        "answer": a,
    }
    r = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(token))
    assert r.status_code == 201
    return r.json()["id"]


def add_mcq_card(client, token: str, deck_id: int, q: str = "Q?", a: str = "A") -> int:
    payload = {
        "qtype": "mcq",
        "question": q,
        "answer": a,
        "options": ["A", "B", "C", "D"],
    }
    r = client.post(f"/decks/{deck_id}/cards", json=payload, headers=auth_headers(token))
    assert r.status_code == 201
    return r.json()["id"]


def test_test_routes_full_coverage(client):
    owner_tok, _ = register_and_login(client, "testcov_owner@example.com")
    other_tok, _ = register_and_login(client, "testcov_other@example.com")

    # Create decks
    pub_id = create_deck(client, owner_tok, "Public Deck", tags="math,tag", visibility="public")
    priv_id = create_deck(client, owner_tok, "Private Deck", tags="secret", visibility="private")

    # Add cards
    c1 = add_card(client, owner_tok, pub_id, q="What is A?", a="A")
    c2 = add_mcq_card(client, owner_tok, pub_id, q="Pick A", a="A")
    add_card(client, owner_tok, priv_id, q="Hidden?", a="H")

    # start: public deck access by other, with explicit total_time_seconds
    r = client.post(
        "/tests/start",
        headers=auth_headers(other_tok),
        json={"deck_id": pub_id, "per_card_seconds": 7, "total_time_seconds": 30},
    )
    assert r.status_code == 200
    sess = r.json()
    assert sess["deck_id"] == pub_id and sess["per_card_seconds"] == 7 and sess["time_limit_seconds"] == 30

    # start: default time path (no total_time_seconds)
    r2 = client.post(
        "/tests/start",
        headers=auth_headers(other_tok),
        json={"deck_id": pub_id, "per_card_seconds": 5},
    )
    assert r2.status_code == 200
    sess2 = r2.json()
    # 2 cards => 10 seconds
    assert sess2["time_limit_seconds"] == 2 * 5

    # start: private deck by non-owner => 403
    r = client.post(
        "/tests/start",
        headers=auth_headers(other_tok),
        json={"deck_id": priv_id},
    )
    assert r.status_code == 403

    # submit-answer: valid card correct
    r = client.post(
        "/tests/submit-answer",
        headers=auth_headers(other_tok),
        params={"session_id": sess["session_id"]},
        json={"card_id": c1, "user_answer": "A", "time_taken": 3},
    )
    assert r.status_code == 200 and r.json()["is_correct"] is True

    # submit-answer: invalid card => 404
    r = client.post(
        "/tests/submit-answer",
        headers=auth_headers(other_tok),
        params={"session_id": sess["session_id"]},
        json={"card_id": 999999, "user_answer": "X"},
    )
    assert r.status_code == 404

    # complete: invalid session id format => 400
    bad = client.post(
        "/tests/complete",
        headers=auth_headers(other_tok),
        params={"session_id": "bad_format"},
        json=[{"card_id": c1, "user_answer": "A", "is_correct": True, "time_taken": 2}],
    )
    assert bad.status_code == 400

    # complete: valid, with mixed answers and time sum
    answers = [
        {"card_id": c1, "user_answer": "A", "is_correct": True, "time_taken": 2},
        {"card_id": c2, "user_answer": "B", "is_correct": False, "time_taken": 5},
    ]
    ok = client.post(
        "/tests/complete",
        headers=auth_headers(other_tok),
        params={"session_id": sess["session_id"]},
        json=answers,
    )
    assert ok.status_code == 200
    res = ok.json()
    assert res["total_cards"] == 2 and res["correct_answers"] == 1 and res["total_time"] == 7

    # stats endpoint (mocked data path)
    r = client.get("/tests/stats", headers=auth_headers(other_tok))
    assert r.status_code == 200 and r.json()["total_tests_taken"] == 0

    # leaderboard endpoint with params
    r = client.get("/tests/leaderboard", params={"deck_id": pub_id, "limit": 5}, headers=auth_headers(other_tok))
    assert r.status_code == 200 and r.json()["limit"] == 5

    # random-deck: with subject filter
    r = client.get("/tests/random-deck", params={"subject": "math"}, headers=auth_headers(other_tok))
    assert r.status_code == 200

    # random-deck: subject with no matches => 404
    r = client.get("/tests/random-deck", params={"subject": "nomatchsubjectxyz"}, headers=auth_headers(other_tok))
    assert r.status_code == 404


def test_start_nonexistent_deck_404(client):
    tok, _ = register_and_login(client, "start404@example.com")
    r = client.post(
        "/tests/start",
        headers=auth_headers(tok),
        json={"deck_id": 999999, "per_card_seconds": 5},
    )
    assert r.status_code == 404


def test_start_deck_without_cards_400(client):
    owner_tok, _ = register_and_login(client, "nocards_owner@example.com")
    other_tok, _ = register_and_login(client, "nocards_other@example.com")
    # Create public deck with no cards
    r = client.post(
        "/decks/",
        headers=auth_headers(owner_tok),
        json={"title": "Empty", "visibility": "public"},
    )
    assert r.status_code == 201
    deck_id = r.json()["id"]
    # Other user can access, but start should 400 due to no cards
    r2 = client.post(
        "/tests/start",
        headers=auth_headers(other_tok),
        json={"deck_id": deck_id, "per_card_seconds": 5},
    )
    assert r2.status_code == 400


def test_complete_with_nonexistent_deck_404(client):
    tok, _ = register_and_login(client, "complete404@example.com")
    # session_id format: any_user_999999_timestamp -> will parse deck id 999999
    session_id = "0_999999_0"
    r = client.post(
        "/tests/complete",
        headers=auth_headers(tok),
        params={"session_id": session_id},
        json=[],
    )
    assert r.status_code == 404
