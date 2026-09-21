import argparse
import os

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.base import create_all
from app.db.session import SessionLocal
from app.models import Avatar, User
from app.services.avatars import ensure_default_avatars


class AdminBootstrapError(ValueError):
    pass


def create_or_get_admin(
    db: Session,
    *,
    nickname: str,
    password: str,
    avatar_id: str = "robot",
) -> tuple[User, bool]:
    nickname = " ".join(nickname.strip().split())
    if not 2 <= len(nickname) <= 16 or any(not character.isprintable() for character in nickname):
        raise AdminBootstrapError("관리자 닉네임은 2~16자의 유효한 문자열이어야 합니다.")
    if not 8 <= len(password) <= 128:
        raise AdminBootstrapError("관리자 비밀번호는 8~128자여야 합니다.")

    existing = db.scalar(
        select(User).where(func.lower(User.nickname) == nickname.casefold())
    )
    if existing is not None:
        if existing.role != UserRole.ADMIN:
            raise AdminBootstrapError(
                f"같은 닉네임을 사용하는 일반 계정이 이미 있습니다: {existing.nickname}"
            )
        if not existing.is_active:
            raise AdminBootstrapError(
                f"기존 관리자 계정이 비활성 상태입니다: {existing.nickname}"
            )
        return existing, False

    avatar = db.get(Avatar, avatar_id)
    if avatar is None or not avatar.is_active:
        raise AdminBootstrapError(f"사용할 수 없는 avatar ID입니다: {avatar_id}")
    admin = User(
        nickname=nickname,
        avatar_id=avatar.id,
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        is_active=True,
        password_reset_required=False,
    )
    db.add(admin)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = db.scalar(
            select(User).where(func.lower(User.nickname) == nickname.casefold())
        )
        if concurrent is not None and concurrent.role == UserRole.ADMIN and concurrent.is_active:
            return concurrent, False
        raise
    db.refresh(admin)
    return admin, True


def reset_admin_password(db: Session, *, admin: User, password: str) -> None:
    if admin.role != UserRole.ADMIN or not admin.is_active:
        raise AdminBootstrapError("활성 관리자 계정만 비밀번호를 재설정할 수 있습니다.")
    if not 8 <= len(password) <= 128:
        raise AdminBootstrapError("관리자 비밀번호는 8~128자여야 합니다.")
    admin.password_hash = hash_password(password)
    db.commit()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="development 로컬 DB에 최초 관리자 계정을 idempotent하게 생성합니다."
    )
    parser.add_argument(
        "--nickname",
        default=os.environ.get("DEV_ADMIN_NICKNAME"),
        help="관리자 로그인 닉네임 (또는 DEV_ADMIN_NICKNAME)",
    )
    parser.add_argument(
        "--password",
        default=os.environ.get("DEV_ADMIN_PASSWORD"),
        help="관리자 비밀번호 (또는 DEV_ADMIN_PASSWORD; 환경변수 사용 권장)",
    )
    parser.add_argument("--avatar-id", default="robot")
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="기존 활성 관리자의 비밀번호를 명시적으로 재설정합니다.",
    )
    args = parser.parse_args()
    if not args.nickname:
        parser.error("--nickname 또는 DEV_ADMIN_NICKNAME이 필요합니다.")
    if not args.password:
        parser.error("--password 또는 DEV_ADMIN_PASSWORD가 필요합니다.")
    return args


def require_development(app_env: str) -> None:
    if app_env != "development":
        raise AdminBootstrapError(
            "관리자 bootstrap CLI는 APP_ENV=development에서만 실행할 수 있습니다."
        )


def main() -> None:
    settings = get_settings()
    try:
        require_development(settings.app_env)
    except AdminBootstrapError as exc:
        raise SystemExit(str(exc)) from exc
    args = parse_args()
    create_all()
    db = SessionLocal()
    try:
        ensure_default_avatars(db)
        admin, created = create_or_get_admin(
            db,
            nickname=args.nickname,
            password=args.password,
            avatar_id=args.avatar_id,
        )
        if not created and args.reset_password:
            reset_admin_password(db, admin=admin, password=args.password)
            action = "Reset password for"
        else:
            action = "Created" if created else "Already exists"
        print(f"{action} active admin. Login ID (nickname): {admin.nickname}")
    except AdminBootstrapError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        db.close()


if __name__ == "__main__":
    main()
