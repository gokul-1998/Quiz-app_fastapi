import pytest
from fastapi.testclient import TestClient

# Helper function to get auth headers for a new, unique user
def get_auth_headers(client: TestClient) -> dict:
    import random
    import string

    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    email = f"decktestuser_{random_suffix}@example.com"
    password = "testpassword"

    # Register user
    register_response = client.post("/auth/register", json={"email": email, "password": password})
    assert register_response.status_code == 200, f"Failed to register user: {register_response.text}"

    # Login user
    login_response = client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    assert login_response.status_code == 200, f"Failed to log in: {login_response.text}"
    access_token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


def test_create_deck(client: TestClient):
    headers = get_auth_headers(client)
    response = client.post(
        "/decks/",
        json={"title": "My First Deck", "description": "A deck for testing"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "My First Deck"
    assert "id" in data


def test_list_decks(client: TestClient):
    headers = get_auth_headers(client)
    # Create a deck first to ensure the list is not empty
    client.post(
        "/decks/",
        json={"title": "List Test Deck", "description": "A deck for listing"},
        headers=headers,
    )

    response = client.get("/decks/", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert data[0]["title"] == "List Test Deck"


def test_get_deck(client: TestClient):
    headers = get_auth_headers(client)
    create_response = client.post(
        "/decks/",
        json={"title": "Get Test Deck", "description": "A deck for getting"},
        headers=headers,
    )
    deck_id = create_response.json()["id"]

    response = client.get(f"/decks/{deck_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == deck_id
    assert data["title"] == "Get Test Deck"


def test_update_deck(client: TestClient):
    headers = get_auth_headers(client)
    create_response = client.post(
        "/decks/",
        json={"title": "Update Test Deck", "description": "Before update"},
        headers=headers,
    )
    deck_id = create_response.json()["id"]

    response = client.patch(
        f"/decks/{deck_id}",
        json={"title": "Updated Title"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["description"] == "Before update"  # Description should not change


def test_delete_deck(client: TestClient):
    headers = get_auth_headers(client)
    create_response = client.post(
        "/decks/",
        json={"title": "Delete Test Deck", "description": "To be deleted"},
        headers=headers,
    )
    deck_id = create_response.json()["id"]

    delete_response = client.delete(f"/decks/{deck_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = client.get(f"/decks/{deck_id}", headers=headers)
    assert get_response.status_code == 404


def test_add_card_to_deck(client: TestClient):
    headers = get_auth_headers(client)
    create_deck_response = client.post(
        "/decks/",
        json={"title": "Card Test Deck"},
        headers=headers,
    )
    deck_id = create_deck_response.json()["id"]

    card_data = {
        "qtype": "mcq",
        "question": "What is the capital of Japan?",
        "answer": "Tokyo",
        "options": ["Tokyo", "Kyoto", "Osaka", "Hokkaido"],
    }
    response = client.post(
        f"/decks/{deck_id}/cards",
        json=card_data,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["question"] == "What is the capital of Japan?"
    assert data["qtype"] == "mcq"
    assert data["options"] == ["Tokyo", "Kyoto", "Osaka", "Hokkaido"]


def test_list_cards_in_deck(client: TestClient):
    headers = get_auth_headers(client)
    create_deck_response = client.post(
        "/decks/",
        json={"title": "List Cards Deck"},
        headers=headers,
    )
    deck_id = create_deck_response.json()["id"]

    # Add a card
    card_data = {
        "qtype": "fillups",
        "question": "The sky is ____.",
        "answer": "blue",
    }
    client.post(f"/decks/{deck_id}/cards", json=card_data, headers=headers)

    response = client.get(f"/decks/{deck_id}/cards", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["question"] == "The sky is ____."
    assert data[0]["qtype"] == "fillups"

