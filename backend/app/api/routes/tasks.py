from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.models import Task, TaskConfig, User
from app.schemas import TaskCreateIn, TaskOut
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

