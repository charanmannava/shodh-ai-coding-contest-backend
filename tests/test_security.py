def token(client, email, password):
    return client.post(
        "/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]


def test_participant_cannot_create_problem(client):
    response = client.post(
        "/problems",
        headers={
            "Authorization": f"Bearer {token(client, 'participant@example.com', 'participant-password')}"
        },
        json={
            "organization_id": "org-one",
            "title": "Unauthorized",
            "statement": "No",
            "test_cases": [{"input": "1", "expected_output": "1"}],
        },
    )
    assert response.status_code == 403


def test_hidden_test_input_is_never_returned(client):
    response = client.get(
        "/problems/problem-one",
        headers={
            "Authorization": f"Bearer {token(client, 'participant@example.com', 'participant-password')}"
        },
    )
    body = response.text

    assert response.status_code == 200
    assert "2 4" not in body
    assert "6\\n" not in body
