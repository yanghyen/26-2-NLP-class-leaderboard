import argparse

from sqlalchemy import select

from app.core.enums import UserRole
from app.core.security import hash_password
from app.db.base import create_all
from app.db.session import SessionLocal
from app.models import User
from app.services.avatars import ensure_default_avatars


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nickname", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    create_all()
    db = SessionLocal()
    try:
        ensure_default_avatars(db)
        existing = db.scalar(select(User).where(User.nickname == args.nickname))
        if existing:
            raise SystemExit(f"User already exists: {args.nickname}")
        user = User(
            nickname=args.nickname,
            avatar_id="robot",
            password_hash=hash_password(args.password),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Created admin: {user.nickname}")
    finally:
        db.close()


if __name__ == "__main__":
    main()

