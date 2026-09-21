from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


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


class Evaluator(ABC):
    key: str

    @abstractmethod
    def validate_submission(self, context: EvaluationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def prepare(self, context: EvaluationContext) -> Any:
        raise NotImplementedError

    @abstractmethod
    def run_inference(self, context: EvaluationContext, model: Any) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def compute_metrics(self, context: EvaluationContext, predictions: list[Any]) -> dict[str, Any]:
        raise NotImplementedError

    def format_result(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return metrics

    def cleanup(self, context: EvaluationContext) -> None:
        return None
