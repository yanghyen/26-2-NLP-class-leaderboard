import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EvaluationSplit, SubmissionKind, SubmissionStatus
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models import FinalSelection, Score, Submission, SubmissionFile, Task, User
from app.queue import JobQueue, get_job_queue
from app.schemas import (
    EvaluationJobOut,
    FinalSelectionOut,
    ScoreOut,
    SubmissionCreateIn,
    SubmissionCreateOut,
    SubmissionDetailOut,
    SubmissionFileOut,
    SubmissionOut,
)
from app.security.malware import MalwareScanner, get_malware_scanner
from app.services.submissions import (
    SubmissionError,
    SubmissionUploadError,
    create_submission_from_upload,
)
from app.storage import get_artifact_storage
from app.storage.base import ArtifactStorage

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("/{task_slug}", response_model=SubmissionCreateOut, status_code=status.HTTP_201_CREATED)
async def create_submission(
    task_slug: str,
    notebook: Annotated[UploadFile, File(...)],
    archive_upload: Annotated[UploadFile, File(alias="model_zip")],
    kind: Annotated[SubmissionKind, Form()] = SubmissionKind.EVALUATION,
    submitted_model_name: Annotated[str | None, Form(alias="model_name", max_length=160)] = None,
    base_model: Annotated[str | None, Form(max_length=160)] = None,
    seed: Annotated[int | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    scanner: MalwareScanner = Depends(get_malware_scanner),
    queue: JobQueue = Depends(get_job_queue),
) -> SubmissionCreateOut:
    task = db.scalar(select(Task).where(Task.slug == task_slug, Task.is_public.is_(True)))
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    try:
        metadata = json.loads(metadata_json)
        if not isinstance(metadata, dict):
            raise ValueError
        payload = SubmissionCreateIn(
            kind=kind,
            model_name=submitted_model_name,
            base_model=base_model,
            seed=seed,
            metadata_json=metadata,
        )
        submission, job = await create_submission_from_upload(
            db,
            user=current_user,
            task=task,
            payload=payload,
            notebook=notebook,
            model_zip=archive_upload,
            storage=storage,
            scanner=scanner,
            queue=queue,
        )
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        if isinstance(exc, SubmissionUploadError):
            raise HTTPException(
                status_code=400,
                detail={"code": exc.code, "message": str(exc), "submission_id": exc.submission_id},
            ) from exc
        if isinstance(exc, SubmissionError):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail="metadata_json은 JSON object여야 합니다.") from exc
    return SubmissionCreateOut(
        submission=SubmissionOut.model_validate(submission),
        evaluation_job=EvaluationJobOut.model_validate(job) if job else None,
    )


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


@router.get("/final-selections", response_model=list[FinalSelectionOut])
def final_selections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FinalSelection]:
    return list(
        db.scalars(
            select(FinalSelection)
            .where(FinalSelection.user_id == current_user.id)
            .order_by(FinalSelection.created_at.desc())
        ).all()
    )


@router.get("/{submission_id}", response_model=SubmissionDetailOut)
def submission_detail(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SubmissionDetailOut:
    submission = db.get(Submission, submission_id)
    if submission is None or submission.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="제출을 찾을 수 없습니다.")
    scores = db.scalars(
        select(Score).where(
            Score.submission_id == submission.id,
            Score.visible_to_student.is_(True),
            Score.split.in_([EvaluationSplit.SMOKE, EvaluationSplit.PUBLIC]),
        )
    ).all()
    result = SubmissionDetailOut.model_validate(submission)
    result.scores = [ScoreOut.model_validate(score) for score in scores]
    files = db.scalars(
        select(SubmissionFile).where(SubmissionFile.submission_id == submission.id)
    ).all()
    result.files = [SubmissionFileOut.model_validate(file) for file in files]
    result.is_final_selection = db.scalar(
        select(FinalSelection).where(
            FinalSelection.user_id == current_user.id,
            FinalSelection.task_id == submission.task_id,
            FinalSelection.submission_id == submission.id,
        )
    ) is not None
    return result


@router.post("/{submission_id}/final-selection", response_model=FinalSelectionOut)
def select_final_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FinalSelection:
    submission = db.get(Submission, submission_id)
    if (
        submission is None
        or submission.user_id != current_user.id
        or submission.kind != SubmissionKind.EVALUATION
        or submission.status != SubmissionStatus.COMPLETED
    ):
        raise HTTPException(status_code=400, detail="완료된 개발 제출만 최종 제출로 선택할 수 있습니다.")
    selection = db.scalar(
        select(FinalSelection).where(
            FinalSelection.user_id == current_user.id,
            FinalSelection.task_id == submission.task_id,
        )
    )
    if selection is None:
        selection = FinalSelection(
            user_id=current_user.id,
            task_id=submission.task_id,
            submission_id=submission.id,
        )
        db.add(selection)
    else:
        selection.submission_id = submission.id
    db.commit()
    db.refresh(selection)
    return selection
