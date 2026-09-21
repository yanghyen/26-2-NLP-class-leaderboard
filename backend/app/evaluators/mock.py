import hashlib
from typing import Any

from app.evaluators.base import EvaluationContext, Evaluator


class MockEvaluator(Evaluator):
    key = "mock"

    def validate_submission(self, context: EvaluationContext) -> None:
        return None

    def prepare(self, context: EvaluationContext) -> dict[str, str]:
        return {"model": "mock"}

    def run_inference(self, context: EvaluationContext, model: Any) -> list[Any]:
        return []

    def compute_metrics(self, context: EvaluationContext, predictions: list[Any]) -> dict[str, Any]:
        digest = hashlib.sha256(context.artifact_digest.encode("ascii")).digest()
        score = round(int.from_bytes(digest[:8], "big") / ((1 << 64) - 1), 6)
        return {
            "primary_metric": "mock_score",
            "primary_score": score,
            "metrics": {"mock_score": score, "deterministic": True},
        }
