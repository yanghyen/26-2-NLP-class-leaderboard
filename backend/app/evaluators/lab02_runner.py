"""Fixed subprocess entry point. Reads local files only and emits aggregate results only."""
import argparse
import json
import os
import time
import threading
import sys
from pathlib import Path

from app.evaluators.errors import EvaluatorError
from app.evaluators.lab02_policy import MODEL_REVISION, TOKENIZER_REVISION
from app.evaluators.lab02_runtime import infer_and_score, library_versions, server_resources
from app.evaluators.local_data import load_dataset


def run(payload: dict) -> dict:
    started = time.monotonic()
    versions = library_versions()
    resources = Path(payload["resources_root"])
    fixed_config = server_resources(resources)
    texts, labels, data_metadata = load_dataset(payload["dataset_config"])
    output = infer_and_score(Path(payload["artifact_dir"]), texts, labels,
                             server_config=fixed_config, tokenizer_dir=resources,
                             device=payload["device"], batch_size=payload["batch_size"], seed=payload["seed"])
    return dict(primary_metric="macro_f1", primary_score=output["metrics"]["macro_f1"],
                secondary_metrics={"accuracy": output["metrics"]["accuracy"]},
                evaluator_version=payload["evaluator_version"], dataset_version=payload["dataset_version"],
                evaluation_metadata=dict(dataset_sha256=payload["dataset_config"]["sha256"],
                    sample_count=output["sample_count"], dataset_source=data_metadata.get("source", "local"),
                    dataset_revision=data_metadata.get("revision"), dataset_scope=data_metadata.get("scope", "local"),
                    base_model="google-bert/bert-base-uncased", model_revision=MODEL_REVISION,
                    tokenizer_revision=TOKENIZER_REVISION, max_length=128, truncation="right",
                    preprocessing="none", device=payload["device"], batch_size=payload["batch_size"],
                    seed=payload["seed"], execution_seconds=time.monotonic() - started, libraries=versions))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    parent_pid = int(os.environ.get("LAB02_PARENT_PID", os.getppid()))
    def watch_parent():
        while os.getppid() == parent_pid:
            time.sleep(.25)
        os._exit(124)
    threading.Thread(target=watch_parent, daemon=True).start()
    if sys.platform.startswith("linux"):
        import ctypes
        import signal
        ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0)  # PR_SET_PDEATHSIG
        if os.getppid() != parent_pid:
            os._exit(124)
    os.environ.update(HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                      TOKENIZERS_PARALLELISM="false")
    try:
        payload = json.loads(Path(args.request).read_text())
        result = {"result": run(payload)}
    except EvaluatorError as exc:
        result = {"error": exc.code}
    except Exception:
        # Exception text, data, labels, predictions and traceback never cross the result boundary.
        result = {"error": "EVALUATION_SERVER_ERROR"}
    Path(args.result).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
