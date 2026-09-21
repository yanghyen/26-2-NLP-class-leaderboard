from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class Evaluator(ABC):
    key: str

    @abstractmethod
    def validate_submission(self, context: EvaluationContext) -> None:
        raise NotImplementedError

    @abstractmethod
    def load_model(self, context: EvaluationContext) -> Any:
        raise NotImplementedError

    @abstractmethod
    def run_inference(self, context: EvaluationContext, model: Any) -> list[Any]:
        raise NotImplementedError

    @abstractmethod
    def compute_metrics(self, context: EvaluationContext, predictions: list[Any]) -> dict[str, Any]:
        raise NotImplementedError

    def format_public_result(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return metrics

    def cleanup(self, context: EvaluationContext) -> None:
        return None

