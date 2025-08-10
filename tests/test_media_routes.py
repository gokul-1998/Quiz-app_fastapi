import io


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


def test_media_requires_auth_and_validations(client):
    # 401 without auth
    img_bytes = io.BytesIO(b"PNGDATA")
    r = client.post(
        "/media/upload-image",
        files={"file": ("x.png", img_bytes, "image/png")},
    )
    assert r.status_code in (401, 403)

    # Login
    token, _ = register_and_login(client, "media1@example.com")

    # 400 invalid extension
    bad_bytes = io.BytesIO(b"text")
    r = client.post(
        "/media/upload-image",
        headers=auth_headers(token),
        files={"file": ("notes.txt", bad_bytes, "text/plain")},
    )
    assert r.status_code == 400
    assert "Unsupported file type" in r.json().get("detail", "")

    # 201 success upload
    good = io.BytesIO(b"\x89PNG\r\n\x1a\n")
    r = client.post(
        "/media/upload-image",
        headers=auth_headers(token),
        data={"alt_text": "diagram"},
        files={"file": ("image.png", good, "image/png")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["url"].startswith("/static/uploads/")
    assert body["markdown"].startswith("![")


def test_media_save_error(monkeypatch, client):
    # Login
    token, _ = register_and_login(client, "media2@example.com")

    # Force open() to fail
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("builtins.open", boom)

    good = io.BytesIO(b"\x89PNG\r\n\x1a\n")
    r = client.post(
        "/media/upload-image",
        headers=auth_headers(token),
        data={"alt_text": "diagram"},
        files={"file": ("image.png", good, "image/png")},
    )
    assert r.status_code == 500
    assert "Failed to save image" in r.json().get("detail", "")
