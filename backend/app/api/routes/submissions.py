import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EvaluationSplit, SubmissionKind, SubmissionStatus
from app.db.session import get_db
from app.models import Score, Submission, Task
from app.queue import JobQueue, get_job_queue
from app.schemas import (
    EvaluationJobOut,
    ScoreOut,
    SubmissionCreateIn,
    SubmissionCreateOut,
    SubmissionDetailOut,
    SubmissionOut,
)
from app.security.malware import MalwareScanner, get_malware_scanner
from app.services.participants import get_participant
from app.services.submissions import (
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
    archive_upload: Annotated[UploadFile, File(alias="artifact")],
    student_number: Annotated[str, Form()],
    nickname: Annotated[str, Form()],
    emoji: Annotated[str, Form()],
    submitted_model_name: Annotated[str, Form(alias="model_name", min_length=1, max_length=160)],
    kind: Annotated[SubmissionKind, Form(alias="submission_type")] = SubmissionKind.EVALUATION,
    base_model: Annotated[str | None, Form(max_length=160)] = None,
    seed: Annotated[int | None, Form()] = None,
    metadata_json: Annotated[str, Form()] = "{}",
    db: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_artifact_storage),
    scanner: MalwareScanner = Depends(get_malware_scanner),
    queue: JobQueue = Depends(get_job_queue),
) -> SubmissionCreateOut:
    task = db.scalar(select(Task).where(Task.slug == task_slug, Task.is_public.is_(True)))
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    try:
        participant = get_participant(db, student_number, nickname, emoji)
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
            participant=participant,
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
        if not isinstance(exc, (json.JSONDecodeError, ValidationError)):
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        raise HTTPException(status_code=400, detail="입력 정보를 확인하세요.") from exc
    return SubmissionCreateOut(
        submission=SubmissionOut.model_validate(submission),
        evaluation_job=EvaluationJobOut.model_validate(job) if job else None,
    )


@router.get("/{submission_id}", response_model=SubmissionDetailOut)
def submission_detail(submission_id: str, db: Session = Depends(get_db)) -> SubmissionDetailOut:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="제출을 찾을 수 없습니다.")
    result = SubmissionDetailOut.model_validate(submission)
    if submission.status == SubmissionStatus.COMPLETED:
        scores = db.scalars(select(Score).where(
            Score.submission_id == submission.id,
            Score.visible_to_student.is_(True),
            Score.split.in_([EvaluationSplit.SMOKE, EvaluationSplit.PUBLIC]),
        )).all()
        result.scores = [ScoreOut(split=x.split, primary_metric=x.primary_metric,
                                 primary_score=x.primary_score, metrics={}) for x in scores]
    return result
