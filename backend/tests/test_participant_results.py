import csv
import io
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from app.models import Participant, Submission, Score, BaselineReference, Task
from app.core.enums import EvaluationSplit, SubmissionStatus
from app.worker import process_job
from tests.conftest import login, auth_header, create_public_task, upload_submission, model_zip_bytes


def evaluate(client, db, queue, storage, kind="EVALUATION"):
    result = upload_submission(client, "20260001", kind=kind)
    assert result.status_code == 201, result.text
    process_job(queue.dequeue(), db_factory=sessionmaker(bind=db.get_bind(), expire_on_commit=False), queue=queue, storage=storage)
    db.expire_all()
    return db.get(Submission, result.json()["submission"]["id"])


def set_score(db, submission, value):
    score = db.scalar(select(Score).where(Score.submission_id == submission.id))
    score.primary_score = value
    db.commit()


def test_fixed_baseline_best_development_improvement_and_csv(client, db_session, job_queue, artifact_storage):
    token = login(client, "RootTA", "admin-password")
    create_public_task(client, token)
    baseline = evaluate(client, db_session, job_queue, artifact_storage, "BASELINE_PRACTICE")
    set_score(db_session, baseline, .4)
    later = evaluate(client, db_session, job_queue, artifact_storage, "BASELINE_PRACTICE")
    set_score(db_session, later, .9)
    ref = db_session.scalar(select(BaselineReference))
    assert ref.submission_id == baseline.id
    board = client.get("/tasks/sentiment/leaderboard").json()
    assert len(board) == 1
    assert board[0]["primary_score"] == .4
    assert board[0]["best_development_score"] is None and board[0]["improvement"] is None
    first = evaluate(client, db_session, job_queue, artifact_storage)
    set_score(db_session, first, .7)
    best = evaluate(client, db_session, job_queue, artifact_storage)
    set_score(db_session, best, .8)
    tied = evaluate(client, db_session, job_queue, artifact_storage)
    set_score(db_session, tied, .8)
    from app.services.results import task_results
    result = task_results(db_session, baseline.task_id)[0]
    assert result["representative"][0].id == best.id  # First successful tie wins.
    row = client.get("/tasks/sentiment/leaderboard").json()[0]
    assert row["baseline_score"] == .4 and row["best_development_score"] == .8
    assert row["improvement"] == pytest.approx(.4)
    assert "submission_id" not in row and "student_number" not in row
    for submission in [best, tied]:
        assert client.post(f"/admin/submissions/{submission.id}/invalidate", headers=auth_header(token)).status_code == 200
    row = client.get("/tasks/sentiment/leaderboard").json()[0]
    assert row["best_development_score"] == .7
    export = client.get("/admin/tasks/sentiment/results.csv", headers=auth_header(token))
    assert export.status_code == 200 and "charset=utf-8" in export.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(export.content.decode("utf-8"))))
    assert rows[0]["student_number"] == "20260001" and rows[0]["emoji"] == "🧠"
    assert rows[0]["total_submission_count"] == "5"
    assert rows[0]["best_development_score"] == "0.7"
    assert client.get("/admin/tasks/sentiment/results.csv").status_code == 401
    assert client.get("/admin/tasks/sentiment/participants").status_code == 401
    # Invalidated pinned baseline stays pinned until an explicit admin reset.
    client.post(f"/admin/submissions/{baseline.id}/invalidate", headers=auth_header(token))
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["baseline_score"] is None
    pid = db_session.scalar(select(Participant)).id
    reset = client.put(f"/admin/participants/{pid}/tasks/sentiment/baseline", headers=auth_header(token), json={"submission_id": later.id})
    assert reset.status_code == 200
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["baseline_score"] == .9


def test_validation_failure_cannot_pin_baseline(client, db_session, job_queue, artifact_storage):
    create_public_task(client, login(client, "RootTA", "admin-password"))
    bad = upload_submission(client, "20260001", kind="BASELINE_PRACTICE", model_content=model_zip_bytes(extras={"attack.py": b"code"}))
    assert bad.status_code == 400
    assert db_session.scalar(select(BaselineReference)) is None
    good = evaluate(client, db_session, job_queue, artifact_storage, "BASELINE_PRACTICE")
    assert db_session.scalar(select(BaselineReference)).submission_id == good.id


@pytest.mark.parametrize("status", [SubmissionStatus.FAILED, SubmissionStatus.QUARANTINED, SubmissionStatus.INVALIDATED])
def test_unsuccessful_scores_excluded(client, db_session, job_queue, artifact_storage, status):
    create_public_task(client, login(client, "RootTA", "admin-password"))
    submission = evaluate(client, db_session, job_queue, artifact_storage)
    submission.status = status
    db_session.commit()
    assert client.get("/tasks/sentiment/leaderboard").json() == []
    assert client.get(f"/submissions/{submission.id}").json()["scores"] == []


def test_public_privacy_and_admin_display_edits(client, db_session, job_queue, artifact_storage):
    token = login(client, "RootTA", "admin-password")
    create_public_task(client, token)
    task = db_session.scalar(select(Task))
    task.config.dataset_config = {"hidden_test_path": "/secret/answers"}
    task.config.split_config = {"secret": "answer-key"}
    db_session.commit()
    submission = evaluate(client, db_session, job_queue, artifact_storage)
    submission.internal_error_message = "secret internal path"
    db_session.commit()
    for url in ["/tasks", "/tasks/sentiment", "/tasks/sentiment/leaderboard", f"/submissions/{submission.id}"]:
        response = client.get(url)
        assert response.status_code == 200
        for value in ["20260001", "Kim NLP", "/secret/answers", "secret internal path", "storage_path", "original_filename"]:
            assert value not in response.text
    admin = client.get("/admin/submissions", headers=auth_header(token)).json()[0]
    assert admin["student_number"] == "20260001"
    pid = db_session.scalar(select(Participant)).id
    assert client.patch(f"/admin/participants/{pid}", json={"nickname": "Updated", "emoji": "🤖"}).status_code == 401
    assert client.patch(f"/admin/participants/{pid}", headers=auth_header(token), json={"nickname": "Updated", "emoji": "🤖"}).status_code == 200
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["nickname"] == "Updated"
    assert client.get(f"/admin/submissions/{submission.id}/download/notebook").status_code == 401


def test_csv_preserves_zero_prefixed_student_number(client, db_session):
    from app.models import CourseRoster
    db_session.add(CourseRoster(student_number="001234", real_name="Synthetic"))
    db_session.commit()
    token = login(client, "RootTA", "admin-password")
    create_public_task(client, token)
    assert upload_submission(client, "001234").status_code == 201
    response = client.get("/admin/tasks/sentiment/results.csv", headers=auth_header(token))
    assert list(csv.DictReader(io.StringIO(response.text)))[0]["student_number"] == "001234"


def test_missing_baseline_and_deadline_guard(client, db_session, job_queue, artifact_storage):
    from datetime import UTC, datetime, timedelta
    token = login(client, "RootTA", "admin-password")
    create_public_task(client, token)
    evaluate(client, db_session, job_queue, artifact_storage)
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["improvement"] is None
    task = db_session.scalar(select(Task))
    task.dev_deadline = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    assert upload_submission(client, "20260001").status_code == 400


def test_admin_roster_upload_to_anonymous_worker_and_csv_e2e(client, db_session, job_queue, artifact_storage):
    token = login(client, "RootTA", "admin-password")
    assert client.post("/admin/roster/upload", headers=auth_header(token), files={"file": ("synthetic.csv", b"student_number,real_name,section\n000002,Synthetic E2E,A\n", "text/csv")}).json() == {"imported": 1}
    create_public_task(client, token)
    ids = []
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    for kind in ["BASELINE_PRACTICE", "EVALUATION", "EVALUATION"]:
        result = upload_submission(client, "000002", kind=kind)
        assert result.status_code == 201
        ids.append(result.json()["submission"]["id"])
        process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)
        assert client.get(f"/submissions/{ids[-1]}").json()["status"] == "COMPLETED"
    db_session.expire_all()
    assert len({db_session.get(Submission, id).participant_id for id in ids}) == 1
    board = client.get("/tasks/sentiment/leaderboard")
    assert len(board.json()) == 1 and "000002" not in board.text
    assert board.json()[0]["improvement"] == pytest.approx(0)
    assert client.get("/admin/tasks/sentiment/participants", headers=auth_header(token)).json()[0]["student_number"] == "000002"
    assert client.get("/admin/tasks/sentiment/results.csv", headers=auth_header(token)).text.count("000002") == 1
    assert client.get("/admin/submissions").status_code == 401
    assert client.get(f"/admin/submissions/{ids[0]}/download/model_zip").status_code == 401


def test_submission_schema_errors_never_echo_private_inputs(client):
    response = client.post("/submissions/sentiment", data={"student_number": "private-roster-number", "submission_type": "bad-kind"})
    assert response.status_code == 422
    assert "private-roster-number" not in response.text
