import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.enums import EvaluationSplit, MalwareScanStatus, SubmissionStatus
from app.evaluators.mock import MockEvaluator
from app.main import app
from app.models import CourseRoster, EvaluationJob, Score, Submission
from app.security.malware import MalwareScanResult, MalwareScanner, get_malware_scanner
from app.services.state import InvalidStateTransition, transition_submission
from app.worker import EvaluationTimeoutError, process_job
import app.worker as worker_module
from tests.conftest import (
    auth_header,
    create_public_task,
    login,
    model_zip_bytes,
    notebook_bytes,
    register_student,
    upload_submission,
)


def setup_student_and_task(client):
    admin_token = login(client, "RootTA", "admin-password")
    assert create_public_task(client, admin_token).status_code == 201
    register_student(client)
    return admin_token, login(client, "20260001", "student-password")


def test_draft_is_stored_without_queue_and_replaces_previous(
    client, db_session, job_queue, artifact_storage
):
    _, student_token = setup_student_and_task(client)
    response = upload_submission(client, student_token, kind="DRAFT")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["submission"]["status"] == "COMPLETED"
    assert body["submission"]["official_attempt_consumed"] is False
    assert body["evaluation_job"] is None
    assert not job_queue.items
    assert (artifact_storage.artifact_path(body["submission"]["id"]) / "notebook.ipynb").is_file()
    replacement = upload_submission(client, student_token, kind="DRAFT")
    assert replacement.status_code == 201
    db_session.expire_all()
    original = db_session.get(Submission, body["submission"]["id"])
    assert original.status == SubmissionStatus.INVALIDATED
    assert not artifact_storage.artifact_path(original.id).exists()


def test_worker_saves_score_completes_and_updates_leaderboard(
    client, db_session, job_queue, artifact_storage
):
    admin_token, student_token = setup_student_and_task(client)
    notebook = notebook_bytes()
    model = model_zip_bytes()
    first = upload_submission(
        client, student_token, notebook_content=notebook, model_content=model
    )
    assert first.status_code == 201, first.text
    first_id = first.json()["submission"]["id"]
    first_job_id = job_queue.dequeue()
    factory = sessionmaker(
        bind=db_session.get_bind(), autoflush=False, autocommit=False, expire_on_commit=False
    )
    process_job(first_job_id, db_factory=factory, queue=job_queue, storage=artifact_storage)

    detail = client.get(f"/submissions/{first_id}", headers=auth_header(student_token))
    assert detail.status_code == 200
    assert detail.json()["status"] == "COMPLETED"
    assert len(detail.json()["scores"]) == 1
    first_score = detail.json()["scores"][0]["primary_score"]

    second = upload_submission(
        client, student_token, notebook_content=notebook, model_content=model
    )
    assert second.status_code == 201, second.text
    second_id = second.json()["submission"]["id"]
    process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)
    second_detail = client.get(f"/submissions/{second_id}", headers=auth_header(student_token))
    assert second_detail.json()["scores"][0]["primary_score"] == first_score

    leaderboard = client.get("/tasks/sentiment/leaderboard")
    assert leaderboard.status_code == 200
    assert leaderboard.json()[0]["nickname"] == "NLPHero"
    assert leaderboard.json()[0]["primary_score"] == first_score

    jobs = client.get("/admin/jobs", headers=auth_header(admin_token))
    assert jobs.status_code == 200
    assert len(jobs.json()) == 2
    submissions = client.get("/admin/submissions", headers=auth_header(admin_token))
    assert submissions.status_code == 200
    assert submissions.json()[0]["nickname"] == "NLPHero"
    assert submissions.json()[0]["task_slug"] == "sentiment"


def test_student_ui_contract_exposes_safe_task_submission_and_final_selection(
    client, db_session, job_queue, artifact_storage
):
    _, student_token = setup_student_and_task(client)
    task = client.get("/tasks/sentiment")
    assert task.status_code == 200
    assert task.json()["config"]["allowed_models"] == ["course/bert-base"]
    assert task.json()["public_leaderboard_visible"] is True

    response = upload_submission(client, student_token)
    submission_id = response.json()["submission"]["id"]
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)

    detail = client.get(
        f"/submissions/{submission_id}", headers=auth_header(student_token)
    )
    assert detail.status_code == 200
    assert {row["file_type"] for row in detail.json()["files"]} == {
        "notebook",
        "model_zip",
    }
    assert detail.json()["is_final_selection"] is False
    selected = client.post(
        f"/submissions/{submission_id}/final-selection",
        headers=auth_header(student_token),
    )
    assert selected.status_code == 200
    assert selected.json()["submission_id"] == submission_id
    assert len(client.get("/submissions/final-selections", headers=auth_header(student_token)).json()) == 1
    assert client.post(
        f"/submissions/{submission_id}/final-selection",
        headers=auth_header(student_token),
    ).status_code == 200


def test_admin_ui_contract_lists_roster_and_manages_join_codes(client):
    admin_token = login(client, "RootTA", "admin-password")
    register_student(client)
    roster = client.get("/admin/roster", headers=auth_header(admin_token))
    assert roster.status_code == 200
    assert roster.json()[0]["nickname"] == "NLPHero"

    created = client.post(
        "/admin/join-code",
        headers=auth_header(admin_token),
        json={"label": "Second code", "code": "SECOND-2026", "deactivate_existing": False},
    )
    assert created.status_code == 201
    code_id = created.json()["id"]
    listing = client.get("/admin/join-codes", headers=auth_header(admin_token))
    assert listing.status_code == 200
    assert any(row["id"] == code_id for row in listing.json())
    deactivated = client.post(
        f"/admin/join-codes/{code_id}/deactivate", headers=auth_header(admin_token)
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    student_token = login(client, "20260001", "student-password")
    assert client.get("/admin/join-codes", headers=auth_header(student_token)).status_code == 403


def test_baseline_practice_is_queued_without_consuming_official_attempt(
    client, job_queue
):
    _, student_token = setup_student_and_task(client)
    response = upload_submission(client, student_token, kind="BASELINE_PRACTICE")
    assert response.status_code == 201
    assert response.json()["submission"]["official_attempt_consumed"] is False
    assert response.json()["evaluation_job"]["split"] == "SMOKE"
    assert job_queue.dequeue() == response.json()["evaluation_job"]["id"]


def test_failed_job_does_not_block_next_job(
    client, db_session, job_queue, artifact_storage
):
    _, first_token = setup_student_and_task(client)
    db_session.add(CourseRoster(student_number="20260002", real_name="Lee NLP", section="A"))
    db_session.commit()
    register_student(
        client,
        nickname="SecondHero",
        student_number="20260002",
        real_name="Lee NLP",
    )
    second_token = login(client, "20260002", "student-password")
    assert upload_submission(client, first_token).status_code == 201
    assert upload_submission(client, second_token).status_code == 201
    first_job_id = job_queue.dequeue()
    second_job_id = job_queue.dequeue()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    class RejectingEvaluator(MockEvaluator):
        def validate_submission(self, context):
            raise ValueError("synthetic student artifact failure")

    process_job(
        first_job_id,
        db_factory=factory,
        queue=job_queue,
        storage=artifact_storage,
        evaluator_factory=lambda _: RejectingEvaluator(),
    )
    process_job(second_job_id, db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    assert db_session.get(EvaluationJob, first_job_id).status == SubmissionStatus.FAILED
    assert db_session.get(EvaluationJob, second_job_id).status == SubmissionStatus.COMPLETED


def test_validation_failure_is_not_queued_and_staging_is_cleaned(
    client, db_session, job_queue, artifact_storage
):
    _, student_token = setup_student_and_task(client)
    response = upload_submission(
        client,
        student_token,
        model_content=model_zip_bytes(extras={"model/attack.py": b"raise SystemExit"}),
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "UNSUPPORTED_FILE"
    assert not job_queue.items
    assert not any(artifact_storage.incoming_root.iterdir())
    assert not any(artifact_storage.artifact_root.iterdir())
    submission = db_session.scalar(select(Submission))
    db_session.refresh(submission)
    assert submission.status == SubmissionStatus.FAILED
    assert submission.official_attempt_consumed is False


def test_students_cannot_access_other_submission_admin_or_private_score(
    client, db_session, job_queue, artifact_storage
):
    admin_token, first_token = setup_student_and_task(client)
    db_session.add(CourseRoster(student_number="20260002", real_name="Lee NLP", section="A"))
    db_session.commit()
    register_student(
        client,
        nickname="SecondHero",
        student_number="20260002",
        real_name="Lee NLP",
    )
    second_token = login(client, "20260002", "student-password")
    response = upload_submission(client, first_token)
    submission_id = response.json()["submission"]["id"]
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.add(
        Score(
            submission_id=submission_id,
            split=EvaluationSplit.PRIVATE,
            primary_metric="private",
            primary_score=1.0,
            metrics={"secret": 1.0},
            visible_to_student=False,
        )
    )
    db_session.commit()

    assert client.get(f"/submissions/{submission_id}", headers=auth_header(second_token)).status_code == 404
    own = client.get(f"/submissions/{submission_id}", headers=auth_header(first_token)).json()
    assert all(score["split"] != "PRIVATE" for score in own["scores"])
    assert client.get("/admin/jobs", headers=auth_header(first_token)).status_code == 403
    download = client.get(
        f"/admin/submissions/{submission_id}/download/notebook",
        headers=auth_header(admin_token),
    )
    assert download.status_code == 200
    assert client.get(
        f"/admin/submissions/{submission_id}/download/notebook",
        headers=auth_header(second_token),
    ).status_code == 403


def test_quarantined_submission_is_never_queued_or_downloadable(
    client, job_queue, artifact_storage
):
    class SyntheticInfectedScanner(MalwareScanner):
        def scan(self, paths):
            return MalwareScanResult(MalwareScanStatus.INFECTED, "synthetic-test-signature")

    app.dependency_overrides[get_malware_scanner] = lambda: SyntheticInfectedScanner()
    admin_token, student_token = setup_student_and_task(client)
    response = upload_submission(client, student_token)
    assert response.status_code == 400
    submission_id = response.json()["detail"]["submission_id"]
    assert not job_queue.items
    assert (artifact_storage.quarantine_root / submission_id).is_dir()
    assert client.get("/admin/quarantine", headers=auth_header(student_token)).status_code == 403
    quarantine = client.get("/admin/quarantine", headers=auth_header(admin_token))
    assert quarantine.status_code == 200
    assert quarantine.json()[0]["status"] == "QUARANTINED"
    download = client.get(
        f"/admin/submissions/{submission_id}/download/model_zip",
        headers=auth_header(admin_token),
    )
    assert download.status_code == 404


def test_server_error_retries_once_then_fails_without_consuming_attempt(
    client, db_session, job_queue, artifact_storage
):
    _, student_token = setup_student_and_task(client)
    response = upload_submission(client, student_token)
    job_id = job_queue.dequeue()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)

    class BrokenServerEvaluator(MockEvaluator):
        def run_inference(self, context, model):
            raise RuntimeError("synthetic infrastructure failure")

    evaluator_factory = lambda _: BrokenServerEvaluator()
    process_job(
        job_id,
        db_factory=factory,
        queue=job_queue,
        storage=artifact_storage,
        evaluator_factory=evaluator_factory,
    )
    assert job_queue.dequeue() == job_id
    process_job(
        job_id,
        db_factory=factory,
        queue=job_queue,
        storage=artifact_storage,
        evaluator_factory=evaluator_factory,
    )
    db_session.expire_all()
    job = db_session.get(EvaluationJob, job_id)
    submission = db_session.get(Submission, response.json()["submission"]["id"])
    assert job.status == SubmissionStatus.FAILED
    assert job.attempts == 2
    assert submission.official_attempt_consumed is False
    assert not job_queue.items


def test_invalid_status_transition_is_rejected(db_session):
    submission = Submission(status=SubmissionStatus.COMPLETED)
    with pytest.raises(InvalidStateTransition):
        transition_submission(submission, SubmissionStatus.RUNNING)


def test_worker_marks_timeout_without_retry(
    client, db_session, job_queue, artifact_storage, monkeypatch
):
    _, student_token = setup_student_and_task(client)
    response = upload_submission(client, student_token)
    job_id = job_queue.dequeue()
    def timeout(*args):
        raise EvaluationTimeoutError

    monkeypatch.setattr(worker_module, "_check_timeout", timeout)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_job(job_id, db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    job = db_session.get(EvaluationJob, job_id)
    assert response.status_code == 201
    assert job.status == SubmissionStatus.FAILED
    assert job.error_kind == "EVALUATION_TIMEOUT"
    assert not job_queue.items
