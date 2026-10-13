from app.evaluators.base import Evaluator
from app.evaluators.mock import MockEvaluator
from app.evaluators.errors import EvaluatorError


EVALUATORS: dict[str, Evaluator] = {"mock_v1": MockEvaluator()}
LEGACY_ALIASES = {"mock": "mock_v1"}


def get_evaluator(key: object) -> Evaluator:
    if not isinstance(key, str) or not key or len(key) > 80:
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    if key == "lab02_sentiment_v1":
        raise EvaluatorError("EVALUATOR_NOT_AVAILABLE")
    canonical = LEGACY_ALIASES.get(key, key)
    if canonical not in EVALUATORS:
        raise EvaluatorError("UNKNOWN_EVALUATOR")
    return EVALUATORS[canonical]
