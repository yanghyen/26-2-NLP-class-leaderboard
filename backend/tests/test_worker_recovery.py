"""Durable dispatch, interrupted attempts and stale-result fencing."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.enums import SubmissionStatus
from app.evaluators.mock import MockEvaluator
from app.models import EvaluationJob, Score, Submission
from app.worker import process_job, recover_jobs
from tests.test_submission_pipeline import setup_student_and_task
from tests.conftest import auth_header, login, upload_submission


def setup_job(client, db_session, job_queue):
    setup_student_and_task(client)
    response = upload_submission(client, '20260001', kind='BASELINE_PRACTICE')
    assert response.status_code == 201
    sid = response.json()['submission']['id']
    jid = job_queue.dequeue()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    return sid, jid, factory


def test_recovery_redispatches_job_lost_after_dequeue(client, db_session, job_queue, artifact_storage):
    sid, jid, factory = setup_job(client, db_session, job_queue)
    recover_jobs(db_factory=factory, queue=job_queue)
    assert job_queue.dequeue() == jid
    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    assert db_session.get(EvaluationJob, jid).attempts == 1
    assert len(db_session.scalars(select(Score).where(Score.submission_id == sid)).all()) == 1


@pytest.mark.parametrize('phase', [SubmissionStatus.RUNNING, SubmissionStatus.SCORING])
def test_expired_attempt_retries_but_live_attempt_is_untouched(client, db_session, job_queue, artifact_storage, phase):
    sid, jid, factory = setup_job(client, db_session, job_queue)
    job = db_session.get(EvaluationJob, jid)
    job.status = job.submission.status = phase
    job.attempts = 1
    job.locked_at = datetime.now(UTC)
    db_session.commit()
    start = job.locked_at
    recover_jobs(db_factory=factory, queue=job_queue, now=start + timedelta(seconds=job.submission.task.timeout_seconds + 29))
    assert job_queue.dequeue() is None
    stale = artifact_storage.create_work_dir(f'{jid}-1')
    (stale / 'partial').write_text('interrupted scratch')
    recover_jobs(db_factory=factory, queue=job_queue, now=start + timedelta(seconds=job.submission.task.timeout_seconds + 31))
    assert job_queue.dequeue() == jid
    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    assert db_session.get(Submission, sid).status == SubmissionStatus.COMPLETED
    assert db_session.get(EvaluationJob, jid).attempts == 2
    assert not stale.exists()
    assert not artifact_storage.artifact_path(sid).exists()


def test_repeated_interruptions_exhaust_retry_without_score_or_deletion(client, db_session, job_queue, artifact_storage):
    sid, jid, factory = setup_job(client, db_session, job_queue)
    job = db_session.get(EvaluationJob, jid)
    job.status = job.submission.status = SubmissionStatus.SCORING
    job.attempts = job.max_attempts
    job.locked_at = datetime.now(UTC) - timedelta(seconds=job.submission.task.timeout_seconds + 31)
    db_session.commit()
    recover_jobs(db_factory=factory, queue=job_queue)
    db_session.expire_all()
    assert db_session.get(EvaluationJob, jid).error_kind == 'WORKER_INTERRUPTED'
    assert db_session.get(Submission, sid).status == SubmissionStatus.FAILED
    assert db_session.scalar(select(Score).where(Score.submission_id == sid)) is None
    assert artifact_storage.artifact_path(sid).exists()
    assert job_queue.dequeue() is None
    token = login(client, 'RootTA', 'admin-password')
    retry = client.post(f'/admin/jobs/{jid}/retry', headers=auth_header(token))
    assert retry.status_code == 200
    assert job_queue.dequeue() == jid


def test_resumed_old_attempt_cannot_score_or_fail_new_attempt(client, db_session, job_queue, artifact_storage):
    sid, jid, factory = setup_job(client, db_session, job_queue)
    class Superseded(MockEvaluator):
        def evaluate(self, request):
            with factory() as other:
                job = other.get(EvaluationJob, jid)
                job.attempts += 1
                other.commit()
            return super().evaluate(request)
    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage,
                evaluator_factory=lambda _: Superseded())
    db_session.expire_all()
    assert db_session.get(EvaluationJob, jid).attempts == 2
    assert db_session.get(EvaluationJob, jid).status == SubmissionStatus.RUNNING
    assert db_session.scalar(select(Score).where(Score.submission_id == sid)) is None
    assert artifact_storage.artifact_path(sid).exists()
