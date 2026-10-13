"""Upgrade an existing populated 0004 DB without losing files or result metadata."""
from datetime import datetime

from sqlalchemy import MetaData, Table, create_engine, select, text
from sqlalchemy.orm import Session

from app.models import EvaluationJob, Score, Submission, SubmissionFile
from tests.test_participant_migration import migrate


def test_existing_db_cleanup_migration_preserves_records(tmp_path):
    path = tmp_path / "retention-migration.db"
    url = f"sqlite:///{path}"
    migrate(url, "0004_roster_participants")
    engine = create_engine(url)
    metadata = MetaData()
    tables = {name: Table(name, metadata, autoload_with=engine) for name in
              ["tasks", "submissions", "evaluation_jobs", "scores", "submission_files"]}
    with engine.begin() as db:
        db.execute(tables["tasks"].insert().values(
            id="task", slug="retention-test", title="Retention", description="", stage="DEVELOPMENT",
            is_public=True, max_official_submissions=5, max_zip_bytes=1000000,
            timeout_seconds=900, public_leaderboard_visible=True,
            private_leaderboard_visible=False, evaluator_key="mock"
        ))
        db.execute(tables["submissions"].insert().values(
            id="success", task_id="task", kind="EVALUATION", status="COMPLETED",
            submission_number=1, model_name="kept-model", metadata_json={"safe": True},
            artifact_digest="a" * 64, validation_report={"model": {"base_model": "course/bert-base"}},
            official_attempt_consumed=False, completed_at=datetime(2026, 10, 13)
        ))
        db.execute(tables["evaluation_jobs"].insert().values(
            id="job", submission_id="success", split="PUBLIC", status="COMPLETED", attempts=1, max_attempts=2
        ))
        db.execute(tables["scores"].insert().values(
            id="score", submission_id="success", split="PUBLIC", primary_metric="mock_score",
            primary_score=.8, metrics={"secondary": .7}, visible_to_student=True
        ))
        db.execute(tables["submission_files"].insert().values(
            id="file", submission_id="success", file_type="notebook", original_filename="safe.ipynb",
            storage_path="success/notebook.ipynb", size_bytes=100, checksum_sha256="b" * 64
        ))
    migrate(url, "head")
    with Session(engine) as db:
        submission = db.get(Submission, "success")
        assert submission.artifact_cleanup_status == "retained"
        assert submission.artifact_deleted_at is None
        assert submission.evaluator_version is None and submission.dataset_version is None
        assert submission.model_name == "kept-model" and submission.artifact_digest == "a" * 64
        assert submission.validation_report["model"]["base_model"] == "course/bert-base"
        assert db.get(Score, "score").metrics == {"secondary": .7}
        assert db.get(EvaluationJob, "job").submission_id == "success"
        assert db.get(SubmissionFile, "file").checksum_sha256 == "b" * 64
        assert db.execute(text("PRAGMA foreign_key_check")).all() == []
        assert db.scalar(select(Submission.id)) == "success"
    engine.dispose()
    path.unlink()
