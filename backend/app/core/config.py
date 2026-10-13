from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NLP Course Leaderboard"
    app_env: Literal["development", "test", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    app_secret_key: str = Field(default="dev-secret-change-me", alias="APP_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=720, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    database_url: str = Field(default="sqlite:///./dev.db", alias="DATABASE_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    storage_root: str = Field(default="./storage/submissions", alias="STORAGE_ROOT")
    queue_name: str = Field(default="evaluation_jobs", alias="QUEUE_NAME")
    lab02_resources_root: str = Field(default="./storage/lab02/resources", alias="LAB02_RESOURCES_ROOT")
    lab02_device: Literal["cpu", "cuda"] = Field(default="cpu", alias="LAB02_DEVICE")
    lab02_batch_size: int = Field(default=8, ge=1, le=64, alias="LAB02_BATCH_SIZE")
    lab02_seed: int = Field(default=42, ge=0, le=2**32-1, alias="LAB02_SEED")
    upload_chunk_bytes: int = Field(default=1_048_576, alias="UPLOAD_CHUNK_BYTES")
    max_notebook_bytes: int = Field(default=20_000_000, alias="MAX_NOTEBOOK_BYTES")
    max_notebook_cells: int = Field(default=1_000, alias="MAX_NOTEBOOK_CELLS")
    max_notebook_source_chars: int = Field(default=2_000_000, alias="MAX_NOTEBOOK_SOURCE_CHARS")
    max_notebook_output_bytes: int = Field(default=10_000_000, alias="MAX_NOTEBOOK_OUTPUT_BYTES")
    max_archive_files: int = Field(default=256, alias="MAX_ARCHIVE_FILES")
    max_archive_depth: int = Field(default=8, alias="MAX_ARCHIVE_DEPTH")
    max_archive_ratio: float = Field(default=200.0, alias="MAX_ARCHIVE_RATIO")
    max_archive_path_length: int = Field(default=240, alias="MAX_ARCHIVE_PATH_LENGTH")
    max_archive_filename_length: int = Field(default=120, alias="MAX_ARCHIVE_FILENAME_LENGTH")
    max_json_bytes: int = Field(default=5_000_000, alias="MAX_JSON_BYTES")
    max_json_depth: int = Field(default=20, alias="MAX_JSON_DEPTH")
    max_json_keys: int = Field(default=10_000, alias="MAX_JSON_KEYS")
    max_json_string_length: int = Field(default=1_000_000, alias="MAX_JSON_STRING_LENGTH")
    max_safetensors_header_bytes: int = Field(default=10_000_000, alias="MAX_SAFETENSORS_HEADER_BYTES")
    max_safetensors_tensors: int = Field(default=100_000, alias="MAX_SAFETENSORS_TENSORS")
    max_tensor_name_length: int = Field(default=512, alias="MAX_TENSOR_NAME_LENGTH")
    max_tensor_dimension: int = Field(default=1_000_000, alias="MAX_TENSOR_DIMENSION")
    malware_scanner: str = Field(default="disabled", alias="MALWARE_SCANNER")
    cors_origins: list[AnyHttpUrl | str] = Field(default=["http://localhost:3000"], alias="CORS_ORIGINS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
