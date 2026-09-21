from sqlalchemy import select

from app.models import CourseRoster
from tests.conftest import register_student


def test_registration_requires_matching_roster_and_marks_student_registered(client, db_session):
    user = register_student(client)

    assert user["nickname"] == "NLPHero"
    roster = db_session.scalar(select(CourseRoster).where(CourseRoster.student_number == "20260001"))
    assert roster.registered_user_id == user["id"]


def test_duplicate_student_number_is_rejected(client):
    register_student(client)

    response = client.post(
        "/auth/register",
        json={
            "student_number": "20260001",
            "real_name": "Kim NLP",
            "nickname": "OtherHero",
            "avatar_id": "brain",
            "password": "student-password",
            "join_code": "JOIN-2026",
        },
    )

    assert response.status_code == 400
    assert "이미 가입" in response.json()["detail"]


def test_reserved_nickname_is_rejected(client):
    response = client.post(
        "/auth/register",
        json={
            "student_number": "20260001",
            "real_name": "Kim NLP",
            "nickname": "Admin",
            "avatar_id": "brain",
            "password": "student-password",
            "join_code": "JOIN-2026",
        },
    )

    assert response.status_code == 400
    assert "예약" in response.json()["detail"]

