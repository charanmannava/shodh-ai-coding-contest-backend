def test_login_returns_bearer_token(client):
    response = client.post(
        "/auth/login",
        json={"email": "participant@example.com", "password": "participant-password"},
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_login_rejects_invalid_credentials(client):
    response = client.post(
        "/auth/login",
        json={"email": "participant@example.com", "password": "wrong"},
    )

    assert response.status_code == 401


def test_protected_route_requires_authentication(client):
    assert client.get("/contests").status_code == 401
