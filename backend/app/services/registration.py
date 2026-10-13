from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.security import verify_password
from app.models import User

RESERVED_NICKNAMES = {"admin", "ta", "professor", "baseline", "administrator", "staff"}


class RegistrationError(ValueError):
    pass


def normalize_name(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_nickname(value: str) -> str:
    return normalize_name(value)


def validate_nickname(value: str) -> str:
    nickname = normalize_nickname(value)
    if not 2 <= len(nickname) <= 16:
        raise RegistrationError("닉네임은 2~16자여야 합니다.")
    if nickname.casefold() in RESERVED_NICKNAMES:
        raise RegistrationError("사용할 수 없는 예약 닉네임입니다.")
    if any(word in nickname.casefold() for word in ("admin", "professor", "baseline")):
        raise RegistrationError("관리자 또는 baseline으로 오해될 수 있는 닉네임은 사용할 수 없습니다.")
    return nickname


def authenticate_user(db: Session, login: str, password: str) -> User | None:
    user = db.scalar(
        select(User).where(User.nickname == login.strip(), User.role == UserRole.ADMIN)
    )
    if user is None or not user.is_active or user.role != UserRole.ADMIN:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

