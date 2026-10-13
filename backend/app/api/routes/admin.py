from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.dependencies import require_admin
from app.core.enums import SubmissionKind, SubmissionStatus
from app.models import CourseRoster, EvaluationJob, Participant, Submission, SubmissionFile, Task, User
from app.queue import JobQueue, QueueUnavailableError, get_job_queue
from app.schemas import (
    EvaluationJobAdminOut,
    RosterRowOut,
    SubmissionAdminOut,
)
from app.services.audit import write_audit
from app.services.artifact_cleanup import cleanup_successful_submission
from app.services.roster import parse_roster_csv, upsert_roster_rows
from app.services.state import InvalidStateTransition, transition_job, transition_submission
from app.storage import get_artifact_storage
from app.storage.base import ArtifactStorage

router = APIRouter(prefix="/admin", tags=["admin"])


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
) -> list[RosterRowOut]:
    rows = db.execute(
        select(CourseRoster, Participant.nickname, Participant.id)
        .outerjoin(Participant, Participant.roster_entry_id == CourseRoster.id)
        .order_by(CourseRoster.student_number)
    ).all()
    return [
        RosterRowOut(
            student_number=roster.student_number,
            real_name=roster.real_name,
            section=roster.section,
            participant_id=participant_id,
            nickname=nickname,
        )
        for roster, nickname, participant_id in rows
    ]


@router.get("/submissions", response_model=list[SubmissionAdminOut])
def list_submissions(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[SubmissionAdminOut]:
    rows = db.execute(
        select(Submission, func.coalesce(Participant.nickname, User.nickname), Task.slug, Task.title, func.coalesce(CourseRoster.student_number, User.student_number))
        .outerjoin(Participant, Participant.id == Submission.participant_id)
        .outerjoin(User, User.id == Submission.user_id)
        .outerjoin(CourseRoster, CourseRoster.id == Participant.roster_entry_id)
        .join(Task, Task.id == Submission.task_id)
        .order_by(Submission.created_at.desc())
    ).all()
    return [
        SubmissionAdminOut.model_validate(submission).model_copy(
            update={"nickname": nickname or "", "task_slug": task_slug, "task_title": task_title, "student_number": student_number}
        )
        for submission, nickname, task_slug, task_title, student_number in rows
    ]


@router.get("/jobs", response_model=list[EvaluationJobAdminOut])
def list_jobs(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[EvaluationJob]:
    return list(db.scalars(select(EvaluationJob).order_by(EvaluationJob.created_at.desc())).all())


@router.get("/quarantine", response_model=list[SubmissionAdminOut])
def list_quarantine(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Submission]:
    return [row for row in list_submissions(db, _) if row.status == SubmissionStatus.QUARANTINED]



@router.get("/submissions/{submission_id}/download/{file_type}")
def download_submission_file(
    submission_id: str,
    file_type: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> FileResponse:
    if file_type not in {"notebook", "model_zip"}:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    submission = db.get(Submission, submission_id)
    if submission is None or submission.status == SubmissionStatus.QUARANTINED:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    if submission.artifact_cleanup_status in {"pending", "deleted"} or (
        submission.status == SubmissionStatus.COMPLETED and submission.kind != SubmissionKind.DRAFT
    ):
        raise HTTPException(status_code=409, detail="평가 완료 후 자동 삭제되는 제출 파일은 다운로드할 수 없습니다.")
    row = db.scalar(
        select(SubmissionFile).where(
            SubmissionFile.submission_id == submission_id,
            SubmissionFile.file_type == file_type,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    filename = "notebook.ipynb" if file_type == "notebook" else "model.zip"
    path = storage.artifact_path(submission_id) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path, filename=filename, media_type=row.mime_type)


@router.post("/jobs/{job_id}/retry", response_model=EvaluationJobAdminOut)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    queue: JobQueue = Depends(get_job_queue),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> EvaluationJob:
    job = db.get(EvaluationJob, job_id)
    if job is not None and job.submission.artifact_cleanup_status in {"pending", "deleted"}:
        raise HTTPException(status_code=409, detail="평가 완료 후 자동 삭제되는 제출은 재평가할 수 없습니다.")
    if job is None or job.status != SubmissionStatus.FAILED or not job.error_kind:
        raise HTTPException(status_code=400, detail="재시도할 수 없는 Job입니다.")
    if job.error_kind not in {"EVALUATION_FAILED", "QUEUE_UNAVAILABLE", "SERVER_ERROR_RETRY"}:
        raise HTTPException(status_code=400, detail="학생 제출 오류는 자동 재시도하지 않습니다.")
    if not storage.artifact_path(job.submission_id).is_dir():
        raise HTTPException(status_code=409, detail="제출 파일이 없어 재평가할 수 없습니다.")
    try:
        transition_job(job, SubmissionStatus.QUEUED)
        transition_submission(job.submission, SubmissionStatus.QUEUED)
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=400, detail="재시도할 수 없는 상태입니다.") from exc
    job.error_kind = None
    job.safe_error_message = None
    job.submission.safe_error_message = None
    db.commit()
    try:
        queue.enqueue(job.id)
    except QueueUnavailableError as exc:
        transition_job(job, SubmissionStatus.FAILED)
        transition_submission(job.submission, SubmissionStatus.FAILED)
        job.error_kind = "QUEUE_UNAVAILABLE"
        db.commit()
        raise HTTPException(status_code=503, detail="평가 대기열을 사용할 수 없습니다.") from exc
    write_audit(
        db,
        actor=actor,
        action="evaluation_job.retried",
        target_type="evaluation_job",
        target_id=job.id,
    )
    db.commit()
    db.refresh(job)
    return job


@router.post("/submissions/{submission_id}/invalidate", response_model=SubmissionAdminOut)
def invalidate_submission(
    submission_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> Submission:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="제출을 찾을 수 없습니다.")
    try:
        transition_submission(submission, SubmissionStatus.INVALIDATED)
    except InvalidStateTransition as exc:
        raise HTTPException(status_code=400, detail="현재 상태에서는 무효화할 수 없습니다.") from exc
    write_audit(
        db,
        actor=actor,
        action="submission.invalidated",
        target_type="submission",
        target_id=submission.id,
    )
    db.commit()
    db.refresh(submission)
    return submission


@router.delete("/submissions/{submission_id}/artifact", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission_artifact(
    submission_id: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    storage: ArtifactStorage = Depends(get_artifact_storage),
) -> None:
    submission = db.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="제출을 찾을 수 없습니다.")
    if submission.status in PENDING_ADMIN_DELETE_STATUSES:
        raise HTTPException(status_code=400, detail="진행 중인 제출 artifact는 삭제할 수 없습니다.")
    if submission.artifact_cleanup_status == "deleted":
        return
    if submission.status == SubmissionStatus.COMPLETED and submission.kind != SubmissionKind.DRAFT:
        # Finish the read transaction before the cleanup service takes its own row lock.
        # Historical successes may still be retained before the first recovery sweep.
        factory = sessionmaker(bind=db.get_bind(), expire_on_commit=False)
        db.rollback()
        if not cleanup_successful_submission(submission_id, storage=storage, db_factory=factory):
            raise HTTPException(status_code=409, detail="파일 정리가 대기 중입니다. 나중에 다시 시도하세요.")
        db.refresh(submission)
        return
    storage.delete_artifact(submission.id)
    submission.artifact_cleanup_status = "deleted"
    submission.artifact_deleted_at = datetime.now(UTC)
    if submission.status != SubmissionStatus.INVALIDATED:
        transition_submission(submission, SubmissionStatus.INVALIDATED)
    write_audit(
        db,
        actor=actor,
        action="submission.artifact_deleted",
        target_type="submission",
        target_id=submission.id,
    )
    db.commit()


PENDING_ADMIN_DELETE_STATUSES = {
    SubmissionStatus.UPLOADING,
    SubmissionStatus.VALIDATING,
    SubmissionStatus.QUEUED,
    SubmissionStatus.RUNNING,
    SubmissionStatus.SCORING,
}


@router.get("/tasks/{task_slug}/participants")
def participant_results(task_slug: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    from app.services.results import task_results
    task = db.scalar(select(Task).where(Task.slug == task_slug))
    if task is None:
        raise HTTPException(404, "태스크를 찾을 수 없습니다.")
    return [dict({k: v for k, v in row.items() if k not in {"participant", "representative"}},
                 participant_id=row["participant"].id, roster_entry_id=row["participant"].roster_entry_id)
            for row in task_results(db, task.id)]


@router.get("/tasks/{task_slug}/results.csv")
def export_results(task_slug: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    import csv
    from io import StringIO
    from fastapi.responses import Response
    rows = participant_results(task_slug, db, _)
    fields = ["student_number", "nickname", "emoji", "baseline_score", "best_development_score", "improvement",
              "total_submission_count", "successful_submission_count", "failed_submission_count",
              "quarantined_submission_count", "last_submitted_at"]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        # Prevent spreadsheet formula injection without changing student number identifiers.
        writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v) for k, v in row.items()})
    return Response(output.getvalue().encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="practice-results.csv"'})


from pydantic import BaseModel, Field


class ParticipantUpdate(BaseModel):
    nickname: str = Field(min_length=2, max_length=16)
    emoji: str = Field(min_length=1, max_length=16)


@router.patch("/participants/{participant_id}")
def update_participant(participant_id: str, payload: ParticipantUpdate, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    from app.models import Avatar
    from app.services.registration import validate_nickname
    participant = db.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(404, "참가자를 찾을 수 없습니다.")
    try:
        nickname = validate_nickname(payload.nickname)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not db.scalar(select(Avatar).where(Avatar.emoji == payload.emoji, Avatar.is_active.is_(True))):
        raise HTTPException(400, "선택할 수 없는 이모지입니다.")
    before = {"nickname": participant.nickname, "emoji": participant.emoji}
    participant.nickname, participant.emoji = nickname, payload.emoji
    write_audit(db, actor=actor, action="participant.updated", target_type="participant", target_id=participant.id,
                before=before, after=payload.model_dump())
    db.commit()
    return {"id": participant.id, "nickname": participant.nickname, "emoji": participant.emoji}


class BaselineUpdate(BaseModel):
    submission_id: str


@router.put("/participants/{participant_id}/tasks/{task_slug}/baseline")
def reset_baseline(participant_id: str, task_slug: str, payload: BaselineUpdate, db: Session = Depends(get_db), actor: User = Depends(require_admin)):
    from app.models import BaselineReference, Score
    from app.core.enums import SubmissionKind, EvaluationSplit
    task = db.scalar(select(Task).where(Task.slug == task_slug))
    submission = db.get(Submission, payload.submission_id)
    if not task or not submission or submission.participant_id != participant_id or submission.task_id != task.id or submission.kind != SubmissionKind.BASELINE_PRACTICE or submission.status != SubmissionStatus.COMPLETED:
        raise HTTPException(400, "성공한 동일 참가자·태스크의 Baseline만 지정할 수 있습니다.")
    if not db.scalar(select(Score).where(Score.submission_id == submission.id, Score.visible_to_student.is_(True), Score.split == EvaluationSplit.SMOKE)):
        raise HTTPException(400, "Baseline 평가 결과가 없습니다.")
    reference = db.scalar(select(BaselineReference).where(BaselineReference.participant_id == participant_id, BaselineReference.task_id == task.id))
    before = {"submission_id": reference.submission_id if reference else None}
    if reference:
        reference.submission_id = submission.id
    else:
        db.add(BaselineReference(participant_id=participant_id, task_id=task.id, submission_id=submission.id))
    write_audit(db, actor=actor, action="baseline.reset", target_type="participant", target_id=participant_id,
                before=before, after={"submission_id": submission.id, "task_id": task.id})
    db.commit()
    return {"submission_id": submission.id}
