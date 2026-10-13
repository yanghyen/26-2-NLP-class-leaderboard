"""Retention through the actual LocalArtifactStorage and committed worker pipeline."""
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from app.core.enums import MalwareScanStatus, SubmissionStatus
from app.db.session import get_db
from app.evaluators.mock import MockEvaluator
from app.main import app
from app.models import AuditLog, Base, BaselineReference, EvaluationJob, Score, Submission, SubmissionFile, Task
from app.security.malware import MalwareScanResult, MalwareScanner, get_malware_scanner
from app.services.artifact_cleanup import cleanup_successful_artifacts, cleanup_successful_submission
from app.storage.local import LocalArtifactStorage
from app.worker import process_job
from tests.conftest import auth_header, create_public_task, login, notebook_bytes, upload_submission


@pytest.fixture()
def artifact_storage(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield LocalArtifactStorage(directory)


@pytest.fixture()
def committed_db(db_session, client, tmp_path):
    """Independent SQLite connections make a pre-commit deletion observable."""
    engine = create_engine(f"sqlite:///{tmp_path / 'cleanup.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as target, db_session.get_bind().connect() as source:
        for table in Base.metadata.sorted_tables:
            rows = source.execute(select(table)).mappings().all()
            if rows:
                target.execute(table.insert(), [dict(row) for row in rows])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        def override_db():
            yield db
        app.dependency_overrides[get_db] = override_db
        try:
            yield db, factory
        finally:
            db.rollback()
    engine.dispose()
    (tmp_path / "cleanup.db").unlink(missing_ok=True)


def setup_task(client):
    token = login(client, "RootTA", "admin-password")
    assert create_public_task(client, token).status_code == 201
    return token


def run_uploaded(client, factory, queue, storage, kind="EVALUATION", **kwargs):
    response = upload_submission(client, "20260001", kind=kind, **kwargs)
    assert response.status_code == 201, response.text
    body = response.json()
    process_job(queue.dequeue(), db_factory=factory, queue=queue, storage=storage)
    return body["submission"]["id"], body["evaluation_job"]["id"]


@pytest.mark.parametrize("kind", ["BASELINE_PRACTICE", "EVALUATION"])
def test_files_deleted_only_after_success_and_scores_commit(
    client, committed_db, job_queue, artifact_storage, monkeypatch, kind
):
    db, factory = committed_db
    token = setup_task(client)
    task = db.scalar(select(Task))
    dataset_version = "synthetic-data-v1" + ("-revision" * 20 if kind == "EVALUATION" else "")
    task.config.dataset_config = {"version": dataset_version}
    db.commit()
    real_delete = artifact_storage.delete_artifact
    observed = []

    def inspect_committed_then_delete(submission_id):
        # A distinct DB connection must see scores, states, metadata and baseline pin.
        with factory() as observer:
            submission = observer.get(Submission, submission_id)
            job = observer.scalar(select(EvaluationJob).where(EvaluationJob.submission_id == submission_id))
            score = observer.scalar(select(Score).where(Score.submission_id == submission_id))
            assert submission.status == job.status == SubmissionStatus.COMPLETED
            assert submission.artifact_cleanup_status == "pending"
            assert submission.completed_at is not None
            assert score.primary_score is not None and score.metrics["deterministic"] is True
            assert submission.evaluator_version == "mock-v1"
            assert submission.dataset_version == dataset_version
            assert submission.artifact_digest and submission.validation_report["model"]
            if kind == "BASELINE_PRACTICE":
                assert observer.scalar(select(BaselineReference)).submission_id == submission_id
        path = artifact_storage.artifact_path(submission_id)
        assert (path / "notebook.ipynb").is_file()
        assert (path / "model.zip").is_file()
        observed.append(submission_id)
        real_delete(submission_id)

    monkeypatch.setattr(artifact_storage, "delete_artifact", inspect_committed_then_delete)
    sid, jid = run_uploaded(client, factory, job_queue, artifact_storage, kind)
    assert observed == [sid]
    assert not artifact_storage.artifact_path(sid).exists()
    assert not any(artifact_storage.work_root.iterdir())
    db.expire_all()
    submission = db.get(Submission, sid)
    assert submission.artifact_cleanup_status == "deleted"
    deleted_at = submission.artifact_deleted_at
    assert deleted_at is not None
    assert submission.participant_id and submission.model_name == "tiny-sentiment"
    assert submission.kind.value == kind
    assert db.get(EvaluationJob, jid).status == SubmissionStatus.COMPLETED
    files = db.scalars(select(SubmissionFile).where(SubmissionFile.submission_id == sid)).all()
    assert len(files) == 2 and all(len(f.checksum_sha256) == 64 for f in files)
    public = client.get(f"/submissions/{sid}")
    assert public.status_code == 200 and public.json()["status"] == "COMPLETED"
    assert public.json()["scores"][0]["primary_score"] is not None
    assert public.json()["files"] == []
    board = client.get("/tasks/sentiment/leaderboard").json()
    assert board[0]["primary_score"] == public.json()["scores"][0]["primary_score"]
    for forbidden in [str(artifact_storage.root), "solution.ipynb", "model.zip", "storage_path", "internal_error", "cleanup"]:
        assert forbidden not in public.text
    admin = client.get("/admin/submissions", headers=auth_header(token)).json()[0]
    assert admin["artifact_cleanup_status"] == "deleted" and admin["artifact_deleted_at"]
    # Repeated cleanup and manual deletion preserve success, scores and the deletion timestamp.
    assert cleanup_successful_submission(sid, storage=artifact_storage, db_factory=factory)
    assert cleanup_successful_submission(sid, storage=artifact_storage, db_factory=factory)
    assert client.delete(f"/admin/submissions/{sid}/artifact", headers=auth_header(token)).status_code == 204
    db.expire_all()
    assert db.get(Submission, sid).status == SubmissionStatus.COMPLETED
    assert db.get(Submission, sid).artifact_deleted_at == deleted_at


def test_fixed_baseline_and_best_development_survive_cleanup(client, committed_db, job_queue, artifact_storage):
    db, factory = committed_db
    setup_task(client)
    ids = []
    for index, kind in enumerate(["BASELINE_PRACTICE", "BASELINE_PRACTICE", "EVALUATION", "EVALUATION"]):
        sid, _ = run_uploaded(client, factory, job_queue, artifact_storage, kind,
                              notebook_content=notebook_bytes() + b" " * index)
        ids.append(sid)
        assert not artifact_storage.artifact_path(sid).exists()
    db.expire_all()
    assert db.scalar(select(BaselineReference)).submission_id == ids[0]
    scores = {score.submission_id: score.primary_score for score in db.scalars(select(Score))}
    row = client.get("/tasks/sentiment/leaderboard").json()[0]
    assert row["baseline_score"] == scores[ids[0]]
    assert row["best_development_score"] == max(scores[sid] for sid in ids[2:])
    assert row["improvement"] == pytest.approx(row["best_development_score"] - row["baseline_score"])


def test_deleted_download_and_reevaluation_are_safe(client, committed_db, job_queue, artifact_storage):
    _, factory = committed_db
    token = setup_task(client)
    sid, jid = run_uploaded(client, factory, job_queue, artifact_storage)
    for file_type in ("notebook", "model_zip"):
        url = f"/admin/submissions/{sid}/download/{file_type}"
        for headers, expected in [({}, 401), (auth_header("invalid"), 401), (auth_header(token), 409)]:
            response = client.get(url, headers=headers)
            assert response.status_code == expected
            assert str(artifact_storage.root) not in response.text
            assert "solution.ipynb" not in response.text and "storage_path" not in response.text
    retry = client.post(f"/admin/jobs/{jid}/retry", headers=auth_header(token))
    assert retry.status_code == 409 and "재평가할 수 없습니다" in retry.text
    assert not job_queue.items


@pytest.mark.parametrize("retry", ["sweep", "manual"])
def test_delete_failure_preserves_success_and_retry(client, committed_db, job_queue, artifact_storage, monkeypatch, retry):
    db, factory = committed_db
    token = setup_task(client)
    real_delete = artifact_storage.delete_artifact
    def fail(submission_id):
        # Model a partial deletion; the ZIP and extracted model still need a retry.
        (artifact_storage.artifact_path(submission_id) / "notebook.ipynb").unlink(missing_ok=True)
        raise OSError(f"private-delete-error: {artifact_storage.root}/secret-original.ipynb")
    monkeypatch.setattr(artifact_storage, "delete_artifact", fail)
    sid, jid = run_uploaded(client, factory, job_queue, artifact_storage)
    db.expire_all()
    assert db.get(Submission, sid).status == db.get(EvaluationJob, jid).status == SubmissionStatus.COMPLETED
    assert db.get(Submission, sid).artifact_cleanup_status == "pending"
    assert db.get(Submission, sid).artifact_deleted_at is None
    assert db.get(Submission, sid).safe_error_message is None
    assert db.get(EvaluationJob, jid).error_kind is None
    assert not job_queue.items
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "submission.artifact_cleanup_pending"))
    assert audit.after == {"code": "ARTIFACT_CLEANUP_FAILED"}
    score_before = client.get(f"/submissions/{sid}").json()["scores"]
    board_before = client.get("/tasks/sentiment/leaderboard").json()
    for url in [f"/submissions/{sid}", "/tasks/sentiment/leaderboard"]:
        response = client.get(url)
        assert "private-delete-error" not in response.text
        assert "secret-original.ipynb" not in response.text
        assert str(artifact_storage.root) not in response.text
    assert client.get(f"/admin/submissions/{sid}/download/model_zip", headers=auth_header(token)).status_code == 409
    assert client.delete(f"/admin/submissions/{sid}/artifact", headers=auth_header(token)).status_code == 409
    monkeypatch.setattr(artifact_storage, "delete_artifact", real_delete)
    if retry == "sweep":
        assert cleanup_successful_artifacts(storage=artifact_storage, db_factory=factory) == 1
    else:
        assert client.delete(f"/admin/submissions/{sid}/artifact", headers=auth_header(token)).status_code == 204
    db.expire_all()
    assert db.get(Submission, sid).artifact_cleanup_status == "deleted"
    assert db.get(Submission, sid).artifact_deleted_at is not None
    assert not artifact_storage.artifact_path(sid).exists()
    assert client.get(f"/submissions/{sid}").json()["scores"] == score_before
    assert client.get("/tasks/sentiment/leaderboard").json() == board_before


@pytest.mark.parametrize("files_already_missing", [False, True])
def test_restart_recovers_commit_before_cleanup_and_missing_files(client, committed_db, job_queue, artifact_storage, monkeypatch, files_already_missing):
    _, factory = committed_db
    setup_task(client)
    def crash(*args, **kwargs):
        raise SystemExit("simulate worker exit immediately after successful commit")
    with monkeypatch.context() as patch:
        patch.setattr("app.worker.cleanup_successful_submission", crash)
        response = upload_submission(client, "20260001")
        sid = response.json()["submission"]["id"]
        with pytest.raises(SystemExit):
            process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)
    assert (artifact_storage.artifact_path(sid) / "notebook.ipynb").is_file()
    with factory() as observer:
        assert observer.get(Submission, sid).artifact_cleanup_status == "pending"
    # Model deletion completed but cleanup DB commit was lost: missing files still succeed.
    if files_already_missing:
        artifact_storage.delete_artifact(sid)
    assert cleanup_successful_artifacts(storage=artifact_storage, db_factory=factory) == 1
    assert cleanup_successful_artifacts(storage=artifact_storage, db_factory=factory) == 0
    assert not artifact_storage.artifact_path(sid).exists()


def test_cleanup_excludes_drafts_pending_failed_and_quarantine(client, committed_db, job_queue, artifact_storage):
    db, factory = committed_db
    setup_task(client)
    draft = upload_submission(client, "20260001", kind="DRAFT").json()["submission"]["id"]
    queued = upload_submission(client, "20260001").json()["submission"]["id"]
    failed = upload_submission(client, "20260001").json()["submission"]["id"]
    queued_job = job_queue.dequeue()
    failed_job = job_queue.dequeue()
    class Reject(MockEvaluator):
        def validate_submission(self, context):
            raise ValueError("bad artifact")
    process_job(failed_job, db_factory=factory, queue=job_queue, storage=artifact_storage,
                evaluator_factory=lambda _: Reject())
    class Infected(MalwareScanner):
        def scan(self, paths):
            return MalwareScanResult(MalwareScanStatus.INFECTED, "private signature")
    app.dependency_overrides[get_malware_scanner] = lambda: Infected()
    response = upload_submission(client, "20260001")
    quarantined = response.json()["detail"]["submission_id"]
    for sid in [draft, queued, failed, quarantined]:
        assert not cleanup_successful_submission(sid, storage=artifact_storage, db_factory=factory)
    assert cleanup_successful_artifacts(storage=artifact_storage, db_factory=factory) == 0
    for sid in [draft, queued, failed]:
        assert (artifact_storage.artifact_path(sid) / "notebook.ipynb").is_file()
        assert (artifact_storage.artifact_path(sid) / "model.zip").is_file()
    assert (artifact_storage.quarantine_root / quarantined / "notebook.ipynb").is_file()
    assert (artifact_storage.quarantine_root / quarantined / "model.zip").is_file()
    db.expire_all()
    assert db.get(EvaluationJob, queued_job).status == SubmissionStatus.QUEUED
    assert db.get(Submission, failed).status == SubmissionStatus.FAILED


def test_success_commit_failure_never_deletes_artifacts(client, committed_db, job_queue, artifact_storage):
    db, factory = committed_db
    setup_task(client)
    response = upload_submission(client, "20260001")
    sid = response.json()["submission"]["id"]
    jid = job_queue.dequeue()
    db.get(EvaluationJob, jid).max_attempts = 1
    db.commit()

    def reject_success_commit(session):
        if any(isinstance(row, Submission) and row.status == SubmissionStatus.COMPLETED
               for row in session.identity_map.values()):
            raise RuntimeError("synthetic success commit failure")

    event.listen(factory, "before_commit", reject_success_commit)
    try:
        process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    finally:
        event.remove(factory, "before_commit", reject_success_commit)
    db.expire_all()
    assert db.get(Submission, sid).status == SubmissionStatus.FAILED
    assert db.get(Submission, sid).artifact_cleanup_status == "retained"
    assert db.scalar(select(Score).where(Score.submission_id == sid)) is None
    assert (artifact_storage.artifact_path(sid) / "notebook.ipynb").is_file()
    assert (artifact_storage.artifact_path(sid) / "model.zip").is_file()


def test_cleanup_db_commit_failure_recovers_missing_files(client, committed_db, job_queue, artifact_storage):
    db, factory = committed_db
    setup_task(client)

    def reject_cleanup_commit(session):
        if any(isinstance(row, Submission) and row.artifact_cleanup_status == "deleted"
               for row in session.identity_map.values()):
            raise RuntimeError("synthetic cleanup commit failure")

    event.listen(factory, "before_commit", reject_cleanup_commit)
    try:
        sid, jid = run_uploaded(client, factory, job_queue, artifact_storage)
    finally:
        event.remove(factory, "before_commit", reject_cleanup_commit)
    db.expire_all()
    assert db.get(Submission, sid).artifact_cleanup_status == "pending"
    assert db.get(EvaluationJob, jid).status == SubmissionStatus.COMPLETED
    assert not artifact_storage.artifact_path(sid).exists()
    assert cleanup_successful_artifacts(storage=artifact_storage, db_factory=factory) == 1
    db.expire_all()
    assert db.get(Submission, sid).artifact_cleanup_status == "deleted"
    assert db.get(Submission, sid).artifact_deleted_at is not None


def test_historical_success_manual_cleanup_preserves_score(client, committed_db, job_queue, artifact_storage, monkeypatch):
    db, factory = committed_db
    token = setup_task(client)
    # Simulate a success produced before cleanup existed, with retained files.
    with monkeypatch.context() as patch:
        patch.setattr("app.worker.cleanup_successful_submission", lambda *args, **kwargs: False)
        sid, jid = run_uploaded(client, factory, job_queue, artifact_storage)
    db.expire_all()
    db.get(Submission, sid).artifact_cleanup_status = "retained"
    db.commit()
    assert client.get(f"/admin/submissions/{sid}/download/notebook", headers=auth_header(token)).status_code == 409
    assert client.delete(f"/admin/submissions/{sid}/artifact", headers=auth_header(token)).status_code == 204
    db.expire_all()
    assert db.get(Submission, sid).status == db.get(EvaluationJob, jid).status == SubmissionStatus.COMPLETED
    assert db.get(Submission, sid).artifact_cleanup_status == "deleted"
    assert client.get(f"/submissions/{sid}").json()["scores"]
    assert not artifact_storage.artifact_path(sid).exists()


@pytest.mark.parametrize("status", [SubmissionStatus.RUNNING, SubmissionStatus.SCORING])
def test_active_evaluations_are_not_cleaned(client, committed_db, job_queue, artifact_storage, status):
    db, factory = committed_db
    setup_task(client)
    response = upload_submission(client, "20260001")
    sid = response.json()["submission"]["id"]
    db.get(Submission, sid).status = status
    db.get(EvaluationJob, response.json()["evaluation_job"]["id"]).status = status
    db.commit()
    assert not cleanup_successful_submission(sid, storage=artifact_storage, db_factory=factory)
    assert cleanup_successful_artifacts(storage=artifact_storage, db_factory=factory) == 0
    assert (artifact_storage.artifact_path(sid) / "notebook.ipynb").is_file()
    assert (artifact_storage.artifact_path(sid) / "model.zip").is_file()
