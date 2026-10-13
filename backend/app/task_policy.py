from typing import Any

CANONICAL_TEST_ALLOWED_MODELS = ["course/bert-base"]
CANONICAL_TEST_ARTIFACT_POLICY = {
    "allowed_architectures": ["BertForSequenceClassification"]
}


def is_submission_policy_configured(
    allowed_models: list[str] | None, artifact_policy: dict[str, Any] | None
) -> bool:
    return bool(
        allowed_models
        and artifact_policy
        and artifact_policy.get("allowed_architectures")
    )
