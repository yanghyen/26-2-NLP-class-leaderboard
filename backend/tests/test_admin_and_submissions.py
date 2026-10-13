from app.core.enums import SubmissionStatus
from app.models import Submission

from tests.conftest import (
    auth_header,
    create_public_task,
    login,
    model_zip_bytes,
    prepare_participant,
    upload_submission,
)


def test_student_cannot_create_task(client):
    prepare_participant(client)
    token = "20260001"

    response = client.post(
        "/tasks",
        headers=auth_header(token),
        json={"slug": "sentiment", "title": "Sentiment Analysis"},
    )

    assert response.status_code == 401


def test_admin_can_partially_update_task_policy_and_preserve_other_fields(client):
    admin_token = login(client, "RootTA", "admin-password")
    created = create_public_task(client, admin_token)
    assert created.status_code == 201

    response = client.patch(
        "/tasks/sentiment",
        headers=auth_header(admin_token),
        json={
            "config": {
                "allowed_models": ["course/bert-v2"],
                "artifact_policy": {
                    "allowed_architectures": ["BertForSequenceClassificationV2"]
                },
            }
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Sentiment Analysis"
    assert body["is_public"] is True
    assert body["config"]["allowed_models"] == ["course/bert-v2"]
    assert body["config"]["artifact_policy"]["allowed_architectures"] == [
        "BertForSequenceClassificationV2"
    ]
    detail = client.get("/tasks/sentiment")
    assert detail.json()["config"] == {k: body["config"][k] for k in ("allowed_models", "artifact_policy")}


def test_task_update_requires_admin_and_existing_task(client):
    admin_token = login(client, "RootTA", "admin-password")
    assert create_public_task(client, admin_token).status_code == 201
    prepare_participant(client)
    student_token = "20260001"

    assert client.patch("/tasks/sentiment", json={"title": "No auth"}).status_code == 401
    assert client.patch(
        "/tasks/sentiment",
        headers=auth_header(student_token),
        json={"title": "Student edit"},
    ).status_code == 401
    assert client.patch(
        "/tasks/missing",
        headers=auth_header(admin_token),
        json={"title": "Missing"},
    ).status_code == 404


def test_task_update_rejects_empty_or_duplicate_policy(client):
    admin_token = login(client, "RootTA", "admin-password")
    assert create_public_task(client, admin_token).status_code == 201

    empty = client.patch(
        "/tasks/sentiment",
        headers=auth_header(admin_token),
        json={"config": {"artifact_policy": {}}},
    )
    duplicate = client.patch(
        "/tasks/sentiment",
        headers=auth_header(admin_token),
        json={"config": {"allowed_models": ["same/model", "same/model"]}},
    )

    assert empty.status_code == 422
    assert duplicate.status_code == 422


def test_updated_task_policy_is_used_by_submission_validation(client):
    admin_token = login(client, "RootTA", "admin-password")
    assert create_public_task(client, admin_token).status_code == 201
    updated = client.patch(
        "/tasks/sentiment",
        headers=auth_header(admin_token),
        json={
            "config": {
                "allowed_models": ["course/roberta-base"],
                "artifact_policy": {
                    "allowed_architectures": ["RobertaForSequenceClassification"]
                },
            }
        },
    )
    assert updated.status_code == 200
    prepare_participant(client)
    student_token = "20260001"

    rejected = upload_submission(client, student_token)
    accepted = upload_submission(
        client,
        student_token,
        model_content=model_zip_bytes(
            base_model="course/roberta-base",
            architecture="RobertaForSequenceClassification",
        ),
    )

    assert rejected.status_code == 400
    assert rejected.json()["detail"]["code"] == "INVALID_MODEL_FORMAT"
    assert accepted.status_code == 201, accepted.text


def test_admin_can_create_task_and_student_submission_creates_queue_job(client):
    admin_token = login(client, "RootTA", "admin-password")
    task_response = create_public_task(client, admin_token, max_submissions=1)
    assert task_response.status_code == 201, task_response.text

    prepare_participant(client)
    student_token = "20260001"
    response = upload_submission(client, student_token)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["submission"]["status"] == "QUEUED"
    assert body["evaluation_job"]["split"] == "PUBLIC"


def test_student_submissions_have_no_count_limit(client, db_session):
    admin_token = login(client, "RootTA", "admin-password")
    create_public_task(client, admin_token, max_submissions=1)
    prepare_participant(client)
    student_token = "20260001"
    first = upload_submission(client, student_token)
    assert first.status_code == 201

    submission = db_session.get(Submission, first.json()["submission"]["id"])
    submission.status = SubmissionStatus.COMPLETED
    db_session.commit()

    second = upload_submission(client, student_token)

    assert second.status_code == 201
