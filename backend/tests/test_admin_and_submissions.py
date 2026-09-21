from tests.conftest import auth_header, login, register_student


def test_student_cannot_create_task(client):
    register_student(client)
    token = login(client, "20260001", "student-password")

    response = client.post(
        "/tasks",
        headers=auth_header(token),
        json={"slug": "sentiment", "title": "Sentiment Analysis"},
    )

    assert response.status_code == 403


def test_admin_can_create_task_and_student_submission_creates_queue_job(client):
    admin_token = login(client, "RootTA", "admin-password")
    task_response = client.post(
        "/tasks",
        headers=auth_header(admin_token),
        json={
            "slug": "sentiment",
            "title": "Sentiment Analysis",
            "is_public": True,
            "max_official_submissions": 1,
            "config": {
                "dataset_config": {"public_path": "hidden/sentiment/public.jsonl"},
                "allowed_models": [],
                "metric_config": {"primary": "macro_f1", "secondary": ["accuracy"]},
                "split_config": {"smoke": "smoke.jsonl", "public": "public.jsonl"},
                "scoring_strategy": "task_primary_score",
            },
        },
    )
    assert task_response.status_code == 201, task_response.text

    register_student(client)
    student_token = login(client, "20260001", "student-password")
    response = client.post(
        "/submissions/sentiment",
        headers=auth_header(student_token),
        json={
            "kind": "EVALUATION",
            "model_name": "tiny-sentiment",
            "base_model": "configured-later",
            "seed": 42,
            "metadata_json": {"task": "sentiment"},
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["submission"]["status"] == "QUEUED"
    assert body["submission"]["official_attempt_consumed"] is True
    assert body["evaluation_job"]["split"] == "PUBLIC"


def test_official_submission_limit_is_enforced(client, db_session):
    admin_token = login(client, "RootTA", "admin-password")
    client.post(
        "/tasks",
        headers=auth_header(admin_token),
        json={
            "slug": "sentiment",
            "title": "Sentiment Analysis",
            "is_public": True,
            "max_official_submissions": 1,
        },
    )
    register_student(client)
    student_token = login(client, "20260001", "student-password")
    first = client.post(
        "/submissions/sentiment",
        headers=auth_header(student_token),
        json={"kind": "EVALUATION", "model_name": "first"},
    )
    assert first.status_code == 201

    second = client.post(
        "/submissions/sentiment",
        headers=auth_header(student_token),
        json={"kind": "EVALUATION", "model_name": "second"},
    )

    assert second.status_code == 400

