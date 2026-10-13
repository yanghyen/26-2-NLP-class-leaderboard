"""Data-only Lab02 contract. This module is not an executable evaluator."""
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.core.config import Settings, get_settings
from app.evaluators.errors import EvaluatorError


@dataclass(frozen=True)
class Lab02Contract:
    key: str = "lab02_sentiment_v1"
    format_version: str = "1.0"
    task: str = "sentiment"
    base_model: str = "google-bert/bert-base-uncased"
    architecture: str = "BertForSequenceClassification"
    artifact_type: str = "full_model"
    num_labels: int = 2
    labels: tuple[str, str] = ("negative", "positive")
    tokenizer_source: str = "server_fixed"
    max_length: int = 128
    primary_metric: str = "macro_f1"
    secondary_metric: str = "accuracy"
    allowed_files: tuple[str, ...] = ("manifest.json", "config.json", "model.safetensors")


LAB02_CONTRACT = Lab02Contract()


def validate_lab02_contract(
    manifest: dict[str, Any],
    config: dict[str, Any],
    artifact_files: Sequence[str],
    *,
    safetensors_validated: bool,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Validate metadata after the shared ZIP/JSON/safetensors security boundary.

    safetensors_validated is a trusted server result, never a manifest field.
    No tensor reads, model imports, tokenizer loads, or inference occur here.
    Server tokenizer/length/metrics are evaluator policy, not required notebook fields.
    """
    from app.security.validation import ArtifactValidationError, validate_json_metadata

    contract = LAB02_CONTRACT
    settings = settings or get_settings()
    for value, code in ((manifest, "LAB02_MANIFEST_INVALID"), (config, "LAB02_CONFIG_INVALID")):
        try:
            validate_json_metadata(value, settings)
        except ArtifactValidationError:
            raise EvaluatorError(code) from None
    if (
        not isinstance(artifact_files, Sequence)
        or isinstance(artifact_files, (str, bytes))
        or len(artifact_files) != len(contract.allowed_files)
        or not all(type(name) is str for name in artifact_files)
        or set(artifact_files) != set(contract.allowed_files)
        or safetensors_validated is not True
    ):
        raise EvaluatorError("LAB02_MANIFEST_INVALID")

    expected = {
        "format_version": contract.format_version,
        "task": contract.task,
        "base_model": contract.base_model,
        "architecture": contract.architecture,
        "artifact_type": contract.artifact_type,
        "num_labels": contract.num_labels,
    }
    for key, value in expected.items():
        if type(manifest.get(key)) is not type(value) or manifest[key] != value:
            raise EvaluatorError("LAB02_MANIFEST_INVALID")
    labels = {str(index): label for index, label in enumerate(contract.labels)}
    # Index-to-label mapping defines the order; JSON member insertion order is irrelevant.
    if type(manifest.get("label_mapping")) is not dict or manifest["label_mapping"] != labels:
        raise EvaluatorError("LAB02_MANIFEST_INVALID")
    for key, value in {
        "max_length": contract.max_length,
        "tokenizer_source": contract.tokenizer_source,
    }.items():
        if key in manifest and (type(manifest[key]) is not type(value) or manifest[key] != value):
            raise EvaluatorError("LAB02_MANIFEST_INVALID")

    if config.get("model_type") != "bert" or config.get("architectures") != [contract.architecture]:
        raise EvaluatorError("LAB02_CONFIG_INVALID")
    if "num_labels" in config and (type(config["num_labels"]) is not int or config["num_labels"] != 2):
        raise EvaluatorError("LAB02_CONFIG_INVALID")
    if "id2label" in config and config["id2label"] != labels:
        raise EvaluatorError("LAB02_CONFIG_INVALID")
    if "label2id" in config:
        mapping = config["label2id"]
        if (
            type(mapping) is not dict
            or mapping != {label: index for index, label in enumerate(contract.labels)}
            or any(type(value) is not int for value in mapping.values())
        ):
            raise EvaluatorError("LAB02_CONFIG_INVALID")
    # Hugging Face configs may omit num_labels when it is derived from id2label.
    if "num_labels" not in config and "id2label" not in config:
        raise EvaluatorError("LAB02_CONFIG_INVALID")
    if "_name_or_path" in config and config["_name_or_path"] != contract.base_model:
        raise EvaluatorError("LAB02_CONFIG_INVALID")
    return {**expected, "label_mapping": labels}
