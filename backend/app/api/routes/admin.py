from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.models import CourseRoster, JoinCode, User
from app.schemas import JoinCodeIn, JoinCodeOut, RosterRowOut
from app.services.audit import write_audit
from app.services.registration import create_join_code
from app.services.roster import parse_roster_csv, upsert_roster_rows

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/join-code", response_model=JoinCodeOut, status_code=status.HTTP_201_CREATED)
def set_join_code(
    payload: JoinCodeIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> JoinCode:
    join_code = create_join_code(
        db,
        label=payload.label,
        code=payload.code,
        deactivate_existing=payload.deactivate_existing,
    )
    write_audit(
        db,
        actor=actor,
        action="join_code.created",
        target_type="join_code",
        target_id=join_code.id,
        after={"label": join_code.label, "is_active": join_code.is_active},
    )
    db.commit()
    return join_code


@router.post("/roster/upload")
async def upload_roster(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> dict[str, int]:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="CSV 파일만 업로드할 수 있습니다.")
    content = (await file.read()).decode("utf-8-sig")
    try:
        rows = parse_roster_csv(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    count = upsert_roster_rows(db, rows)
    write_audit(
        db,
        actor=actor,
        action="roster.uploaded",
        target_type="course_roster",
        target_id=None,
        after={"count": count},
    )
    db.commit()
    return {"imported": count}


@router.get("/roster", response_model=list[RosterRowOut])
def list_roster(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[CourseRoster]:
    return list(db.scalars(select(CourseRoster).order_by(CourseRoster.student_number)).all())

