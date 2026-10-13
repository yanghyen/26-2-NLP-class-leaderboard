from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import User
from app.schemas import ErrorResponse, LoginIn, TokenOut, UserOut
from app.services.registration import authenticate_user

router = APIRouter(prefix="/auth", tags=["admin authentication"])


def to_user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        nickname=user.nickname,
        avatar_id=user.avatar_id,
        avatar_emoji=user.avatar.emoji,
        role=user.role,
        student_number=user.student_number,
        real_name=user.real_name,
        password_reset_required=user.password_reset_required,
    )


@router.post(
    "/login",
    response_model=TokenOut,
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "아이디 또는 비밀번호가 올바르지 않거나 계정이 비활성 상태입니다.",
        }
    },
)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = authenticate_user(db, payload.student_number_or_nickname, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인 정보가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    return to_user_out(current_user)
