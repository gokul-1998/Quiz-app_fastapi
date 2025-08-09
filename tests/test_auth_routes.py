
def test_register_user(client):
    response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "testpassword"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "User registered successfully"}

    # Test registering the same user again
    response = client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "testpassword"},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "User already exists"}


def test_login_for_access_token(client):
    # First, register a user
    client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "loginpassword"},
    )

    response = client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "loginpassword"},
    )
    assert response.status_code == 200
    json_response = response.json()
    assert "access_token" in json_response
    assert "refresh_token" in json_response
    assert json_response["token_type"] == "bearer"

    # Test login with wrong password
    response = client.post(
        "/auth/login",
        data={"username": "login@example.com", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_get_current_user_invalid_token_type(client):
    # Register and login to get a refresh token
    client.post(
        "/auth/register",
        json={"email": "invalidtype@example.com", "password": "testpassword"},
    )
    login_response = client.post(
        "/auth/login",
        data={"username": "invalidtype@example.com", "password": "testpassword"},
    )
    refresh_token = login_response.json()["refresh_token"]

    # Try to use the refresh token as an access token
    response = client.post(
        "/auth/refresh",
        params={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid access token"}


def test_get_current_user_user_not_found(client):
    # Create a token for a user that doesn't exist
    from auth import create_access_token
    non_existent_user_token = create_access_token({"sub": "nouser@example.com", "type": "access"})

    response = client.post(
        "/auth/refresh",
        params={"refresh_token": "anytoken"},
        headers={"Authorization": f"Bearer {non_existent_user_token}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "User not found"}


def test_refresh_token_mismatch(client):
    # Register and login
    client.post(
        "/auth/register",
        json={"email": "mismatch@example.com", "password": "testpassword"},
    )
    login_response = client.post(
        "/auth/login",
        data={"username": "mismatch@example.com", "password": "testpassword"},
    )
    tokens = login_response.json()
    access_token = tokens["access_token"]

    # Create a second, valid, but different refresh token
    from auth import create_refresh_token
    mismatched_refresh_token = create_refresh_token({"sub": "mismatch@example.com", "type": "refresh"})

    # Try to use the mismatched refresh token
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": mismatched_refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Refresh token mismatch"}


def test_refresh_token(client):
    # Register and login to get tokens
    client.post(
        "/auth/register",
        json={"email": "refresh@example.com", "password": "refreshpassword"},
    )
    login_response = client.post(
        "/auth/login",
        data={"username": "refresh@example.com", "password": "refreshpassword"},
    )
    tokens = login_response.json()
    access_token = tokens["access_token"]
    refresh_token = tokens["refresh_token"]

    # Use the refresh token to get a new access token
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()

    # Test with invalid refresh token
    response = client.post(
        "/auth/refresh",
        json={"refresh_token": "invalidtoken"},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 401


