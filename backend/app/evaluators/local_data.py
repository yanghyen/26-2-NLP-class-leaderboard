"""Strict local JSONL input; no network or sample/label output in evaluation results."""
import hashlib
import json
from pathlib import Path

from app.evaluators.errors import EvaluatorError
from app.evaluators.lab02_policy import IMDB_REVISION, validate_dataset_config


def read_json_object(path: Path, max_bytes: int = 100000) -> dict:
    try:
        if path.stat().st_size > max_bytes:
            raise ValueError
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, ValueError, UnicodeError):
        raise EvaluatorError("EVALUATION_DATA_INVALID") from None


def valid_record(value: object) -> bool:
    return (isinstance(value, dict) and set(value) == {"text", "label"}
            and isinstance(value["text"], str) and bool(value["text"].strip())
            and type(value["label"]) is int and value["label"] in (0, 1))


def read_records(path: Path) -> tuple[list[str], list[int], str]:
    texts, labels = [], []
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for line in source:
                if len(line) > 2_000_000:
                    raise ValueError
                digest.update(line)
                value = json.loads(line.decode("utf-8"))
                if not valid_record(value):
                    raise ValueError
                texts.append(value["text"])
                labels.append(value["label"])
        if not labels:
            raise ValueError
    except (OSError, ValueError, UnicodeError):
        raise EvaluatorError("EVALUATION_DATA_INVALID") from None
    return texts, labels, digest.hexdigest()


def load_dataset(config: dict) -> tuple[list[str], list[int], dict]:
    validate_dataset_config(config)
    metadata = read_json_object(Path(config["metadata_path"]))
    texts, labels, digest = read_records(Path(config["path"]))
    if any(type(metadata.get(k)) is not type(config[k]) or metadata[k] != config[k]
           for k in ("version", "sha256", "sample_count")):
        raise EvaluatorError("EVALUATION_DATA_INVALID")
    if digest != config["sha256"] or len(labels) != config["sample_count"]:
        raise EvaluatorError("EVALUATION_DATA_INVALID")
    if metadata.get("source") not in {"stanfordnlp/imdb", "local"}:
        raise EvaluatorError("EVALUATION_DATA_INVALID")
    if metadata.get("source") == "stanfordnlp/imdb":
        if metadata.get("revision") != IMDB_REVISION or metadata.get("split") != "test":
            raise EvaluatorError("EVALUATION_DATA_INVALID")
        if metadata.get("scope") == "full" and len(labels) != 25000:
            raise EvaluatorError("EVALUATION_DATA_INVALID")
        if metadata.get("scope") not in {"full", "smoke"}:
            raise EvaluatorError("EVALUATION_DATA_INVALID")
    return texts, labels, metadata
