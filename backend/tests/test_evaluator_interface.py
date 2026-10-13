"""Public configuration errors and the Worker/evaluator contract, without model loading."""
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.enums import SubmissionStatus
from app.evaluators.base import EvaluationContext, EvaluationRequest, EvaluationResult, Evaluator
from app.evaluators.errors import EvaluatorError
from app.evaluators.mock import MockEvaluator
from app.evaluators.registry import EVALUATORS, get_evaluator
from app.models import EvaluationJob, Score, Submission, Task
from app.storage.local import LocalArtifactStorage
from app.worker import process_job
from tests.conftest import auth_header, create_public_task, login, upload_submission


@pytest.fixture()
def artifact_storage(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield LocalArtifactStorage(directory)


def request_for(digest, dataset_config=None):
    context = EvaluationContext(
        task_slug="any-title", split="PUBLIC", submission_dir=Path("validated-model"),
        dataset_config=dataset_config or {}, allowed_models=[], metric_config={}, artifact_digest=digest,
    )
    return EvaluationRequest(
        submission_id="submission", task_id="task", evaluator_key="mock_v1",
        artifact_path=context.submission_dir, validated_manifest={}, validated_metadata={}, context=context,
    )


@pytest.mark.parametrize("char,score", [
    ("0", .378423), ("1", .192272), ("a", .999517), ("f", .871209),
])
def test_mock_scores_match_checkpoint_golden_values(char, score):
    # Values generated from checkpoint b5833e7, not recomputed by a test copy of the formula.
    request = request_for(char * 64)
    result = get_evaluator("mock_v1").evaluate(request)
    assert result.primary_score == score
    assert result.primary_metric == "mock_score"
    assert result.secondary_metrics == {"mock_score": score, "deterministic": True}
    assert result.evaluator_version == "mock-v1"
    assert result.dataset_version == "mock-dataset-v1"
    assert get_evaluator("mock").evaluate(request) == result


@pytest.mark.parametrize("config", [{"version": "legacy-data"}, {"dataset_version": "legacy-data"}])
def test_configured_dataset_version_remains_compatible(config):
    assert MockEvaluator().evaluate(request_for("0" * 64, config)).dataset_version == "legacy-data"


@pytest.mark.parametrize("key,code", [
    ("/private/server/eval.py", "UNKNOWN_EVALUATOR"),
    ("__import__('os')", "UNKNOWN_EVALUATOR"),
    ("disabled_evaluator_v1", "UNKNOWN_EVALUATOR"),
    (None, "EVALUATOR_CONFIG_INVALID"), ("", "EVALUATOR_CONFIG_INVALID"),
])
def test_registry_is_explicit_and_returns_safe_errors(key, code):
    assert set(EVALUATORS) == {"mock_v1", "lab02_sentiment_v1"}
    with pytest.raises(EvaluatorError) as caught:
        get_evaluator(key)
    assert caught.value.code == code
    assert "/private" not in str(caught.value) and "__import__" not in str(caught.value)


def test_worker_calls_only_common_evaluate_interface_and_persists_result(
    client, db_session, job_queue, artifact_storage
):
    token = login(client, "RootTA", "admin-password")
    task_response = create_public_task(client, token)
    assert task_response.json()["evaluator_key"] == "mock_v1"
    response = upload_submission(client, "20260001")
    sid = response.json()["submission"]["id"]
    jid = job_queue.dequeue()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    events = []

    class InterfaceOnlyEvaluator(Evaluator):
        key = "mock_v1"
        def evaluate(self, request):
            assert isinstance(request, EvaluationRequest)
            assert request.submission_id == sid
            assert request.evaluator_key == "mock_v1"
            assert request.task_id == task_response.json()["id"]
            assert request.artifact_path == artifact_storage.artifact_path(sid) / "model_artifact"
            assert request.validated_manifest == {"base_model": "course/bert-base"}
            assert request.validated_metadata["model"]["safetensors_validated"] is True
            assert request.context.trust_remote_code is False
            events.append("evaluate")
            result = MockEvaluator().evaluate(request)
            with factory() as observer:
                assert observer.get(EvaluationJob, jid).status == SubmissionStatus.SCORING
            return result
        def cleanup(self, request):
            assert request.submission_id == sid
            events.append("cleanup")

    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage,
                evaluator_factory=lambda key: InterfaceOnlyEvaluator())
    db_session.expire_all()
    submission = db_session.get(Submission, sid)
    score = db_session.scalar(select(Score).where(Score.submission_id == sid))
    assert events == ["evaluate", "cleanup"]
    assert submission.status == db_session.get(EvaluationJob, jid).status == SubmissionStatus.COMPLETED
    assert submission.evaluator_version == "mock-v1" and submission.dataset_version == "mock-dataset-v1"
    assert score.metrics == {"mock_score": score.primary_score, "deterministic": True}
    assert submission.artifact_cleanup_status == "deleted"
    assert not artifact_storage.artifact_path(sid).exists()
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["primary_score"] == score.primary_score


@pytest.mark.parametrize("key,code", [
    ("private.module.evaluator", "UNKNOWN_EVALUATOR"),
    ("lab02_sentiment_v1", "EVALUATOR_CONFIG_INVALID"),
])
def test_legacy_bad_task_config_is_refused_at_upload_and_worker(
    client, db_session, job_queue, artifact_storage, key, code
):
    token = login(client, "RootTA", "admin-password")
    create_public_task(client, token)
    response = upload_submission(client, "20260001")
    sid = response.json()["submission"]["id"]
    jid = job_queue.dequeue()
    task = db_session.scalar(select(Task))
    task.evaluator_key = key
    db_session.commit()
    refused = upload_submission(client, "20260001")
    assert refused.status_code == 400 and refused.json()["detail"]["code"] == code
    assert key not in refused.text
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    job = db_session.get(EvaluationJob, jid)
    assert job.status == SubmissionStatus.FAILED and job.error_kind == code
    assert job.attempts == 1 and not job_queue.items
    assert db_session.scalar(select(Score).where(Score.submission_id == sid)) is None
    public = client.get(f"/submissions/{sid}")
    assert public.json()["status"] == "FAILED"
    assert key not in public.text and "Traceback" not in public.text
    assert str(artifact_storage.root) not in public.text
    assert artifact_storage.artifact_path(sid).is_dir()


def task_payload(key):
    return {
        "slug": "sentiment", "title": "Lab02 sentiment title is not evaluator selection",
        "is_public": True, "evaluator_key": key,
        "config": {"allowed_models": ["course/bert-base"],
                   "artifact_policy": {"allowed_architectures": ["BertForSequenceClassification"]}},
    }


@pytest.mark.parametrize("key,code", [
    ("/private/server/eval.py", "UNKNOWN_EVALUATOR"),
    ("lab02_sentiment_v1", "EVALUATOR_CONFIG_INVALID"),
    (None, "EVALUATOR_CONFIG_INVALID"), ("", "EVALUATOR_CONFIG_INVALID"),
    ({"module": "/private/unsafe.py"}, "EVALUATOR_CONFIG_INVALID"),
])
def test_create_and_update_reject_bad_selection_without_echoing_inputs(client, db_session, key, code):
    token = login(client, "RootTA", "admin-password")
    headers = auth_header(token)
    response = client.post("/tasks", headers=headers, json=task_payload(key))
    assert response.status_code == 400 and response.json()["detail"]["code"] == code
    assert db_session.scalar(select(Task)) is None
    create_public_task(client, token)
    response = client.patch("/tasks/sentiment", headers=headers,
                            json={"evaluator_key": key, "title": "Must not be saved"})
    assert response.status_code == 400 and response.json()["detail"]["code"] == code
    assert "/private" not in response.text and "Traceback" not in response.text
    db_session.expire_all()
    assert db_session.scalar(select(Task)).title == "Sentiment Analysis"
    assert db_session.scalar(select(Task)).evaluator_key == "mock_v1"


def test_legacy_mock_key_canonicalizes_on_create_and_update(client):
    token = login(client, "RootTA", "admin-password")
    response = client.post("/tasks", headers=auth_header(token), json=task_payload("mock"))
    assert response.status_code == 201 and response.json()["evaluator_key"] == "mock_v1"
    response = client.patch("/tasks/sentiment", headers=auth_header(token), json={"evaluator_key": "mock"})
    assert response.status_code == 200 and response.json()["evaluator_key"] == "mock_v1"


def test_worker_accepts_a_one_shot_result_without_legacy_phase_methods(
    client, db_session, job_queue, artifact_storage
):
    create_public_task(client, login(client, "RootTA", "admin-password"))
    response = upload_submission(client, "20260001")
    sid = response.json()["submission"]["id"]
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    class OneShot(Evaluator):
        key = "mock_v1"
        def evaluate(self, request):
            return EvaluationResult("synthetic_metric", .5, {"synthetic": True}, "test-v1", "test-data-v1")
    process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage,
                evaluator_factory=lambda _: OneShot())
    db_session.expire_all()
    submission = db_session.get(Submission, sid)
    assert submission.status == SubmissionStatus.COMPLETED
    assert submission.evaluator_version == "test-v1" and submission.dataset_version == "test-data-v1"
    assert db_session.scalar(select(Score).where(Score.submission_id == sid)).primary_score == .5
