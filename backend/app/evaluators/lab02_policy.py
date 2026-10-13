"""Server-owned revisions and evaluation identity. No model/data imports at API startup."""
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.evaluators.errors import EvaluatorError
from app.evaluators.lab02_contract import LAB02_CONTRACT

MODEL_REVISION = "86b5e0934494bd15c9632b12f734a8a67f723594"
TOKENIZER_REVISION = MODEL_REVISION
IMDB_REVISION = "e6281661ce1c48d982bc483cf8a173c1bbeb5d31"
LIBRARY_VERSIONS = {"torch": "2.6.0", "transformers": "4.57.1", "safetensors": "0.4.5", "scikit-learn": "1.6.1"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def evaluation_identity(dataset_config: dict[str, Any], settings: Settings | None = None) -> tuple[str, str]:
    settings = settings or get_settings()
    policy = dict(model_revision=MODEL_REVISION, tokenizer_revision=TOKENIZER_REVISION,
                  max_length=128, truncation="right", cleaning="none", labels=[0, 1],
                  metric="macro_f1", libraries=LIBRARY_VERSIONS, device=settings.lab02_device,
                  batch_size=settings.lab02_batch_size, seed=settings.lab02_seed)
    digest = hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]
    return f"lab02-sentiment-v1-{digest}", f"{dataset_config['version']}:{dataset_config['sha256']}"


def validate_dataset_config(config: dict[str, Any]) -> None:
    if not isinstance(config, dict):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    if not isinstance(config.get("version"), str) or not config["version"].strip() or len(config["version"]) > 160:
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    if not isinstance(config.get("sha256"), str) or not SHA256_RE.fullmatch(config["sha256"]):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    if type(config.get("sample_count")) is not int or config["sample_count"] < 1:
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    for field in ("path", "metadata_path"):
        if not isinstance(config.get(field), str) or not Path(config[field]).is_absolute():
            raise EvaluatorError("EVALUATOR_CONFIG_INVALID")


def validate_task_config(dataset_config, metric_config, allowed_models, artifact_policy) -> None:
    validate_dataset_config(dataset_config)
    if not isinstance(metric_config, dict) or not isinstance(artifact_policy, dict):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    paths = artifact_policy.get("allowed_paths")
    if paths is not None and (not isinstance(paths, list)
            or not all(type(path) is str for path in paths)
            or len(paths) != len(LAB02_CONTRACT.allowed_files)
            or set(paths) != set(LAB02_CONTRACT.allowed_files)):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
    if (
        allowed_models != [LAB02_CONTRACT.base_model]
        or artifact_policy.get("allowed_architectures") != [LAB02_CONTRACT.architecture]
        or metric_config.get("primary") != "macro_f1"
        or metric_config.get("scale", "0_1") != "0_1"
        or ("score_range" in metric_config and metric_config["score_range"] != [0, 1])
    ):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
