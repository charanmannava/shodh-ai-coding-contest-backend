def test_same_key_with_changed_payload_is_conflict(client):
    token = client.post(
        "/auth/login",
        json={"email": "participant@example.com", "password": "participant-password"},
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "stable-key"}
    original = {
        "contest_id": "contest-one",
        "problem_id": "problem-one",
        "code": "print(3)",
    }

    assert client.post("/submissions", headers=headers, json=original).status_code == 202
    response = client.post(
        "/submissions", headers=headers, json={**original, "code": "print(4)"}
    )
    assert response.status_code == 409
