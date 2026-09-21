from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.core.enums import EvaluationSplit, SubmissionStatus
from app.models import Avatar, Score, Submission, Task, TaskConfig, User
from app.schemas import LeaderboardRowOut, TaskCreateIn, TaskOut
from app.services.audit import write_audit

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.is_public.is_(True)).order_by(Task.created_at)).all())


@router.get("/admin", response_model=list[TaskOut])
def list_admin_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Task]:
    return list(db.scalars(select(Task).order_by(Task.created_at)).all())


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> Task:
    if db.scalar(select(Task).where(Task.slug == payload.slug)):
        raise HTTPException(status_code=400, detail="이미 존재하는 태스크 slug입니다.")
    task = Task(
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        stage=payload.stage,
        is_public=payload.is_public,
        max_official_submissions=payload.max_official_submissions,
        max_zip_bytes=payload.max_zip_bytes,
        timeout_seconds=payload.timeout_seconds,
        evaluator_key=payload.evaluator_key,
    )
    task.config = TaskConfig(
        dataset_config=payload.config.dataset_config,
        allowed_models=payload.config.allowed_models,
        artifact_policy=payload.config.artifact_policy,
        metric_config=payload.config.metric_config,
        split_config=payload.config.split_config,
        scoring_strategy=payload.config.scoring_strategy,
    )
    db.add(task)
    db.flush()
    write_audit(
        db,
        actor=actor,
        action="task.created",
        target_type="task",
        target_id=task.id,
        after={"slug": task.slug, "stage": task.stage},
    )
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_slug}/leaderboard", response_model=list[LeaderboardRowOut])
def task_leaderboard(task_slug: str, db: Session = Depends(get_db)) -> list[LeaderboardRowOut]:
    task = db.scalar(
        select(Task).where(
            Task.slug == task_slug,
            Task.is_public.is_(True),
            Task.public_leaderboard_visible.is_(True),
        )
    )
    if task is None:
        raise HTTPException(status_code=404, detail="리더보드를 찾을 수 없습니다.")
    rows = db.execute(
        select(Submission, Score, User, Avatar)
        .join(Score, Score.submission_id == Submission.id)
        .join(User, User.id == Submission.user_id)
        .join(Avatar, Avatar.id == User.avatar_id)
        .where(
            Submission.task_id == task.id,
            Submission.status == SubmissionStatus.COMPLETED,
            Score.split == EvaluationSplit.PUBLIC,
            Score.visible_to_student.is_(True),
        )
    ).all()
    best_by_user: dict[str, tuple[Submission, Score, User, Avatar]] = {}
    for submission, score, user, avatar in rows:
        current = best_by_user.get(user.id)
        if current is None or score.primary_score > current[1].primary_score:
            best_by_user[user.id] = (submission, score, user, avatar)
    ordered = sorted(best_by_user.values(), key=lambda row: (-row[1].primary_score, row[0].created_at))
    result: list[LeaderboardRowOut] = []
    previous_score: float | None = None
    previous_rank = 0
    for index, (submission, score, user, avatar) in enumerate(ordered, start=1):
        rank = previous_rank if previous_score == score.primary_score else index
        result.append(
            LeaderboardRowOut(
                rank=rank,
                nickname=user.nickname,
                avatar_id=user.avatar_id,
                avatar_emoji=avatar.emoji,
                submission_id=submission.id,
                primary_metric=score.primary_metric,
                primary_score=score.primary_score,
                metrics=score.metrics,
            )
        )
        previous_score = score.primary_score
        previous_rank = rank
    return result
