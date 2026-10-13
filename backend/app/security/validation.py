import json
import math
import os
import re
import stat
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from safetensors import safe_open

from app.core.config import Settings
from app.evaluators.errors import SAFE_EVALUATOR_MESSAGES, EvaluatorError
from app.evaluators.lab02_contract import LAB02_CONTRACT, validate_lab02_contract


DEFAULT_ALLOWED_PATHS = {
    "submission.json",
    "model/config.json",
    "model/model.safetensors",
    "model/model.safetensors.index.json",
    "model/tokenizer.json",
    "model/tokenizer_config.json",
    "model/special_tokens_map.json",
    "model/generation_config.json",
    "model/vocab.txt",
    "model/vocab.json",
    "model/merges.txt",
    "model/tokenizer.model",
}
MODEL_SHARD_RE = re.compile(r"^model/model-[A-Za-z0-9._-]+\.safetensors$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
URL_RE = re.compile(r"(?:https?|file|javascript)://", re.IGNORECASE)
FORBIDDEN_SUFFIXES = {
    ".py", ".pyc", ".pyo", ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts",
    ".exe", ".dll", ".so", ".dylib", ".bat", ".cmd", ".ps1", ".jar", ".class",
    ".app", ".com", ".scr", ".msi", ".pt", ".pth", ".pkl", ".pickle", ".bin",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
}
EXECUTABLE_SIGNATURES = (
    b"MZ",
    b"\x7fELF",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"#!",
)
ALLOWED_DTYPES = {
    "BOOL", "U8", "I8", "I16", "I32", "I64", "F16", "BF16", "F32", "F64",
}
DTYPE_BYTES = {
    "BOOL": 1, "U8": 1, "I8": 1, "I16": 2, "I32": 4, "I64": 8,
    "F16": 2, "BF16": 2, "F32": 4, "F64": 8,
}
SAFE_ERROR_MESSAGES = {
    **SAFE_EVALUATOR_MESSAGES,
    "INVALID_ARCHIVE": "모델 ZIP 형식이 올바르지 않습니다.",
    "UNSUPPORTED_FILE": "허용되지 않은 파일이 포함되어 있습니다.",
    "INVALID_MODEL_FORMAT": "모델 artifact 형식이 올바르지 않습니다.",
    "MODEL_TOO_LARGE": "모델 artifact가 허용 제한을 초과했습니다.",
    "MALWARE_DETECTED": "안전 검사에서 제출물을 처리할 수 없습니다.",
    "VALIDATION_FAILED": "제출 파일 검증에 실패했습니다.",
}


class ArtifactValidationError(ValueError):
    def __init__(self, code: str, internal_detail: str) -> None:
        self.code = code
        self.internal_detail = internal_detail
        super().__init__(SAFE_ERROR_MESSAGES.get(code, SAFE_ERROR_MESSAGES["VALIDATION_FAILED"]))


@dataclass(frozen=True)
class ValidationResult:
    notebook: dict[str, int]
    archive: dict[str, int]
    model: dict[str, Any]

    def public_report(self) -> dict[str, Any]:
        return {
            "notebook": self.notebook,
            "archive": self.archive,
            "model": self.model,
            "policy": {"notebook_executed": False, "trust_remote_code": False},
        }


def validate_notebook(path: Path, settings: Settings) -> dict[str, int]:
    if path.suffix.lower() != ".ipynb":
        raise ArtifactValidationError("UNSUPPORTED_FILE", "Notebook extension is not .ipynb")
    size = path.stat().st_size
    if size > settings.max_notebook_bytes:
        raise ArtifactValidationError("MODEL_TOO_LARGE", "Notebook exceeds byte limit")
    try:
        raw = path.read_text(encoding="utf-8")
        notebook = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError("VALIDATION_FAILED", "Notebook is not valid UTF-8 JSON") from exc
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        raise ArtifactValidationError("VALIDATION_FAILED", "Notebook has no cells array")
    if notebook.get("nbformat") not in {4}:
        raise ArtifactValidationError("VALIDATION_FAILED", "Only notebook format 4 is accepted")
    cells = notebook["cells"]
    if len(cells) > settings.max_notebook_cells:
        raise ArtifactValidationError("VALIDATION_FAILED", "Notebook cell count exceeds limit")
    source_chars = 0
    output_bytes = 0
    code_cells = 0
    for cell in cells:
        if not isinstance(cell, dict) or cell.get("cell_type") not in {"code", "markdown", "raw"}:
            raise ArtifactValidationError("VALIDATION_FAILED", "Notebook contains an invalid cell")
        source = cell.get("source", [])
        if isinstance(source, str):
            source_chars += len(source)
        elif isinstance(source, list) and all(isinstance(item, str) for item in source):
            source_chars += sum(len(item) for item in source)
        else:
            raise ArtifactValidationError("VALIDATION_FAILED", "Notebook cell source is invalid")
        if cell.get("cell_type") == "code":
            code_cells += 1
            outputs = cell.get("outputs", [])
            if not isinstance(outputs, list):
                raise ArtifactValidationError("VALIDATION_FAILED", "Notebook outputs are invalid")
            output_bytes += len(json.dumps(outputs, ensure_ascii=False).encode("utf-8"))
    if code_cells == 0:
        raise ArtifactValidationError("VALIDATION_FAILED", "Notebook contains no code cell")
    if source_chars > settings.max_notebook_source_chars:
        raise ArtifactValidationError("VALIDATION_FAILED", "Notebook source exceeds limit")
    if output_bytes > settings.max_notebook_output_bytes:
        raise ArtifactValidationError("VALIDATION_FAILED", "Notebook outputs exceed limit")
    return {"bytes": size, "cells": len(cells), "code_cells": code_cells, "output_bytes": output_bytes}


def validate_and_extract_model_zip(
    archive_path: Path,
    extract_root: Path,
    *,
    settings: Settings,
    max_uncompressed_bytes: int,
    allowed_models: list[str],
    artifact_policy: dict[str, Any],
    contract_key: str | None = None,
) -> tuple[dict[str, int], dict[str, Any]]:
    if contract_key not in {None, LAB02_CONTRACT.key}:
        raise ArtifactValidationError("EVALUATOR_CONFIG_INVALID", "Unknown artifact contract")
    is_lab02 = contract_key == LAB02_CONTRACT.key
    _validate_zip_envelope(archive_path)
    allowed_paths = set(LAB02_CONTRACT.allowed_files) if is_lab02 else set(
        artifact_policy.get("allowed_paths") or DEFAULT_ALLOWED_PATHS
    )
    allowed_architectures = set(artifact_policy.get("allowed_architectures") or [])
    allowed_dtypes = set(artifact_policy.get("allowed_dtypes") or ALLOWED_DTYPES)
    seen: set[str] = set()
    infos: list[zipfile.ZipInfo] = []
    total_expected = 0
    try:
        archive = zipfile.ZipFile(archive_path)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArtifactValidationError("INVALID_ARCHIVE", "ZIP central directory cannot be read") from exc
    with archive:
        for info in archive.infolist():
            normalized = _validate_zip_entry(info, settings)
            collision_key = normalized.casefold()
            if collision_key in seen:
                raise ArtifactValidationError("INVALID_ARCHIVE", "Duplicate or case-colliding path")
            seen.add(collision_key)
            if info.is_dir():
                if is_lab02:
                    raise ArtifactValidationError("LAB02_MANIFEST_INVALID", "Lab02 requires top-level files only")
                continue
            if is_lab02 and normalized not in allowed_paths:
                raise ArtifactValidationError("LAB02_MANIFEST_INVALID", "Unexpected Lab02 artifact file")
            _validate_allowed_path(normalized, allowed_paths)
            total_expected += info.file_size
            if total_expected > max_uncompressed_bytes:
                raise ArtifactValidationError("MODEL_TOO_LARGE", "Archive uncompressed bytes exceed limit")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > settings.max_archive_ratio:
                raise ArtifactValidationError("MODEL_TOO_LARGE", "Archive compression ratio exceeds limit")
            infos.append(info)
        if len(infos) > settings.max_archive_files:
            raise ArtifactValidationError("MODEL_TOO_LARGE", "Archive file count exceeds limit")
        names = {info.filename for info in infos}
        if is_lab02 and names != allowed_paths:
            raise ArtifactValidationError("LAB02_MANIFEST_INVALID", "Required Lab02 files are missing")
        if not is_lab02 and "submission.json" not in names:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "submission.json is required")
        if not is_lab02 and "model/config.json" not in names:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "model/config.json is required")
        if not any(info.filename.endswith(".safetensors") for info in infos):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "At least one safetensors file is required")
        try:
            extracted = _extract_checked(archive, infos, extract_root, max_uncompressed_bytes)
        except zipfile.BadZipFile as exc:
            raise ArtifactValidationError("INVALID_ARCHIVE", "ZIP CRC validation failed") from exc

    for path in extracted:
        _reject_disguised_executable(path)
    submission_name = "manifest.json" if is_lab02 else "submission.json"
    config_name = "config.json" if is_lab02 else "model/config.json"

    def load_metadata(name: str, code: str) -> dict[str, Any]:
        try:
            return _load_safe_json(extract_root / name, settings)
        except ArtifactValidationError as exc:
            if is_lab02:
                raise ArtifactValidationError(code, exc.internal_detail) from exc
            raise

    submission = load_metadata(submission_name, "LAB02_MANIFEST_INVALID")
    config = load_metadata(config_name, "LAB02_CONFIG_INVALID")
    parsed_json: dict[str, dict[str, Any]] = {}
    for json_path in extract_root.rglob("*.json"):
        parsed_json[json_path.relative_to(extract_root).as_posix()] = _load_safe_json(
            json_path, settings
        )
    if not is_lab02:
        _validate_model_config(config, submission, allowed_models, allowed_architectures)
    tensor_count = 0
    tensor_bytes = 0
    tensor_names: set[str] = set()
    tensor_paths = list(extract_root.rglob("*.safetensors"))
    for tensor_path in tensor_paths:
        count, size, names = _validate_safetensors(
            tensor_path,
            settings=settings,
            allowed_dtypes=allowed_dtypes,
            max_tensor_bytes=max_uncompressed_bytes,
        )
        tensor_count += count
        tensor_bytes += size
        if tensor_names.intersection(names):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Duplicate tensor name across shards")
        tensor_names.update(names)
    _validate_safetensors_index(
        parsed_json.get("model/model.safetensors.index.json"),
        tensor_paths,
        tensor_names,
        extract_root,
    )
    if is_lab02:
        try:
            manifest = validate_lab02_contract(
                submission, config, [info.filename for info in infos],
                safetensors_validated=True, settings=settings,
            )
        except EvaluatorError as exc:
            raise ArtifactValidationError(exc.code, "Lab02 metadata conflicts with contract") from exc
    else:
        # Persist only bounded, allowlisted manifest fields rather than arbitrary student data.
        manifest = {"base_model": submission["base_model"]}
    return (
        {"files": len(infos), "uncompressed_bytes": total_expected},
        {
            "base_model": submission.get("base_model"),
            "architectures": config.get("architectures", []),
            "tensor_count": tensor_count,
            "tensor_bytes": tensor_bytes,
            "trust_remote_code": False,
            "manifest": manifest,
            "safetensors_validated": True,
        },
    )


def _validate_zip_envelope(path: Path) -> None:
    file_size = path.stat().st_size
    with path.open("rb") as file:
        if file.read(4) != b"PK\x03\x04":
            raise ArtifactValidationError(
                "INVALID_ARCHIVE", "ZIP has a prepended payload or invalid signature"
            )
        tail_size = min(file_size, 65_557)
        file.seek(file_size - tail_size)
        tail = file.read(tail_size)
    relative_offset = tail.rfind(b"PK\x05\x06")
    if relative_offset < 0 or relative_offset + 22 > len(tail):
        raise ArtifactValidationError("INVALID_ARCHIVE", "ZIP end record is missing")
    disk_number, central_disk, entries_disk, entries_total = struct.unpack_from(
        "<HHHH", tail, relative_offset + 4
    )
    comment_length = struct.unpack_from("<H", tail, relative_offset + 20)[0]
    if relative_offset + 22 + comment_length != len(tail):
        raise ArtifactValidationError("INVALID_ARCHIVE", "ZIP contains trailing or concatenated data")
    if disk_number != 0 or central_disk != 0 or entries_disk != entries_total:
        raise ArtifactValidationError("INVALID_ARCHIVE", "Multi-disk ZIP files are not accepted")


def _validate_zip_entry(info: zipfile.ZipInfo, settings: Settings) -> str:
    name = info.filename
    if "\x00" in name or "\\" in name or name.startswith(("/", "\\")) or WINDOWS_DRIVE_RE.match(name):
        raise ArtifactValidationError("INVALID_ARCHIVE", "Unsafe archive path")
    pure = PurePosixPath(name)
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ArtifactValidationError("INVALID_ARCHIVE", "Archive path contains unsafe segments")
    if len(name) > settings.max_archive_path_length or any(
        len(part) > settings.max_archive_filename_length for part in pure.parts
    ):
        raise ArtifactValidationError("INVALID_ARCHIVE", "Archive path is too long")
    if len(pure.parts) > settings.max_archive_depth:
        raise ArtifactValidationError("INVALID_ARCHIVE", "Archive path depth exceeds limit")
    if info.flag_bits & 0x1:
        raise ArtifactValidationError("INVALID_ARCHIVE", "Encrypted ZIP entries are not accepted")
    if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
        raise ArtifactValidationError("INVALID_ARCHIVE", "Unsupported ZIP compression method")
    mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(mode)
    if file_type not in {0, stat.S_IFREG, stat.S_IFDIR} or stat.S_ISLNK(mode):
        raise ArtifactValidationError("INVALID_ARCHIVE", "Archive contains a special file")
    if not info.is_dir() and mode & 0o111:
        raise ArtifactValidationError("UNSUPPORTED_FILE", "Executable permission bits are not accepted")
    return pure.as_posix().rstrip("/")


def _validate_allowed_path(path: str, allowed_paths: set[str]) -> None:
    lower = path.lower()
    suffix = Path(lower).suffix
    if suffix in FORBIDDEN_SUFFIXES or Path(lower).name == "pytorch_model.bin":
        raise ArtifactValidationError("UNSUPPORTED_FILE", f"Forbidden file type: {suffix or lower}")
    if path not in allowed_paths and not MODEL_SHARD_RE.fullmatch(path):
        raise ArtifactValidationError("UNSUPPORTED_FILE", "Path is not in the task artifact allowlist")


def _extract_checked(
    archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], root: Path, limit: int
) -> list[Path]:
    root.mkdir(parents=True, mode=0o700)
    root_resolved = root.resolve()
    extracted: list[Path] = []
    total = 0
    for info in infos:
        target = root / PurePosixPath(info.filename)
        resolved = target.resolve(strict=False)
        if root_resolved not in resolved.parents:
            raise ArtifactValidationError("INVALID_ARCHIVE", "Archive extraction escaped root")
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with archive.open(info, "r") as source, target.open("xb") as output:
            os.chmod(target, 0o600)
            while chunk := source.read(1_048_576):
                total += len(chunk)
                if total > limit or output.tell() + len(chunk) > info.file_size:
                    raise ArtifactValidationError("MODEL_TOO_LARGE", "Extracted bytes exceed declared limit")
                output.write(chunk)
        if target.stat().st_size != info.file_size:
            raise ArtifactValidationError("INVALID_ARCHIVE", "Extracted size differs from central directory")
        extracted.append(target)
    return extracted


def _reject_disguised_executable(path: Path) -> None:
    with path.open("rb") as file:
        prefix = file.read(8)
    if any(prefix.startswith(signature) for signature in EXECUTABLE_SIGNATURES):
        raise ArtifactValidationError("UNSUPPORTED_FILE", "Executable signature found in allowed path")
    if prefix.startswith(b"\x80") and path.suffix != ".safetensors":
        raise ArtifactValidationError("UNSUPPORTED_FILE", "Possible pickle payload found")


def _load_safe_json(path: Path, settings: Settings) -> dict[str, Any]:
    if path.stat().st_size > settings.max_json_bytes:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "JSON file exceeds size limit")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Invalid JSON artifact") from exc
    return validate_json_metadata(value, settings)


def validate_json_metadata(value: Any, settings: Settings) -> dict[str, Any]:
    """Shared data-only JSON checks, also usable for already parsed contract metadata."""
    if not isinstance(value, dict):
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "JSON artifact root must be an object")
    keys = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal keys
        if depth > settings.max_json_depth:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "JSON nesting exceeds limit")
        if isinstance(item, dict):
            keys += len(item)
            if keys > settings.max_json_keys:
                raise ArtifactValidationError("INVALID_MODEL_FORMAT", "JSON key count exceeds limit")
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > settings.max_json_string_length:
                    raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Invalid JSON key")
                if key in {"auto_map", "custom_pipelines", "custom_code"}:
                    raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Custom module configuration is forbidden")
                if key == "trust_remote_code" and child is not False:
                    raise ArtifactValidationError("INVALID_MODEL_FORMAT", "trust_remote_code must be false")
                walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
        elif isinstance(item, str):
            if len(item) > settings.max_json_string_length:
                raise ArtifactValidationError("INVALID_MODEL_FORMAT", "JSON string exceeds limit")
            if URL_RE.search(item) or item.startswith(("/", "\\")) or WINDOWS_DRIVE_RE.match(item):
                raise ArtifactValidationError("INVALID_MODEL_FORMAT", "External URL or absolute path is forbidden")
        elif isinstance(item, (int, float)) and (not math.isfinite(item) or abs(item) > 10**18):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "JSON numeric value is outside policy")

    walk(value, 0)
    return value


def _validate_model_config(
    config: dict[str, Any],
    submission: dict[str, Any],
    allowed_models: list[str],
    allowed_architectures: set[str],
) -> None:
    submission_base = submission.get("base_model")
    config_base = config.get("_name_or_path")
    if (
        not isinstance(submission_base, str)
        or not isinstance(config_base, str)
        or submission_base != config_base
        or submission_base not in allowed_models
    ):
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Base model is not registered for this task")
    architectures = config.get("architectures")
    if not isinstance(architectures, list) or not architectures or not all(
        isinstance(item, str) for item in architectures
    ):
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Model architectures are missing")
    if not allowed_architectures or any(item not in allowed_architectures for item in architectures):
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Model architecture is not registered")


def _validate_safetensors(
    path: Path,
    *,
    settings: Settings,
    allowed_dtypes: set[str],
    max_tensor_bytes: int,
) -> tuple[int, int, set[str]]:
    file_size = path.stat().st_size
    if file_size < 8:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors file is truncated")
    with path.open("rb") as file:
        header_size = struct.unpack("<Q", file.read(8))[0]
        if header_size > settings.max_safetensors_header_bytes or header_size + 8 > file_size:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors header is invalid")
        try:
            header = json.loads(file.read(header_size).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors header JSON is invalid") from exc
    tensors = {key: value for key, value in header.items() if key != "__metadata__"}
    if not tensors or len(tensors) > settings.max_safetensors_tensors:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors tensor count is invalid")
    total = 0
    for name, tensor in tensors.items():
        if not isinstance(name, str) or len(name) > settings.max_tensor_name_length or not isinstance(tensor, dict):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors tensor name is invalid")
        dtype = tensor.get("dtype")
        shape = tensor.get("shape")
        offsets = tensor.get("data_offsets")
        if dtype not in allowed_dtypes or dtype not in DTYPE_BYTES:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors dtype is not allowed")
        if not isinstance(shape, list) or not all(
            isinstance(dim, int) and not isinstance(dim, bool) and 0 <= dim <= settings.max_tensor_dimension
            for dim in shape
        ):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors shape is invalid")
        if not isinstance(offsets, list) or len(offsets) != 2 or not all(isinstance(x, int) for x in offsets):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors data offsets are invalid")
        expected = math.prod(shape) * DTYPE_BYTES[dtype]
        if offsets[1] - offsets[0] != expected:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors byte range is inconsistent")
        total += expected
        if total > max_tensor_bytes:
            raise ArtifactValidationError("MODEL_TOO_LARGE", "Tensor bytes exceed task limit")
    try:
        with safe_open(path, framework="numpy") as parsed:
            if set(parsed.keys()) != set(tensors):
                raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors parser key mismatch")
            for name in parsed.keys():
                parsed.get_slice(name).get_shape()
    except ArtifactValidationError:
        raise
    except Exception as exc:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors parser rejected the file") from exc
    return len(tensors), total, set(tensors)


def _validate_safetensors_index(
    index: dict[str, Any] | None,
    tensor_paths: list[Path],
    tensor_names: set[str],
    extract_root: Path,
) -> None:
    if len(tensor_paths) > 1 and index is None:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Sharded weights require an index")
    if index is None:
        return
    weight_map = index.get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors index has no weight_map")
    known_paths = {path.relative_to(extract_root).as_posix() for path in tensor_paths}
    indexed_names: set[str] = set()
    for tensor_name, filename in weight_map.items():
        if not isinstance(tensor_name, str) or not isinstance(filename, str):
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors index entry is invalid")
        normalized = filename if filename.startswith("model/") else f"model/{filename}"
        if normalized not in known_paths or tensor_name not in tensor_names:
            raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors index references unknown data")
        indexed_names.add(tensor_name)
    if indexed_names != tensor_names:
        raise ArtifactValidationError("INVALID_MODEL_FORMAT", "Safetensors index is incomplete")
