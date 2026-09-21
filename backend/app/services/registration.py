from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.security import constant_time_hash, hash_password, verify_password
from app.models import Avatar, CourseRoster, JoinCode, User
from app.schemas import RegisterIn

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


def active_join_code_matches(db: Session, code: str) -> bool:
    code_hash = constant_time_hash(code)
    rows = db.scalars(select(JoinCode).where(JoinCode.is_active.is_(True))).all()
    return any(row.code_hash == code_hash for row in rows)


def create_join_code(
    db: Session, *, label: str, code: str, deactivate_existing: bool = True
) -> JoinCode:
    if deactivate_existing:
        for row in db.scalars(select(JoinCode).where(JoinCode.is_active.is_(True))).all():
            row.is_active = False
    join_code = JoinCode(label=label, code_hash=constant_time_hash(code), is_active=True)
    db.add(join_code)
    db.commit()
    db.refresh(join_code)
    return join_code


def register_student(db: Session, payload: RegisterIn) -> User:
    student_number = payload.student_number.strip()
    real_name = normalize_name(payload.real_name)
    nickname = validate_nickname(payload.nickname)

    if not active_join_code_matches(db, payload.join_code):
        raise RegistrationError("가입 코드가 올바르지 않거나 비활성화되었습니다.")

    roster = db.scalar(
        select(CourseRoster).where(
            CourseRoster.student_number == student_number,
            CourseRoster.real_name == real_name,
        )
    )
    if roster is None:
        raise RegistrationError("학번과 본명이 수강생 명단과 일치하지 않습니다.")
    if roster.registered_user_id is not None:
        raise RegistrationError("이미 가입된 학번입니다.")

    avatar = db.get(Avatar, payload.avatar_id)
    if avatar is None or not avatar.is_active:
        raise RegistrationError("선택할 수 없는 프로필 이모지입니다.")

    existing = db.scalar(
        select(User).where(or_(User.student_number == student_number, User.nickname == nickname))
    )
    if existing is not None:
        if existing.student_number == student_number:
            raise RegistrationError("이미 가입된 학번입니다.")
        raise RegistrationError("이미 사용 중인 닉네임입니다.")

    user = User(
        student_number=student_number,
        real_name=real_name,
        nickname=nickname,
        avatar_id=avatar.id,
        password_hash=hash_password(payload.password),
        role=UserRole.STUDENT,
    )
    db.add(user)
    db.flush()
    roster.registered_user_id = user.id
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, login: str, password: str) -> User | None:
    user = db.scalar(
        select(User).where(or_(User.student_number == login.strip(), User.nickname == login.strip()))
    )
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user

