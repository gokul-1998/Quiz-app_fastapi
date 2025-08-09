import os
import pytest
from jose import jwt
from datetime import datetime, timedelta

# Set environment variables for testing
os.environ["JWT_SECRET"] = "test_secret"
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "15"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)


def test_hash_password():
    password = "testpassword"
    hashed = hash_password(password)
    assert hashed != password
    assert isinstance(hashed, str)


def test_verify_password():
    password = "testpassword"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_create_access_token():
    data = {"sub": "test@example.com"}
    token = create_access_token(data)
    decoded = jwt.decode(token, "test_secret", algorithms=["HS256"])
    assert decoded["sub"] == "test@example.com"
    assert decoded["type"] == "access"
    assert "exp" in decoded


def test_create_refresh_token():
    data = {"sub": "test@example.com"}
    token = create_refresh_token(data)
    decoded = jwt.decode(token, "test_secret", algorithms=["HS256"])
    assert decoded["sub"] == "test@example.com"
    assert decoded["type"] == "refresh"
    assert "exp" in decoded


def test_decode_token():
    data = {"sub": "test@example.com"}
    token = create_access_token(data)
    decoded = decode_token(token)
    assert decoded["sub"] == "test@example.com"

    # Test invalid token
    invalid_token = "invalidtoken"
    assert decode_token(invalid_token) is None

    # Test expired token
    expired_token = create_access_token({"sub": "test@example.com"})
    # Manually expire the token
    payload = jwt.decode(expired_token, "test_secret", algorithms=["HS256"])
    payload["exp"] = datetime.utcnow() - timedelta(minutes=1)
    expired_token = jwt.encode(payload, "test_secret", algorithm="HS256")

    # Temporarily reduce the expiration time for testing and reload the module
    os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "-1"
    import importlib
    import auth
    importlib.reload(auth)

    expired_token_2 = auth.create_access_token(data)
    assert auth.decode_token(expired_token_2) is None

    # Reset the expiration time and reload the module again
    os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "15"
    importlib.reload(auth)
