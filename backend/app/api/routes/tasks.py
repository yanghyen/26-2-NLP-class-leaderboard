from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import require_admin
from app.models import Task, TaskConfig, User
from app.schemas import LeaderboardRowOut, TaskCreateIn, TaskDetailOut, TaskOut, TaskUpdateIn, PublicTaskDetailOut, PublicTaskOut
from app.services.audit import write_audit
from app.services.results import task_results
from app.evaluators.errors import EvaluatorError
from app.evaluators.registry import get_evaluator
from app.evaluators.lab02_policy import validate_task_config

router = APIRouter(prefix="/tasks", tags=["tasks"])


def validate_evaluator_selection(key: object) -> str:
    try:
        return get_evaluator(key).key
    except EvaluatorError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)}) from exc


def validate_lab02_selection(key: str, config: dict) -> None:
    if key == "lab02_sentiment_v1":
        try:
            validate_task_config(config["dataset_config"], config["metric_config"],
                                 config["allowed_models"], config["artifact_policy"])
        except EvaluatorError as exc:
            raise HTTPException(400, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("", response_model=list[PublicTaskOut])
def list_tasks(db: Session = Depends(get_db)) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.is_public.is_(True)).order_by(Task.created_at)).all())


@router.get("/admin", response_model=list[TaskDetailOut])
def list_admin_tasks(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[Task]:
    return list(db.scalars(select(Task).order_by(Task.created_at)).all())


@router.get("/admin/{task_slug}", response_model=TaskDetailOut)
def admin_task_detail(
    task_slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
) -> Task:
    task = db.scalar(select(Task).where(Task.slug == task_slug))
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
    return task


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> Task:
    evaluator_key = validate_evaluator_selection(payload.evaluator_key)
    validate_lab02_selection(evaluator_key, payload.config.model_dump())
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
        evaluator_key=evaluator_key,
        opens_at=payload.opens_at, dev_deadline=payload.dev_deadline, final_deadline=payload.final_deadline,
    )
    task.config = TaskConfig(
        dataset_config=payload.config.dataset_config,
        allowed_models=payload.config.allowed_models,
        artifact_policy=payload.config.artifact_policy.model_dump(exclude_none=True),
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
        after={"slug": task.slug, "stage": task.stage, "evaluator_key": task.evaluator_key},
    )
    db.commit()
    db.refresh(task)
    return task


@router.patch("/{task_slug}", response_model=TaskDetailOut)
def update_task(
    task_slug: str,
    payload: TaskUpdateIn,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
) -> Task:
    task = db.scalar(select(Task).where(Task.slug == task_slug))
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")

    evaluator_key = validate_evaluator_selection(
        payload.evaluator_key if "evaluator_key" in payload.model_fields_set else task.evaluator_key
    )
    prospective = {k: getattr(task.config, k) for k in
                   ("dataset_config", "metric_config", "allowed_models", "artifact_policy")}
    if payload.config is not None:
        prospective.update(payload.config.model_dump(exclude_unset=True))
    validate_lab02_selection(evaluator_key, prospective)
    before = {
        "evaluator_key": task.evaluator_key,
        "title": task.title,
        "stage": task.stage.value,
        "is_public": task.is_public,
        "allowed_models": task.config.allowed_models,
        "artifact_policy": task.config.artifact_policy,
    }
    for field, value in payload.model_dump(exclude_unset=True, exclude={"config"}).items():
        setattr(task, field, value)
    task.evaluator_key = evaluator_key
    if payload.config is not None:
        config_values = payload.config.model_dump(exclude_unset=True)
        if payload.config.artifact_policy is not None:
            config_values["artifact_policy"] = payload.config.artifact_policy.model_dump(
                exclude_none=True
            )
        for field, value in config_values.items():
            setattr(task.config, field, value)

    write_audit(
        db,
        actor=actor,
        action="task.updated",
        target_type="task",
        target_id=task.id,
        before=before,
        after={
            "evaluator_key": task.evaluator_key,
            "title": task.title,
            "stage": task.stage.value,
            "is_public": task.is_public,
            "allowed_models": task.config.allowed_models,
            "artifact_policy": task.config.artifact_policy,
        },
    )
    db.commit()
    db.refresh(task)
    return task


@router.get("/{task_slug}", response_model=PublicTaskDetailOut)
def task_detail(task_slug: str, db: Session = Depends(get_db)) -> Task:
    task = db.scalar(select(Task).where(Task.slug == task_slug, Task.is_public.is_(True)))
    if task is None:
        raise HTTPException(status_code=404, detail="태스크를 찾을 수 없습니다.")
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
    rows = [row for row in task_results(db, task.id) if row["representative"]]
    rows.sort(key=lambda row: (-row["representative"][1].primary_score, row["representative"][0].created_at))
    ranks = []
    for index, row in enumerate(rows, 1):
        same_score = index > 1 and row["representative"][1].primary_score == rows[index-2]["representative"][1].primary_score
        ranks.append(ranks[-1] if same_score else index)
    return [LeaderboardRowOut(rank=ranks[index-1], nickname=row["nickname"], avatar_id="",
        avatar_emoji=row["emoji"], primary_metric=row["representative"][1].primary_metric,
        primary_score=row["representative"][1].primary_score, metrics={},
        model_name=row["representative"][0].model_name, submitted_at=row["representative"][0].created_at,
        baseline_score=row["baseline_score"], best_development_score=row["best_development_score"],
        improvement=row["improvement"]) for index, row in enumerate(rows, 1)]
