import os
import tempfile
import io
import json
import struct
import zipfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["APP_SECRET_KEY"] = "test-secret"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import Avatar, Base, CourseRoster, User
from app.queue import InMemoryJobQueue, get_job_queue
from app.security.malware import DisabledDevelopmentScanner, get_malware_scanner
from app.services.avatars import ensure_default_avatars
from app.services.registration import create_join_code
from app.storage import get_artifact_storage
from app.storage.local import LocalArtifactStorage


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        ensure_default_avatars(db)
        create_join_code(db, label="Fall 2026", code="JOIN-2026", deactivate_existing=True)
        db.add(CourseRoster(student_number="20260001", real_name="Kim NLP", section="A"))
        admin = User(
            nickname="RootTA",
            avatar_id="robot",
            password_hash=hash_password("admin-password"),
            role=UserRole.ADMIN,
        )
        db.add(admin)
        db.commit()
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def job_queue() -> InMemoryJobQueue:
    return InMemoryJobQueue()


@pytest.fixture()
def artifact_storage(tmp_path: Path) -> LocalArtifactStorage:
    return LocalArtifactStorage(tmp_path / "submission-storage")


@pytest.fixture()
def client(
    db_session: Session,
    job_queue: InMemoryJobQueue,
    artifact_storage: LocalArtifactStorage,
) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_job_queue] = lambda: job_queue
    app.dependency_overrides[get_artifact_storage] = lambda: artifact_storage
    app.dependency_overrides[get_malware_scanner] = lambda: DisabledDevelopmentScanner()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_student(
    client: TestClient,
    nickname: str = "NLPHero",
    student_number: str = "20260001",
    real_name: str = "Kim NLP",
) -> dict[str, str]:
    response = client.post(
        "/auth/register",
        json={
            "student_number": student_number,
            "real_name": real_name,
            "nickname": nickname,
            "avatar_id": "brain",
            "password": "student-password",
            "join_code": "JOIN-2026",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client: TestClient, login_id: str, password: str) -> str:
    response = client.post(
        "/auth/login",
        json={"student_number_or_nickname": login_id, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def notebook_bytes(outputs: list[dict] | None = None) -> bytes:
    return json.dumps(
        {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": outputs or [],
                    "source": ["print('course submission')"],
                }
            ],
        }
    ).encode()


def model_zip_bytes(
    *,
    base_model: str = "course/bert-base",
    architecture: str = "BertForSequenceClassification",
    extras: dict[str, bytes] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("submission.json", json.dumps({"base_model": base_model}))
        archive.writestr(
            "model/config.json",
            json.dumps({"_name_or_path": base_model, "architectures": [architecture]}),
        )
        archive.writestr(
            "model/model.safetensors",
            safetensors_bytes(),
        )
        for name, content in (extras or {}).items():
            archive.writestr(name, content)
    return output.getvalue()


def safetensors_bytes() -> bytes:
    header = json.dumps(
        {"classifier.weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}},
        separators=(",", ":"),
    ).encode()
    header += b" " * ((8 - len(header) % 8) % 8)
    return struct.pack("<Q", len(header)) + header + b"\0" * 4


def create_public_task(client: TestClient, admin_token: str, max_submissions: int = 5):
    return client.post(
        "/tasks",
        headers=auth_header(admin_token),
        json={
            "slug": "sentiment",
            "title": "Sentiment Analysis",
            "is_public": True,
            "max_official_submissions": max_submissions,
            "config": {
                "allowed_models": ["course/bert-base"],
                "artifact_policy": {
                    "allowed_architectures": ["BertForSequenceClassification"]
                },
                "metric_config": {"primary": "mock_score"},
            },
        },
    )


def upload_submission(
    client: TestClient,
    token: str,
    kind: str = "EVALUATION",
    notebook_content: bytes | None = None,
    model_content: bytes | None = None,
):
    return client.post(
        "/submissions/sentiment",
        headers=auth_header(token),
        data={
            "kind": kind,
            "model_name": "tiny-sentiment",
            "base_model": "course/bert-base",
            "seed": "42",
            "metadata_json": '{"task":"sentiment"}',
        },
        files={
            "notebook": (
                "solution.ipynb",
                notebook_content if notebook_content is not None else notebook_bytes(),
                "application/json",
            ),
            "model_zip": (
                "model.zip",
                model_content if model_content is not None else model_zip_bytes(),
                "application/zip",
            ),
        },
    )
