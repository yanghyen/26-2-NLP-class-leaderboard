"""Server-code test entry point: real tiny BERT inference or intentional hangs/errors."""
import argparse
import json
import os
import time
from pathlib import Path

from app.evaluators.lab02_runtime import infer_and_score, library_versions
from app.evaluators.local_data import load_dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request")
    parser.add_argument("--result")
    args = parser.parse_args()
    payload = json.loads(Path(args.request).read_text())
    if payload.get("test_mode") == "sleep":
        Path(payload["pid_file"]).write_text(str(os.getpid()))
        time.sleep(60)
    texts, labels, metadata = load_dataset(payload["dataset_config"])
    root = Path(payload["resources_root"])
    output = infer_and_score(Path(payload["artifact_dir"]), texts, labels,
                             server_config=json.loads((root / "config.json").read_text()),
                             tokenizer_dir=root, device=payload["device"],
                             batch_size=payload["batch_size"], seed=payload["seed"])
    result = dict(primary_metric="macro_f1", primary_score=output["metrics"]["macro_f1"],
                  secondary_metrics={"accuracy": output["metrics"]["accuracy"]},
                  evaluator_version=payload["evaluator_version"], dataset_version=payload["dataset_version"],
                  evaluation_metadata=dict(dataset_sha256=payload["dataset_config"]["sha256"],
                                           sample_count=len(labels), libraries=library_versions(), device="cpu"))
    Path(args.result).write_text(json.dumps({"result": result}))


if __name__ == "__main__":
    main()
