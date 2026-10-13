"""Offline, server-owned BERT architecture. Never load classes/config from a student path."""
import gc
import hashlib
import importlib.metadata
import time
from pathlib import Path

from app.evaluators.errors import EvaluatorError
from app.evaluators.lab02_contract import LAB02_CONTRACT, validate_lab02_contract
from app.evaluators.lab02_policy import LIBRARY_VERSIONS, MODEL_REVISION, TOKENIZER_REVISION
from app.evaluators.local_data import read_json_object

RESOURCE_FILES = ("config.json", "vocab.txt", "tokenizer.json", "tokenizer_config.json")
STRUCTURE_FIELDS = ("vocab_size", "hidden_size", "num_hidden_layers", "num_attention_heads",
                    "intermediate_size", "max_position_embeddings", "type_vocab_size")
BASE_STRUCTURE = dict(zip(STRUCTURE_FIELDS, (30522, 768, 12, 12, 3072, 512, 2)))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def server_resources(root: Path) -> dict:
    try:
        metadata = read_json_object(root / "resources.json")
        if (metadata.get("model_id") != LAB02_CONTRACT.base_model
                or metadata.get("model_revision") != MODEL_REVISION
                or metadata.get("tokenizer_revision") != TOKENIZER_REVISION
                or set(metadata.get("files", {})) != set(RESOURCE_FILES)):
            raise ValueError
        for name in RESOURCE_FILES:
            if sha256_file(root / name) != metadata["files"][name]:
                raise ValueError
        config = read_json_object(root / "config.json")
        if config.get("model_type") != "bert" or any(config.get(k) != v for k, v in BASE_STRUCTURE.items()):
            raise ValueError
        return config
    except (OSError, ValueError, EvaluatorError):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID") from None


def library_versions() -> dict:
    try:
        versions = {name: importlib.metadata.version(name) for name in LIBRARY_VERSIONS}
        if any(versions[name].split("+")[0] != expected for name, expected in LIBRARY_VERSIONS.items()):
            raise ValueError
        return versions
    except (importlib.metadata.PackageNotFoundError, ValueError):
        raise EvaluatorError("EVALUATOR_CONFIG_INVALID") from None


def classification_metrics(labels: list[int], predictions: list[int]) -> dict:
    from sklearn.metrics import accuracy_score, f1_score
    if not labels or len(labels) != len(predictions) or any(type(x) is not int or x not in (0, 1) for x in labels + predictions):
        raise EvaluatorError("EVALUATION_DATA_INVALID")
    return {"macro_f1": float(f1_score(labels, predictions, labels=[0, 1], average="macro", zero_division=0)),
            "accuracy": float(accuracy_score(labels, predictions))}


def load_weights(model, path: Path) -> None:
    import torch
    from safetensors.torch import load_file
    from safetensors import SafetensorError
    try:
        state = load_file(str(path), device="cpu")
        expected = model.state_dict()
        if set(state) != set(expected):
            raise ValueError
        for name, tensor in state.items():
            if (tensor.shape != expected[name].shape
                    or tensor.dtype not in {torch.float32, torch.float16, torch.bfloat16}
                    or not torch.isfinite(tensor).all().item()):
                raise ValueError
        model.load_state_dict(state, strict=True)
    except torch.cuda.OutOfMemoryError:
        raise
    except (ValueError, RuntimeError, OSError, SafetensorError) as exc:
        raise EvaluatorError("MODEL_WEIGHTS_INVALID") from exc


def infer_and_score(artifact_dir: Path, texts: list[str], labels: list[int], *,
                    server_config: dict, tokenizer_dir: Path, device: str, batch_size: int, seed: int) -> dict:
    """Shared real loading/inference path; tests supply a trusted tiny server config.

    Production supplies server_resources(), never a student's config. Tiny test
    fixtures use the same BertForSequenceClassification, safetensors and tokenizer.
    """
    import torch
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast
    started = time.monotonic()
    model = tokenizer = inputs = logits = None
    try:
        if device not in {"cpu", "cuda"} or (device == "cuda" and not torch.cuda.is_available()):
            raise EvaluatorError("EVALUATOR_CONFIG_INVALID")
        torch.set_num_threads(1)
        torch.manual_seed(seed)
        if device == "cuda":
            torch.cuda.manual_seed_all(seed)
        try:
            manifest = read_json_object(artifact_dir / "manifest.json")
        except EvaluatorError:
            raise EvaluatorError("LAB02_MANIFEST_INVALID") from None
        try:
            config = read_json_object(artifact_dir / "config.json")
        except EvaluatorError:
            raise EvaluatorError("LAB02_CONFIG_INVALID") from None
        # Parent upload validation already checked ZIP trust boundaries; recheck weight parsing below.
        validate_lab02_contract(manifest, config, [p.name for p in artifact_dir.iterdir()], safetensors_validated=True)
        if any(k in config and config[k] != server_config[k] for k in STRUCTURE_FIELDS):
            raise EvaluatorError("LAB02_CONFIG_INVALID")
        fixed = BertConfig.from_dict(server_config)
        fixed.num_labels = 2
        fixed.id2label = {0: "negative", 1: "positive"}
        fixed.label2id = {"negative": 0, "positive": 1}
        fixed._attn_implementation = "eager"
        model = BertForSequenceClassification(fixed)
        load_weights(model, artifact_dir / "model.safetensors")
        model.to(torch.device(device))
        model.eval()
        tokenizer = BertTokenizerFast.from_pretrained(
            str(tokenizer_dir), local_files_only=True, trust_remote_code=False,
            do_lower_case=True, truncation_side="right", padding_side="right",
        )
        predictions = []
        with torch.inference_mode():
            for offset in range(0, len(texts), batch_size):
                # Raw review text is passed unchanged; no HTML cleaning or student preprocessing.
                batch = texts[offset:offset + batch_size]
                inputs = tokenizer(batch, add_special_tokens=True, padding=True,
                                   truncation=True, max_length=128, return_tensors="pt")
                inputs = {name: tensor.to(device) for name, tensor in inputs.items()}
                logits = model(**inputs).logits
                if logits.shape != (len(batch), 2) or not torch.isfinite(logits).all().item():
                    raise EvaluatorError("MODEL_WEIGHTS_INVALID")
                predictions.extend(logits.argmax(dim=-1).cpu().tolist())
        if len(predictions) != len(labels) or len(texts) != len(labels):
            raise EvaluatorError("EVALUATION_DATA_INVALID")
        return dict(metrics=classification_metrics(labels, predictions), sample_count=len(labels),
                    inference_seconds=time.monotonic() - started)
    except (torch.cuda.OutOfMemoryError, MemoryError):
        raise EvaluatorError("EVALUATION_RESOURCE_LIMIT") from None
    finally:
        model = tokenizer = inputs = logits = None
        gc.collect()
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
