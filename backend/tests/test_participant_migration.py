"""Use disposable databases; never mutate backend/dev.db."""
import os
from pathlib import Path
from runpy import run_path
import subprocess
import sys
from datetime import UTC, datetime
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
from app.models import Participant, Submission, Score, EvaluationJob, SubmissionFile, BaselineReference, User


def migrate(url, revision):
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=Path(__file__).parents[1], env={**os.environ, "DATABASE_URL": url}, check=True, capture_output=True)


def assert_legacy_migration(url):
    migrate(url, "0003_backfill_test_task_policy")
    old = run_path(str(Path(__file__).parents[1] / "alembic/initial_schema.py"))
    engine = create_engine(url)
    with Session(engine) as db:
        avatar = old["Avatar"](id="synthetic", emoji="🧠", label="Synthetic")
        db.add(avatar)
        user = old["User"](nickname="Migrated", student_number="001234", avatar_id="synthetic", password_hash="old-hash", role=old["UserRole"].STUDENT)
        orphan = old["User"](nickname="Unmapped", student_number="009999", avatar_id="synthetic", password_hash="old-hash", role=old["UserRole"].STUDENT)
        db.add_all([user, orphan]); db.flush()
        db.add(old["CourseRoster"](student_number="001234", real_name="Synthetic", registered_user_id=user.id))
        task = old["Task"](slug="synthetic", title="Migration test")
        db.add(task); db.flush()
        submission = old["Submission"](user_id=user.id, task_id=task.id, submission_number=1, kind=old["SubmissionKind"].BASELINE_PRACTICE,
            status=old["SubmissionStatus"].COMPLETED, completed_at=datetime.now(UTC))
        unmapped = old["Submission"](user_id=orphan.id, task_id=task.id, submission_number=1, kind=old["SubmissionKind"].EVALUATION, status=old["SubmissionStatus"].FAILED)
        db.add_all([submission, unmapped]); db.flush()
        score = old["Score"](submission_id=submission.id, split=old["EvaluationSplit"].SMOKE, primary_metric="mock", primary_score=.5)
        job = old["EvaluationJob"](submission_id=submission.id, split=old["EvaluationSplit"].SMOKE, status=old["SubmissionStatus"].COMPLETED)
        artifact = old["SubmissionFile"](submission_id=submission.id, file_type="notebook", original_filename="safe.ipynb", storage_path="untouched/path", size_bytes=10, checksum_sha256="0"*64)
        db.add_all([score, job, artifact]); db.flush()
        ids = [submission.id, unmapped.id, score.id, job.id, artifact.id, user.id]
        db.commit()
    migrate(url, "head")
    with Session(engine) as db:
        participant = db.scalar(select(Participant))
        assert participant.roster_entry.student_number == "001234"
        assert db.get(Submission, ids[0]).participant_id == participant.id
        assert db.get(Submission, ids[1]).participant_id is None
        assert db.get(Score, ids[2]).submission_id == ids[0]
        assert db.get(EvaluationJob, ids[3]).submission_id == ids[0]
        assert db.get(SubmissionFile, ids[4]).storage_path == "untouched/path"
        assert db.get(User, ids[5]).password_hash == "!disabled-student-auth"
        assert db.get(User, ids[5]).is_active is False
        assert db.scalar(select(BaselineReference)).submission_id == ids[0]
        if engine.dialect.name == "sqlite":
            assert db.execute(text("PRAGMA foreign_key_check")).all() == []
    engine.dispose()


def test_sqlite_migration_preserves_legacy_relationships(tmp_path):
    assert_legacy_migration(f"sqlite:///{tmp_path / 'legacy.db'}")


def test_fresh_sqlite_migration_matches_orm(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    migrate(url, "head")
    result = subprocess.run([sys.executable, "-m", "alembic", "check"], cwd=Path(__file__).parents[1], env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
