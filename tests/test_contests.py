def token(client, email, password):
    return client.post(
        "/auth/login", json={"email": email, "password": password}
    ).json()["access_token"]


def test_organizer_can_create_contest_and_participant_can_join(client):
    organizer_token = token(client, "organizer@example.com", "organizer-password")
    participant_token = token(client, "participant@example.com", "participant-password")
    create = client.post(
        "/contests",
        headers={"Authorization": f"Bearer {organizer_token}"},
        json={
            "organization_id": "org-one",
            "name": "New contest",
            "start_time": "2030-01-01T10:00:00Z",
            "end_time": "2030-01-01T11:00:00Z",
        },
    )
    assert create.status_code == 201

    joined = client.post(
        f"/contests/{create.json()['id']}/join",
        headers={"Authorization": f"Bearer {participant_token}"},
    )
    assert joined.status_code == 200
    assert joined.json()["status"] == "JOINED"


def test_participant_cannot_create_contest(client):
    participant_token = token(client, "participant@example.com", "participant-password")
    response = client.post(
        "/contests",
        headers={"Authorization": f"Bearer {participant_token}"},
        json={
            "organization_id": "org-one",
            "name": "Unauthorized contest",
            "start_time": "2030-01-01T10:00:00Z",
            "end_time": "2030-01-01T11:00:00Z",
        },
    )
    assert response.status_code == 403
