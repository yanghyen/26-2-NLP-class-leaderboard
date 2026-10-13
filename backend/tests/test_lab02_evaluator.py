"""Network-independent real torch/Transformers/safetensors CPU loading and inference."""
import io
import json
import os
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import torch
from safetensors.torch import load_file, save_file
from sqlalchemy import select, event
from sqlalchemy.orm import sessionmaker
from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

from app.core.config import get_settings
from app.core.enums import EvaluationSplit, SubmissionKind, SubmissionStatus
from app.evaluators.errors import EvaluatorError
from app.evaluators.lab02 import run_subprocess
from app.evaluators.lab02_policy import evaluation_identity
from app.evaluators.lab02_runtime import classification_metrics, infer_and_score, load_weights
from app.evaluators.local_data import load_dataset, read_records
from app.evaluators.registry import get_evaluator
from app.models import EvaluationJob, Score, Submission, Task
from app.scripts.prepare_lab02 import publish_dataset
from app.storage.local import LocalArtifactStorage
from app.worker import process_job
from tests.conftest import auth_header, login, upload_submission


@pytest.fixture()
def artifact_storage(tmp_path):
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield LocalArtifactStorage(directory)


@pytest.fixture()
def tiny(tmp_path, monkeypatch):
    root = tmp_path / "server"
    root.mkdir()
    vocab = ["[PAD]", "[UNK]", "[CLS]", "[SEP]", "[MASK]", "good", "bad", "movie", "<", ">", "br", "/"]
    (root / "vocab.txt").write_text("\n".join(vocab) + "\n")
    tokenizer = BertTokenizerFast(vocab_file=str(root / "vocab.txt"), do_lower_case=True)
    tokenizer.save_pretrained(root)
    config = BertConfig(vocab_size=len(vocab), hidden_size=8, num_hidden_layers=1,
                        num_attention_heads=2, intermediate_size=16, max_position_embeddings=512,
                        num_labels=2, id2label={0: "negative", 1: "positive"},
                        label2id={"negative": 0, "positive": 1})
    config.architectures = ["BertForSequenceClassification"]
    config.to_json_file(root / "config.json")
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    model = BertForSequenceClassification(config)
    save_file({k: v.contiguous() for k, v in model.state_dict().items()}, str(artifact / "model.safetensors"))
    (artifact / "config.json").write_bytes((root / "config.json").read_bytes())
    manifest = json.loads((Path(__file__).parent / "fixtures/lab02/manifest.json").read_text())
    (artifact / "manifest.json").write_text(json.dumps(manifest))
    dataset_config = publish_dataset([dict(text="good movie<br />", label=1), dict(text="bad movie", label=0)],
                                     tmp_path / "data", version="tiny-cpu-smoke-v1", source="local")
    monkeypatch.setenv("LAB02_RESOURCES_ROOT", str(root))
    monkeypatch.setenv("LAB02_BATCH_SIZE", "2")
    get_settings.cache_clear()
    try:
        yield root, artifact, json.loads((root / "config.json").read_text()), dataset_config
    finally:
        get_settings.cache_clear()


def run_tiny(tiny, **kwargs):
    root, artifact, config, dataset_config = tiny
    texts, labels, _ = load_dataset(dataset_config)
    return infer_and_score(artifact, texts, labels, server_config=config, tokenizer_dir=root,
                           device="cpu", batch_size=kwargs.get("batch_size", 2), seed=42)


def test_registry_activates_real_evaluator_without_changing_mock():
    assert get_evaluator("lab02_sentiment_v1").key == "lab02_sentiment_v1"
    assert get_evaluator("mock") is get_evaluator("mock_v1")


@pytest.mark.parametrize("paths,status", [(1, 422), ({}, 422), ([{}], 422), (["manifest.json"], 400)])
def test_malformed_lab02_policy_has_a_safe_configuration_error(client, tiny, paths, status):
    from app.evaluators.lab02_policy import validate_task_config
    policy = {"allowed_architectures": ["BertForSequenceClassification"], "allowed_paths": paths}
    with pytest.raises(EvaluatorError) as caught:
        validate_task_config(tiny[3], {"primary": "macro_f1", "scale": "0_1"},
                             ["google-bert/bert-base-uncased"], policy)
    assert caught.value.code == "EVALUATOR_CONFIG_INVALID"
    token = login(client, "RootTA", "admin-password")
    response = client.post("/tasks", headers=auth_header(token), json={
        "slug": "bad-policy", "title": "Invalid policy", "evaluator_key": "lab02_sentiment_v1",
        "config": {"dataset_config": tiny[3], "allowed_models": ["google-bert/bert-base-uncased"],
                   "artifact_policy": policy,
                   "metric_config": {"primary": "macro_f1", "scale": "0_1"}},
    })
    assert response.status_code == status
    if status == 400:
        assert response.json()["detail"]["code"] == "EVALUATOR_CONFIG_INVALID"
    assert str(tiny[0]) not in response.text and "Traceback" not in response.text


@pytest.mark.parametrize("labels,predictions,f1,accuracy", [
    ([0, 0, 1, 1], [0, 1, 1, 1], (2/3 + 4/5)/2, .75),
    ([0, 0], [0, 0], .5, 1), ([0, 1], [1, 0], 0, 0),
])
def test_macro_f1_uses_both_labels_over_the_whole_dataset(labels, predictions, f1, accuracy):
    result = classification_metrics(labels, predictions)
    assert result["macro_f1"] == pytest.approx(f1)
    assert result["accuracy"] == accuracy


@pytest.mark.parametrize("content", [b"", b"{}\n", b'{"text":"", "label":0}\n',
    b'{"text":"x", "label":true}\n', b'{"text":"x", "label":2}\n', b'{"text":"x", "label":"0"}\n'])
def test_invalid_local_data_is_not_silently_skipped(tmp_path, content):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(content)
    with pytest.raises(EvaluatorError) as caught:
        read_records(path)
    assert caught.value.code == "EVALUATION_DATA_INVALID"
    assert str(path) not in str(caught.value)


def test_local_hash_count_and_metadata_are_verified(tiny):
    config = tiny[3]
    texts, labels, metadata = load_dataset(config)
    assert texts[0] == "good movie<br />" and labels == [1, 0]
    Path(config["path"]).write_text('{"text":"changed", "label":1}\n')
    with pytest.raises(EvaluatorError):
        load_dataset(config)


def test_real_cpu_safetensors_loading_and_inference_are_batch_invariant(tiny):
    first = run_tiny(tiny, batch_size=1)
    second = run_tiny(tiny, batch_size=2)
    assert first["sample_count"] == 2 and first["metrics"] == second["metrics"]
    assert 0 <= first["metrics"]["macro_f1"] <= 1


def test_fixed_tokenizer_truncates_right_and_counts_special_tokens(tiny, monkeypatch):
    actual = BertTokenizerFast.from_pretrained(str(tiny[0]), local_files_only=True)
    observations = []
    class RecordingTokenizer:
        def __call__(self, texts, **kwargs):
            observations.append((texts, kwargs))
            encoded = actual(texts, **kwargs)
            assert encoded["input_ids"].shape[1] <= 128
            return encoded
    def load(*args, **kwargs):
        assert kwargs["local_files_only"] is True and kwargs["trust_remote_code"] is False
        assert kwargs["truncation_side"] == "right"
        return RecordingTokenizer()
    monkeypatch.setattr(BertTokenizerFast, "from_pretrained", load)
    text = "good " * 200 + "<br />bad"
    infer_and_score(tiny[1], [text], [1], server_config=tiny[2], tokenizer_dir=tiny[0], device="cpu", batch_size=2, seed=42)
    assert observations[0][0] == [text]
    assert observations[0][1]["max_length"] == 128 and observations[0][1]["add_special_tokens"] is True


@pytest.mark.parametrize("corruption", ["missing", "extra", "shape", "nan", "inf", "dtype"])
def test_invalid_real_weights_are_rejected(tiny, corruption):
    path = tiny[1] / "model.safetensors"
    state = load_file(str(path))
    key = "classifier.weight"
    if corruption == "missing": del state[key]
    elif corruption == "extra": state["unexpected"] = torch.ones(1)
    elif corruption == "shape": state[key] = torch.zeros(3, 8)
    elif corruption in {"nan", "inf"}: state[key][0, 0] = float(corruption)
    else: state[key] = state[key].to(torch.int32)
    # Avoid overwriting a memory-mapped file while its tensors are still backed by it.
    changed = tiny[1] / "changed.safetensors"
    save_file(state, str(changed))
    model = BertForSequenceClassification(BertConfig.from_dict(tiny[2]))
    with pytest.raises(EvaluatorError) as caught:
        load_weights(model, changed)
    assert caught.value.code == "MODEL_WEIGHTS_INVALID"


def test_cuda_unavailable_and_oom_are_safe(tiny, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(EvaluatorError) as caught:
        infer_and_score(tiny[1], ["good"], [1], server_config=tiny[2], tokenizer_dir=tiny[0], device="cuda", batch_size=2, seed=42)
    assert caught.value.code == "EVALUATOR_CONFIG_INVALID"
    def oom(*args): raise torch.cuda.OutOfMemoryError()
    monkeypatch.setattr("app.evaluators.lab02_runtime.load_weights", oom)
    with pytest.raises(EvaluatorError) as caught:
        run_tiny(tiny)
    assert caught.value.code == "EVALUATION_RESOURCE_LIMIT"


def test_nonfinite_logits_never_produce_a_partial_score(tiny, monkeypatch):
    from types import SimpleNamespace
    def forward(self, input_ids, **kwargs):
        return SimpleNamespace(logits=torch.full((input_ids.shape[0], 2), float("nan")))
    monkeypatch.setattr(BertForSequenceClassification, "forward", forward)
    with pytest.raises(EvaluatorError) as caught:
        run_tiny(tiny)
    assert caught.value.code == "MODEL_WEIGHTS_INVALID"


def test_student_config_cannot_override_server_dimensions(tiny):
    config = json.loads((tiny[1] / "config.json").read_text())
    config["hidden_size"] = 768
    (tiny[1] / "config.json").write_text(json.dumps(config))
    with pytest.raises(EvaluatorError) as caught:
        run_tiny(tiny)
    assert caught.value.code == "LAB02_CONFIG_INVALID"


def test_imdb_preparation_uses_only_pinned_test_file_and_distinct_smoke_identity(tmp_path, monkeypatch):
    import datasets
    import huggingface_hub
    from app.scripts.prepare_lab02 import prepare_imdb
    from app.evaluators.lab02_policy import IMDB_REVISION
    calls = []
    def download(*args, **kwargs):
        calls.append(kwargs)
        return str(tmp_path / "test.parquet")
    class FixtureDataset:
        def __iter__(self):
            return iter([dict(text="review", label=index % 2) for index in range(25000)])
        def select(self, indices):
            return [dict(text="review", label=index % 2) for index in indices]
    def load(name, **kwargs):
        assert name == "parquet" and kwargs["split"] == "test"
        assert kwargs["data_files"] == {"test": str(tmp_path / "test.parquet")}
        return FixtureDataset()
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(datasets, "load_dataset", load)
    full = prepare_imdb(tmp_path / "full")
    smoke = prepare_imdb(tmp_path / "smoke", limit=2)
    assert full["sample_count"] == 25000 and smoke["sample_count"] == 2
    assert full["version"] != smoke["version"] and full["sha256"] != smoke["sha256"]
    assert calls[0]["revision"] == IMDB_REVISION and calls[0]["filename"] == "plain_text/test-00000-of-00001.parquet"


def setup_lab_task(client, tiny):
    token = login(client, "RootTA", "admin-password")
    response = client.post("/tasks", headers=auth_header(token), json={
        "slug": "sentiment", "title": "Lab2 real", "is_public": True, "evaluator_key": "lab02_sentiment_v1",
        "config": {"dataset_config": tiny[3], "allowed_models": ["google-bert/bert-base-uncased"],
                   "artifact_policy": {"allowed_architectures": ["BertForSequenceClassification"]},
                   "metric_config": {"primary": "macro_f1", "scale": "0_1"}},
    })
    assert response.status_code == 201, response.text
    return token


def upload_tiny(client, tiny, kind="EVALUATION"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("manifest.json", "config.json", "model.safetensors"):
            archive.writestr(name, (tiny[1] / name).read_bytes())
    response = upload_submission(client, "20260001", kind=kind, model_content=stream.getvalue())
    assert response.status_code == 201, response.text
    return response.json()["submission"]["id"]


def fixture_subprocess(payload, **kwargs):
    return run_subprocess(payload, module="tests.lab02_test_runner", **kwargs)


def test_worker_real_cpu_subprocess_stores_metadata_and_cleans_artifact(client, db_session, job_queue, artifact_storage, tiny, monkeypatch):
    setup_lab_task(client, tiny)
    monkeypatch.setattr("app.evaluators.lab02.run_subprocess", fixture_subprocess)
    sid = upload_tiny(client, tiny)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    submission = db_session.get(Submission, sid)
    assert submission.status == SubmissionStatus.COMPLETED
    assert (submission.evaluator_version, submission.dataset_version) == evaluation_identity(tiny[3])
    score = db_session.scalar(select(Score).where(Score.submission_id == sid))
    assert score.primary_metric == "macro_f1" and "accuracy" in score.metrics
    assert submission.validation_report["evaluation"]["sample_count"] == 2
    assert submission.validation_report["evaluation"]["dataset_sha256"] == tiny[3]["sha256"]
    assert not artifact_storage.artifact_path(sid).exists() and not any(artifact_storage.work_root.iterdir())
    detail = client.get(f"/submissions/{sid}")
    assert detail.json()["scores"][0]["metrics"] == {}
    for private in [str(tiny[0]), "good movie", "dataset_sha256", "libraries", "predictions"]:
        assert private not in detail.text
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["primary_metric"] == "macro_f1"


def test_timeout_kills_real_child_and_next_job_can_run(client, db_session, job_queue, artifact_storage, tiny, monkeypatch, tmp_path):
    setup_lab_task(client, tiny)
    sid = upload_tiny(client, tiny)
    jid = job_queue.dequeue()
    pid_file = tmp_path / "child.pid"
    def hang(payload, **kwargs):
        payload.update(test_mode="sleep", pid_file=str(pid_file))
        kwargs["deadline"] = time.monotonic() + 1
        return run_subprocess(payload, module="tests.lab02_test_runner", **kwargs)
    monkeypatch.setattr("app.evaluators.lab02.run_subprocess", hang)
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    assert db_session.get(EvaluationJob, jid).error_kind == "EVALUATION_TIMEOUT"
    with pytest.raises(ProcessLookupError): os.kill(int(pid_file.read_text()), 0)
    assert not any(artifact_storage.work_root.iterdir())
    assert artifact_storage.artifact_path(sid).is_dir()
    monkeypatch.setattr("app.evaluators.lab02.run_subprocess", fixture_subprocess)
    second = upload_tiny(client, tiny)
    process_job(job_queue.dequeue(), db_factory=factory, queue=job_queue, storage=artifact_storage)
    db_session.expire_all()
    assert db_session.get(Submission, second).status == SubmissionStatus.COMPLETED


def test_aggregation_never_mixes_mock_old_data_or_old_evaluator(client, db_session, tiny):
    setup_lab_task(client, tiny)
    from tests.conftest import prepare_participant
    pid = prepare_participant(client)["id"]
    task = db_session.scalar(select(Task))
    version, data = evaluation_identity(tiny[3])
    for number, ev, ds, value in [(1, "mock-v1", "mock-dataset-v1", .99), (2, version, "old-data", .98),
                                  (3, "old-evaluator", data, .97), (4, version, data, .6)]:
        submission = Submission(participant_id=pid, task_id=task.id, submission_number=number,
                                kind=SubmissionKind.EVALUATION, status=SubmissionStatus.COMPLETED,
                                evaluator_version=ev, dataset_version=ds)
        db_session.add(submission); db_session.flush()
        db_session.add(Score(submission_id=submission.id, split=EvaluationSplit.PUBLIC,
                             primary_metric="macro_f1", primary_score=value, metrics={}))
    db_session.commit()
    assert client.get("/tasks/sentiment/leaderboard").json()[0]["primary_score"] == .6
    task.config.dataset_config = {**tiny[3], "version": "replacement"}
    db_session.commit()
    assert client.get("/tasks/sentiment/leaderboard").json() == []


def test_score_commit_server_failure_retries_without_deleting_or_duplicate_score(client, db_session, job_queue, artifact_storage, tiny, monkeypatch):
    setup_lab_task(client, tiny)
    monkeypatch.setattr("app.evaluators.lab02.run_subprocess", fixture_subprocess)
    sid = upload_tiny(client, tiny)
    jid = job_queue.dequeue()
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    failed = []
    def fail_once(session):
        if not failed and any(isinstance(row, Submission) and row.status == SubmissionStatus.COMPLETED
                              for row in session.identity_map.values()):
            failed.append(True)
            raise RuntimeError("Synthetic commit interruption")
    event.listen(factory, "before_commit", fail_once)
    try:
        process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
        db_session.expire_all()
        assert db_session.get(Submission, sid).status == SubmissionStatus.QUEUED
        assert artifact_storage.artifact_path(sid).exists()
        assert db_session.scalar(select(Score).where(Score.submission_id == sid)) is None
        assert job_queue.dequeue() == jid
        process_job(jid, db_factory=factory, queue=job_queue, storage=artifact_storage)
    finally:
        event.remove(factory, "before_commit", fail_once)
    db_session.expire_all()
    assert db_session.get(Submission, sid).status == SubmissionStatus.COMPLETED
    assert db_session.get(Submission, sid).safe_error_message is None
    assert len(db_session.scalars(select(Score).where(Score.submission_id == sid)).all()) == 1
    assert not artifact_storage.artifact_path(sid).exists()
