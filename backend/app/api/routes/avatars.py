from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Avatar
from app.schemas import AvatarOut

router = APIRouter(prefix="/avatars", tags=["avatars"])


@router.get("", response_model=list[AvatarOut])
def list_avatars(db: Session = Depends(get_db)) -> list[Avatar]:
    return list(db.scalars(select(Avatar).where(Avatar.is_active.is_(True)).order_by(Avatar.id)).all())

