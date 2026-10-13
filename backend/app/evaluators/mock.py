import hashlib
from typing import Any

from app.evaluators.base import EvaluationContext, EvaluationRequest, EvaluationResult, Evaluator


class MockEvaluator(Evaluator):
    key = "mock_v1"
    version = "mock-v1"
    dataset_version = "mock-dataset-v1"

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        context = request.context
        self.validate_submission(context)
        prepared = self.prepare(context)
        predictions = self.run_inference(context, prepared)
        context.begin_scoring()
        metrics = self.format_result(self.compute_metrics(context, predictions))
        # Preserve explicitly configured historical version values without connecting a dataset.
        version = context.dataset_config.get("dataset_version", context.dataset_config.get("version"))
        return EvaluationResult(
            primary_metric=str(metrics["primary_metric"]),
            primary_score=float(metrics["primary_score"]),
            secondary_metrics=dict(metrics.get("metrics", {})),
            evaluator_version=self.version,
            dataset_version=str(version) if version is not None else self.dataset_version,
        )

    def format_result(self, metrics: dict[str, Any]) -> dict[str, Any]:
        return metrics

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
