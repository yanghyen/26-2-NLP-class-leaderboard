from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import Submission, Task, User
from app.schemas import EvaluationJobOut, SubmissionCreateIn, SubmissionOut
from app.services.submissions import SubmissionError, create_submission_record

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("/{task_slug}", status_code=status.HTTP_201_CREATED)
def create_submission(
    task_slug: str,
    payload: SubmissionCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, SubmissionOut | EvaluationJobOut | None]:
    task = db.scalar(select(Task).where(Task.slug == task_slug, Task.is_public.is_(True)))
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    try:
        submission, job = create_submission_record(db, user=current_user, task=task, payload=payload)
    except SubmissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "submission": SubmissionOut.model_validate(submission),
        "evaluation_job": EvaluationJobOut.model_validate(job) if job else None,
    }


@router.get("/me", response_model=list[SubmissionOut])
def my_submissions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Submission]:
    return list(
        db.scalars(
            select(Submission)
            .where(Submission.user_id == current_user.id)
            .order_by(Submission.created_at.desc())
        ).all()
    )

