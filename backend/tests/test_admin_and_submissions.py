from app.core.enums import SubmissionStatus
from app.models import Submission

from tests.conftest import (
    auth_header,
    create_public_task,
    login,
    register_student,
    upload_submission,
)


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
    task_response = create_public_task(client, admin_token, max_submissions=1)
    assert task_response.status_code == 201, task_response.text

    register_student(client)
    student_token = login(client, "20260001", "student-password")
    response = upload_submission(client, student_token)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["submission"]["status"] == "QUEUED"
    assert body["submission"]["official_attempt_consumed"] is True
    assert body["evaluation_job"]["split"] == "PUBLIC"


def test_official_submission_limit_is_enforced(client, db_session):
    admin_token = login(client, "RootTA", "admin-password")
    create_public_task(client, admin_token, max_submissions=1)
    register_student(client)
    student_token = login(client, "20260001", "student-password")
    first = upload_submission(client, student_token)
    assert first.status_code == 201

    submission = db_session.get(Submission, first.json()["submission"]["id"])
    submission.status = SubmissionStatus.COMPLETED
    db_session.commit()

    second = upload_submission(client, student_token)

    assert second.status_code == 400
