"""Administrator preparation only: download pinned metadata/tokenizer or IMDb, never per Job."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

from app.evaluators.lab02_contract import LAB02_CONTRACT
from app.evaluators.lab02_policy import IMDB_REVISION, MODEL_REVISION, TOKENIZER_REVISION
from app.evaluators.lab02_runtime import RESOURCE_FILES, server_resources, sha256_file
from app.evaluators.local_data import read_records, valid_record


def publish_dataset(records, output: Path, *, version: str, source: str, revision=None, scope="local") -> dict:
    if output.exists() or output.is_symlink() or not version.strip() or len(version) > 160:
        raise ValueError("Use a new output directory and a non-empty dataset version")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as staging:
        root = Path(staging)
        digest = hashlib.sha256()
        count = 0
        with (root / "reviews.jsonl").open("wb") as stream:
            for record in records:
                if not valid_record(record):
                    raise ValueError("Invalid local dataset schema")
                line = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                stream.write(line)
                digest.update(line)
                count += 1
        if count == 0 or (source == "stanfordnlp/imdb" and scope == "full" and count != 25000):
            raise ValueError("Dataset is empty or not the complete IMDb test split")
        metadata = dict(version=version, sha256=digest.hexdigest(), sample_count=count,
                        source=source, revision=revision, split="test" if source == "stanfordnlp/imdb" else None,
                        scope=scope)
        (root / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        # Rename the complete pair atomically, without overwriting existing prepared data.
        root.rename(output)
    return dict(path=str((output / "reviews.jsonl").resolve()),
                metadata_path=str((output / "metadata.json").resolve()),
                version=version, sha256=metadata["sha256"], sample_count=count)


def prepare_model(output: Path) -> None:
    from huggingface_hub import snapshot_download
    if output.exists() or output.is_symlink():
        raise ValueError("Use a new server resource directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as staging:
        root = Path(staging)
        downloaded = Path(snapshot_download(LAB02_CONTRACT.base_model, revision=MODEL_REVISION,
                                            allow_patterns=list(RESOURCE_FILES), cache_dir=root / "cache", token=False))
        resource_dir = root / "resources"
        resource_dir.mkdir()
        for name in RESOURCE_FILES:
            shutil.copyfile(downloaded / name, resource_dir / name)
        metadata = dict(model_id=LAB02_CONTRACT.base_model, model_revision=MODEL_REVISION,
                        tokenizer_revision=TOKENIZER_REVISION,
                        files={name: sha256_file(resource_dir / name) for name in RESOURCE_FILES})
        (resource_dir / "resources.json").write_text(json.dumps(metadata, indent=2))
        server_resources(resource_dir)
        resource_dir.rename(output)


def prepare_imdb(output: Path, limit: int | None = None) -> dict:
    from datasets import load_dataset
    from huggingface_hub import hf_hub_download
    if limit is not None and not 1 <= limit < 25000:
        raise ValueError("Smoke limit must be between 1 and 24999")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as cache:
        parquet = hf_hub_download("stanfordnlp/imdb", repo_type="dataset", revision=IMDB_REVISION,
                                  filename="plain_text/test-00000-of-00001.parquet", cache_dir=cache, token=False)
        dataset = load_dataset("parquet", data_files={"test": parquet}, split="test", cache_dir=cache)
        scope = "full" if limit is None else "smoke"
        records = (dict(text=row["text"], label=row["label"]) for row in
                   (dataset if limit is None else dataset.select(range(limit))))
        version = f"imdb-public-test-{scope}-{25000 if limit is None else limit}@{IMDB_REVISION}"
        return publish_dataset(records, output, version=version, source="stanfordnlp/imdb",
                               revision=IMDB_REVISION, scope=scope)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    model = subparsers.add_parser("model")
    model.add_argument("--output", type=Path, required=True)
    imdb = subparsers.add_parser("imdb")
    imdb.add_argument("--output", type=Path, required=True)
    imdb.add_argument("--limit", type=int, help="Smoke only: creates a distinct dataset identity")
    local = subparsers.add_parser("local")
    local.add_argument("--input", type=Path, required=True)
    local.add_argument("--output", type=Path, required=True)
    local.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "model":
        prepare_model(args.output)
        print("Pinned server model config and tokenizer prepared")
    elif args.command == "imdb":
        print(json.dumps(prepare_imdb(args.output, args.limit), indent=2))
    else:
        texts, labels, _ = read_records(args.input)
        print(json.dumps(publish_dataset((dict(text=t, label=l) for t, l in zip(texts, labels)),
                                        args.output, version=args.version, source="local"), indent=2))


if __name__ == "__main__":
    main()
