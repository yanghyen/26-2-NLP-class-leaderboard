from app.evaluators.base import Evaluator
from app.evaluators.mock import MockEvaluator


EVALUATORS: dict[str, Evaluator] = {"mock": MockEvaluator()}


def get_evaluator(key: str) -> Evaluator:
    try:
        return EVALUATORS[key]
    except KeyError as exc:
        raise LookupError(f"Unknown evaluator key: {key}") from exc
