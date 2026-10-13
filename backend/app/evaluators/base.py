from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _noop() -> None:
    pass


@dataclass(frozen=True)
class EvaluationContext:
    task_slug: str
    split: str
    submission_dir: Path
    dataset_config: dict[str, Any]
    allowed_models: list[str]
    metric_config: dict[str, Any]
    artifact_digest: str
    trust_remote_code: bool = field(default=False, init=False)
    check_timeout: Callable[[], None] = field(default=_noop, repr=False, compare=False)
    on_scoring: Callable[[], None] = field(default=_noop, repr=False, compare=False)

    def begin_scoring(self) -> None:
        """Worker-owned timeout checkpoint and RUNNING -> SCORING transition."""
        self.check_timeout()
        self.on_scoring()


@dataclass(frozen=True)
class EvaluationRequest:
    """Internal request only; paths and callbacks never belong in public schemas."""
    submission_id: str
    task_id: str
    evaluator_key: str
    artifact_path: Path
    validated_manifest: dict[str, Any]
    validated_metadata: dict[str, Any]
    context: EvaluationContext


@dataclass(frozen=True)
class EvaluationResult:
    primary_metric: str
    primary_score: float
    secondary_metrics: dict[str, Any]
    evaluator_version: str
    dataset_version: str


class Evaluator(ABC):
    key: str
    version = "unversioned"

    @abstractmethod
    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        raise NotImplementedError

    def cleanup(self, request: EvaluationRequest) -> None:
        return None
