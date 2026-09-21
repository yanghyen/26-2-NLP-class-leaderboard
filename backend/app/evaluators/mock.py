from typing import Any

from app.evaluators.base import EvaluationContext, Evaluator


class MockEvaluator(Evaluator):
    key = "mock"

    def validate_submission(self, context: EvaluationContext) -> None:
        return None

    def load_model(self, context: EvaluationContext) -> dict[str, str]:
        return {"model": "mock"}

    def run_inference(self, context: EvaluationContext, model: Any) -> list[Any]:
        return []

    def compute_metrics(self, context: EvaluationContext, predictions: list[Any]) -> dict[str, Any]:
        return {"primary_metric": "mock_score", "primary_score": 0.0, "metrics": {}}

