def access_token(client, email="participant@example.com", password="participant-password"):
    return client.post(
        "/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]


def test_submission_is_idempotent_and_code_changes_conflict(client):
    headers = {
        "Authorization": f"Bearer {access_token(client)}",
        "Idempotency-Key": "request-1",
    }
    payload = {
        "contest_id": "contest-one",
        "problem_id": "problem-one",
        "code": "print(sum(map(int, input().split())))",
    }
    first = client.post("/submissions", headers=headers, json=payload)
    duplicate = client.post("/submissions", headers=headers, json=payload)
    changed = client.post(
        "/submissions",
        headers=headers,
        json={**payload, "code": "print('different')"},
    )

    assert first.status_code == 202
    assert duplicate.status_code == 202
    assert duplicate.json()["submission_id"] == first.json()["submission_id"]
    assert changed.status_code == 409


def test_submission_response_does_not_expose_hidden_tests(client):
    headers = {
        "Authorization": f"Bearer {access_token(client)}",
        "Idempotency-Key": "request-hidden",
    }
    response = client.get(
        "/problems/problem-one",
        headers={"Authorization": headers["Authorization"]},
    )

    assert response.status_code == 200
    assert len(response.json()["samples"]) == 1
    assert response.json()["samples"][0]["input"] == "1 2\n"


def test_user_cannot_read_other_organization_submission(client):
    participant_token = access_token(client)
    created = client.post(
        "/submissions",
        headers={
            "Authorization": f"Bearer {participant_token}",
            "Idempotency-Key": "private-submission",
        },
        json={
            "contest_id": "contest-one",
            "problem_id": "problem-one",
            "code": "print(3)",
        },
    )
    outsider_token = access_token(
        client, "outsider@example.com", "outsider-password"
    )
    response = client.get(
        f"/submissions/{created.json()['submission_id']}",
        headers={"Authorization": f"Bearer {outsider_token}"},
    )

    assert response.status_code == 404


def test_participant_cannot_rejudge(client):
    participant_token = access_token(client)
    created = client.post(
        "/submissions",
        headers={
            "Authorization": f"Bearer {participant_token}",
            "Idempotency-Key": "participant-rejudge",
        },
        json={
            "contest_id": "contest-one",
            "problem_id": "problem-one",
            "code": "print(3)",
        },
    )
    response = client.post(
        f"/submissions/{created.json()['submission_id']}/rejudge",
        headers={"Authorization": f"Bearer {participant_token}"},
    )

    assert response.status_code == 403
