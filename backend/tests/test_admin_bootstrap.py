from sqlalchemy import func, select

import pytest

from app.core.enums import UserRole
from app.core.security import verify_password
from app.models import User
from app.scripts.create_admin import (
    AdminBootstrapError,
    create_or_get_admin,
    require_development,
    reset_admin_password,
)


def test_admin_bootstrap_is_idempotent_and_does_not_reset_password(db_session):
    first, first_created = create_or_get_admin(
        db_session,
        nickname="CourseTA",
        password="first-password",
    )
    original_hash = first.password_hash

    second, second_created = create_or_get_admin(
        db_session,
        nickname="courseta",
        password="different-password",
    )

    count = db_session.scalar(
        select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
    )
    assert first_created is True
    assert second_created is False
    assert second.id == first.id
    assert second.nickname == "CourseTA"
    assert second.password_hash == original_hash
    assert verify_password("first-password", second.password_hash)
    assert not verify_password("different-password", second.password_hash)
    assert count == 2  # Includes the RootTA test fixture.


def test_admin_bootstrap_rejects_existing_student_nickname(client, db_session):
    db_session.add(User(nickname="NLPHero", avatar_id="brain", password_hash="!disabled", role=UserRole.STUDENT, is_active=False))
    db_session.commit()
    with pytest.raises(AdminBootstrapError, match="일반 계정"):
        create_or_get_admin(
            db_session,
            nickname="NLPHero",
            password="admin-password",
        )


def test_admin_password_reset_requires_explicit_operation(db_session):
    admin, _ = create_or_get_admin(
        db_session,
        nickname="ResetTA",
        password="original-password",
    )
    reset_admin_password(db_session, admin=admin, password="replacement-password")

    assert verify_password("replacement-password", admin.password_hash)
    assert not verify_password("original-password", admin.password_hash)


@pytest.mark.parametrize("app_env", ["test", "production"])
def test_admin_bootstrap_is_blocked_outside_development(app_env):
    with pytest.raises(AdminBootstrapError, match="development"):
        require_development(app_env)


def test_login_401_is_described_in_openapi_and_returned(client):
    operation = client.get("/openapi.json").json()["paths"]["/auth/login"]["post"]
    unauthorized = operation["responses"]["401"]
    schema = unauthorized["content"]["application/json"]["schema"]

    assert schema["$ref"].endswith("/ErrorResponse")
    response = client.post(
        "/auth/login",
        json={"student_number_or_nickname": "missing", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "로그인 정보가 올바르지 않습니다."}
    assert response.headers["www-authenticate"] == "Bearer"
