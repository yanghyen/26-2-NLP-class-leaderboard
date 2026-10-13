from sqlalchemy import select
from app.core.enums import UserRole
from app.core.security import create_access_token, hash_password
from app.models import User, Participant
from tests.conftest import login, auth_header, create_public_task, upload_submission


def test_admin_auth_and_student_auth_removed(client, db_session):
    token = login(client, "RootTA", "admin-password")
    assert client.get("/auth/me", headers=auth_header(token)).json()["role"] == "ADMIN"
    assert client.post("/auth/register", json={}).status_code == 404
    user = User(nickname="LegacyStudent", student_number="20260001", avatar_id="brain", role=UserRole.STUDENT, password_hash=hash_password("old-password"))
    db_session.add(user)
    db_session.commit()
    assert client.post("/auth/login", json={"student_number_or_nickname": "LegacyStudent", "password": "old-password"}).status_code == 401
    assert client.get("/auth/me", headers=auth_header(create_access_token(user.id))).status_code == 401
    paths = client.get("/openapi.json").json()["paths"]
    assert "/auth/register" not in paths and not any("join-code" in p for p in paths)


def test_first_public_upload_creates_and_reuses_participant(client, db_session):
    create_public_task(client, login(client, "RootTA", "admin-password"))
    assert db_session.scalar(select(Participant)) is None
    first = upload_submission(client, "20260001")
    assert first.status_code == 201
    participant = db_session.scalar(select(Participant))
    assert participant is not None
    from app.services.participants import get_participant
    assert get_participant(db_session, " 20260001 ", "Different", "🤖").id == participant.id
    assert participant.nickname == "NLPHero" and participant.emoji == "🧠"
    second = upload_submission(client, "20260001", nickname="APIChange", emoji="🤖")
    assert second.status_code == 201  # Pending jobs do not limit subsequent submissions.
    assert len(db_session.scalars(select(Participant)).all()) == 1
    assert participant.nickname == "NLPHero" and participant.emoji == "🧠"


def test_unknown_roster_and_reserved_nickname(client, db_session):
    from app.services.participants import get_participant
    import pytest
    with pytest.raises(ValueError, match="수강생 명단"):
        get_participant(db_session, "unknown-number", "ValidNick", "🧠")
    with pytest.raises(ValueError, match="예약"):
        get_participant(db_session, "20260001", "Admin", "🧠")
    create_public_task(client, login(client, "RootTA", "admin-password"))
    result = upload_submission(client, "unknown-number")
    assert result.status_code == 400
    assert "unknown-number" not in result.text


def test_participant_roster_unique_constraint(db_session):
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.models import CourseRoster
    roster = db_session.scalar(select(CourseRoster))
    db_session.add_all([Participant(roster_entry_id=roster.id, nickname="First", emoji="🧠"), Participant(roster_entry_id=roster.id, nickname="Second", emoji="🤖")])
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
