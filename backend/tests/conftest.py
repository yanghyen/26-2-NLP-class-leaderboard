import os
import tempfile
from collections.abc import Generator

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
from app.services.avatars import ensure_default_avatars
from app.services.registration import create_join_code


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
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_student(client: TestClient, nickname: str = "NLPHero") -> dict[str, str]:
    response = client.post(
        "/auth/register",
        json={
            "student_number": "20260001",
            "real_name": "Kim NLP",
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
