"""Actual supplied ZIP JSON metadata; tiny synthetic weights for shared security tests."""
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.evaluators.errors import EvaluatorError
from app.evaluators.lab02_contract import LAB02_CONTRACT, validate_lab02_contract
from app.security.validation import ArtifactValidationError, validate_and_extract_model_zip
from tests.conftest import safetensors_bytes

FIXTURES = Path(__file__).parent / "fixtures" / "lab02"


@pytest.fixture()
def metadata():
    return tuple(json.loads((FIXTURES / name).read_text()) for name in ["manifest.json", "config.json"])


def validate(manifest, config, **kwargs):
    return validate_lab02_contract(manifest, config, list(LAB02_CONTRACT.allowed_files),
                                   safetensors_validated=True, **kwargs)


def test_supplied_notebook_zip_metadata_passes_without_loading_a_model(metadata):
    manifest, config = metadata
    assert "num_labels" not in config  # The actual notebook config derives it from id2label.
    assert validate(manifest, config) == manifest
    assert LAB02_CONTRACT.tokenizer_source == "server_fixed"
    assert LAB02_CONTRACT.max_length == 128
    assert (LAB02_CONTRACT.primary_metric, LAB02_CONTRACT.secondary_metric) == ("macro_f1", "accuracy")
    reversed_members = deepcopy(manifest)
    reversed_members["label_mapping"] = {"1": "positive", "0": "negative"}
    assert validate(reversed_members, config) == manifest


@pytest.mark.parametrize("field,value", [
    ("format_version", 1.0), ("task", "translation"),
    ("base_model", "course/bert-base"), ("architecture", "CustomPythonModel"),
    ("artifact_type", "adapter"), ("num_labels", 3), ("num_labels", True), ("num_labels", 2.0),
    ("label_mapping", {"0": "positive", "1": "negative"}),
    ("label_mapping", ["negative", "positive"]), ("label_mapping", {0: "negative", 1: "positive"}),
    ("max_length", 512), ("tokenizer_source", "student"),
])
def test_manifest_mismatch_has_safe_contract_code(metadata, field, value):
    manifest, config = metadata
    manifest[field] = value
    with pytest.raises(EvaluatorError) as caught:
        validate(manifest, config)
    assert caught.value.code == "LAB02_MANIFEST_INVALID"
    assert "CustomPythonModel" not in str(caught.value)


@pytest.mark.parametrize("field", [
    "format_version", "task", "base_model", "architecture", "artifact_type", "num_labels", "label_mapping",
])
def test_required_manifest_fields(metadata, field):
    manifest, config = metadata
    del manifest[field]
    with pytest.raises(EvaluatorError, match="Lab02 manifest"):
        validate(manifest, config)


@pytest.mark.parametrize("field,value", [
    ("model_type", "gpt2"), ("architectures", ["CustomModel"]),
    ("num_labels", 3), ("num_labels", True),
    ("id2label", {"0": "positive", "1": "negative"}),
    ("label2id", {"negative": False, "positive": 1}),
    ("auto_map", {"AutoModel": "student.Code"}), ("trust_remote_code", True),
    ("_name_or_path", "/private/secret/model"),
])
def test_config_conflicts_and_remote_code_are_rejected(metadata, field, value):
    manifest, config = metadata
    config[field] = value
    with pytest.raises(EvaluatorError) as caught:
        validate(manifest, config)
    assert caught.value.code == "LAB02_CONFIG_INVALID"
    assert "/private" not in str(caught.value) and "student.Code" not in str(caught.value)


@pytest.mark.parametrize("files", [
    ["manifest.json", "config.json", "model.safetensors", "tokenizer.json"],
    ["manifest.json", "config.json", "model.safetensors", "run.py"],
    ["manifest.json", "config.json"], ["manifest.json", "config.json", "config.json"], None,
])
def test_exact_file_set_required(metadata, files):
    with pytest.raises(EvaluatorError) as caught:
        validate_lab02_contract(*metadata, files, safetensors_validated=True)
    assert caught.value.code == "LAB02_MANIFEST_INVALID"


def test_safetensors_security_result_is_required(metadata):
    with pytest.raises(EvaluatorError):
        validate_lab02_contract(*metadata, LAB02_CONTRACT.allowed_files, safetensors_validated=False)


def zip_bytes(manifest, config, extras=None, weights=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("config.json", json.dumps(config))
        archive.writestr("model.safetensors", safetensors_bytes() if weights is None else weights)
        for name, data in (extras or {}).items():
            archive.writestr(name, data)
    return output.getvalue()


def secure_validate(tmp_path, payload):
    archive = tmp_path / "synthetic.zip"
    archive.write_bytes(payload)
    try:
        return validate_and_extract_model_zip(
            archive, tmp_path / "extracted", settings=get_settings(), max_uncompressed_bytes=100000,
            allowed_models=[LAB02_CONTRACT.base_model],
            artifact_policy={"allowed_architectures": [LAB02_CONTRACT.architecture]},
            contract_key=LAB02_CONTRACT.key,
        )
    finally:
        # Metadata/weights are temporary; the fixtures contain only the two small JSON files.
        archive.unlink(missing_ok=True)
        import shutil
        shutil.rmtree(tmp_path / "extracted", ignore_errors=True)


def test_lab02_zip_uses_existing_safetensors_checks(metadata, tmp_path):
    archive, model = secure_validate(tmp_path, zip_bytes(*metadata))
    assert archive["files"] == 3
    assert model["manifest"] == metadata[0]
    assert model["safetensors_validated"] is True and model["tensor_count"] == 1
    with pytest.raises(ArtifactValidationError):
        secure_validate(tmp_path, zip_bytes(*metadata, weights=b"not a safetensors file"))


@pytest.mark.parametrize("name", ["tokenizer.json", "run.py", "model/config.json"])
def test_lab02_zip_rejects_additional_files(metadata, tmp_path, name):
    with pytest.raises(ArtifactValidationError) as caught:
        secure_validate(tmp_path, zip_bytes(*metadata, extras={name: b"{}"}))
    assert caught.value.code == "LAB02_MANIFEST_INVALID"
    assert str(tmp_path) not in str(caught.value)


def test_lab02_zip_json_errors_remain_safe(metadata, tmp_path):
    manifest, config = metadata
    config["auto_map"] = {"AutoModel": "/private/server/evil.py"}
    with pytest.raises(ArtifactValidationError) as caught:
        secure_validate(tmp_path, zip_bytes(manifest, config))
    assert caught.value.code == "LAB02_CONFIG_INVALID"
    assert "/private" not in str(caught.value) and "Traceback" not in str(caught.value)
