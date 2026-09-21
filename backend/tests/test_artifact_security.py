import io
import json
import stat
import zipfile
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.security.validation import (
    ArtifactValidationError,
    _validate_zip_entry,
    validate_and_extract_model_zip,
    validate_notebook,
)
from tests.conftest import model_zip_bytes, notebook_bytes


ALLOWED_MODELS = ["course/bert-base"]
POLICY = {"allowed_architectures": ["BertForSequenceClassification"]}


def validate_archive(tmp_path: Path, content: bytes, **setting_updates):
    tmp_path.mkdir(parents=True, exist_ok=True)
    archive_path = tmp_path / "model.zip"
    archive_path.write_bytes(content)
    settings = get_settings().model_copy(update=setting_updates)
    return validate_and_extract_model_zip(
        archive_path,
        tmp_path / "extracted",
        settings=settings,
        max_uncompressed_bytes=5_000_000,
        allowed_models=ALLOWED_MODELS,
        artifact_policy=POLICY,
    )


@pytest.mark.parametrize("unsafe_path", ["../escape.py", "/absolute.py", "C:/drive.py", "server\\share.py"])
def test_archive_rejects_unsafe_paths(tmp_path, unsafe_path):
    content = model_zip_bytes(extras={unsafe_path: b"pass"})
    with pytest.raises(ArtifactValidationError) as error:
        validate_archive(tmp_path, content)
    assert error.value.code == "INVALID_ARCHIVE"


@pytest.mark.parametrize(
    "name",
    [
        "model/evil.py",
        "model/run.sh",
        "model/program.exe",
        "model/native.so",
        "model/weights.pt",
        "model/weights.pth",
        "model/data.pkl",
        "model/data.pickle",
        "model/pytorch_model.bin",
        "model/unknown.xyz",
        "model/nested.zip",
    ],
)
def test_archive_rejects_code_pickle_native_unknown_and_nested_files(tmp_path, name):
    with pytest.raises(ArtifactValidationError) as error:
        validate_archive(tmp_path, model_zip_bytes(extras={name: b"synthetic"}))
    assert error.value.code == "UNSUPPORTED_FILE"


def test_archive_rejects_symlink_and_special_file_entries():
    settings = get_settings()
    for file_type in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR, stat.S_IFSOCK):
        info = zipfile.ZipInfo("model/tokenizer.json")
        info.create_system = 3
        info.external_attr = (file_type | 0o600) << 16
        with pytest.raises(ArtifactValidationError):
            _validate_zip_entry(info, settings)


def test_archive_rejects_encrypted_and_executable_entries():
    settings = get_settings()
    encrypted = zipfile.ZipInfo("model/tokenizer.json")
    encrypted.flag_bits = 0x1
    with pytest.raises(ArtifactValidationError):
        _validate_zip_entry(encrypted, settings)
    executable = zipfile.ZipInfo("model/tokenizer.json")
    executable.create_system = 3
    executable.external_attr = (stat.S_IFREG | 0o700) << 16
    with pytest.raises(ArtifactValidationError):
        _validate_zip_entry(executable, settings)


def test_archive_rejects_duplicate_case_collisions(tmp_path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("submission.json", "{}")
        archive.writestr("SUBMISSION.JSON", "{}")
    with pytest.raises(ArtifactValidationError) as error:
        validate_archive(tmp_path, output.getvalue())
    assert error.value.code == "INVALID_ARCHIVE"


def test_archive_rejects_excessive_depth_count_and_compression_ratio(tmp_path):
    deep = model_zip_bytes(extras={"a/b/c/d/e/f/g/h/i.json": b"{}"})
    with pytest.raises(ArtifactValidationError):
        validate_archive(tmp_path, deep, max_archive_depth=4)

    many_policy = {
        **POLICY,
        "allowed_paths": [
            "submission.json",
            "model/config.json",
            "model/model.safetensors",
            "model/a.json",
            "model/b.json",
        ],
    }
    archive_path = tmp_path / "many.zip"
    archive_path.write_bytes(
        model_zip_bytes(extras={"model/a.json": b"{}", "model/b.json": b"{}"})
    )
    with pytest.raises(ArtifactValidationError):
        validate_and_extract_model_zip(
            archive_path,
            tmp_path / "many",
            settings=get_settings().model_copy(update={"max_archive_files": 3}),
            max_uncompressed_bytes=5_000_000,
            allowed_models=ALLOWED_MODELS,
            artifact_policy=many_policy,
        )

    bomb_policy = {
        **POLICY,
        "allowed_paths": [
            "submission.json",
            "model/config.json",
            "model/model.safetensors",
            "model/tokenizer.json",
        ],
    }
    with pytest.raises(ArtifactValidationError) as error:
        validate_and_extract_model_zip(
            _write(tmp_path / "bomb.zip", model_zip_bytes(extras={"model/tokenizer.json": b"0" * 100_000})),
            tmp_path / "bomb",
            settings=get_settings().model_copy(update={"max_archive_ratio": 2.0}),
            max_uncompressed_bytes=5_000_000,
            allowed_models=ALLOWED_MODELS,
            artifact_policy=bomb_policy,
        )
    assert error.value.code == "MODEL_TOO_LARGE"


def test_archive_rejects_disguised_executable(tmp_path):
    with pytest.raises(ArtifactValidationError) as error:
        validate_archive(
            tmp_path,
            model_zip_bytes(extras={"model/tokenizer.json": b"MZ synthetic executable"}),
        )
    assert error.value.code == "UNSUPPORTED_FILE"


@pytest.mark.parametrize(
    "dangerous_config",
    [
        {"auto_map": {"AutoModel": "custom.Model"}},
        {"trust_remote_code": True},
    ],
)
def test_model_policy_rejects_remote_code_and_custom_architecture(
    tmp_path, dangerous_config
):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("submission.json", json.dumps({"base_model": "course/bert-base"}))
        archive.writestr(
            "model/config.json",
            json.dumps({
                "_name_or_path": "course/bert-base",
                "architectures": ["BertForSequenceClassification"],
                **dangerous_config,
            }),
        )
        from tests.conftest import safetensors_bytes

        archive.writestr("model/model.safetensors", safetensors_bytes())
    with pytest.raises(ArtifactValidationError) as error:
        validate_archive(tmp_path, output.getvalue())
    assert error.value.code == "INVALID_MODEL_FORMAT"

    with pytest.raises(ArtifactValidationError) as error:
        validate_archive(tmp_path / "custom", model_zip_bytes(architecture="CustomPythonModel"))
    assert error.value.code == "INVALID_MODEL_FORMAT"


def test_notebook_validation_never_executes_or_renders_outputs(tmp_path):
    marker = tmp_path / "should-not-exist"
    notebook = tmp_path / "submission.ipynb"
    notebook.write_bytes(
        notebook_bytes(
            outputs=[
                {
                    "output_type": "display_data",
                    "data": {"text/html": f"<script>fetch('file://{marker}')</script>"},
                    "metadata": {},
                }
            ]
        )
    )
    report = validate_notebook(notebook, get_settings())
    assert report["code_cells"] == 1
    assert not marker.exists()


def test_notebook_rejects_invalid_json_and_limits(tmp_path):
    invalid = _write(tmp_path / "invalid.ipynb", b"not-json")
    with pytest.raises(ArtifactValidationError):
        validate_notebook(invalid, get_settings())
    large = _write(tmp_path / "large.ipynb", notebook_bytes())
    with pytest.raises(ArtifactValidationError):
        validate_notebook(large, get_settings().model_copy(update={"max_notebook_bytes": 10}))
    with pytest.raises(ArtifactValidationError):
        validate_notebook(large, get_settings().model_copy(update={"max_notebook_cells": 0}))
    with pytest.raises(ArtifactValidationError):
        validate_notebook(large, get_settings().model_copy(update={"max_notebook_output_bytes": -1}))


def _write(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path
