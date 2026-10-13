"""Lab02 evaluator with a per-Job hard deadline and deterministic offline subprocess."""
import json
import os
import signal
import subprocess
import sys
import time
import logging
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import get_settings
from app.evaluators.base import EvaluationRequest, EvaluationResult, Evaluator
from app.evaluators.errors import SAFE_EVALUATOR_MESSAGES, EvaluatorError
from app.evaluators.lab02_policy import evaluation_identity, validate_dataset_config

logger = logging.getLogger(__name__)


def terminate_process(process: subprocess.Popen) -> None:
    if process.poll() is None:
        try:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
            process.wait()


def run_subprocess(payload: dict, *, deadline: float, work_dir: Path | None,
                   module: str = "app.evaluators.lab02_runner") -> dict:
    # module is a server-code/testing injection point, never read from Task/student data.
    with TemporaryDirectory(prefix="lab02-", dir=work_dir) as directory:
        request_path = Path(directory) / "request.json"
        result_path = Path(directory) / "result.json"
        request_path.write_text(json.dumps(payload), encoding="utf-8")
        # Do not pass API/DB credentials or user import paths to the model process.
        env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT",
                                         "CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER") if k in os.environ}
        env.update(HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   TOKENIZERS_PARALLELISM="false", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1",
                   HF_HOME=str(Path(directory) / "hf"), HF_HUB_DISABLE_TELEMETRY="1",
                   LAB02_PARENT_PID=str(os.getpid()), PYTHONHASHSEED=str(payload.get("seed", 42)))
        if time.monotonic() >= deadline:
            raise EvaluatorError("EVALUATION_TIMEOUT")
        error_path = Path(directory) / "stderr.log"
        error_log = error_path.open("wb")
        try:
            process = subprocess.Popen([sys.executable, "-m", module, "--request", str(request_path),
                                        "--result", str(result_path)], cwd=Path(__file__).parents[2],
                                       env=env, stdout=subprocess.DEVNULL, stderr=error_log,
                                       start_new_session=True)
        except Exception:
            error_log.close()
            raise
        try:
            try:
                process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                terminate_process(process)
                raise EvaluatorError("EVALUATION_TIMEOUT") from None
            if process.returncode != 0:
                with error_path.open("rb") as source:
                    source.seek(max(0, error_path.stat().st_size - 4096))
                    logger.error("Evaluator subprocess diagnostic: %s", source.read().decode(errors="replace"))
                if process.returncode in (-signal.SIGKILL, -signal.SIGTERM):
                    raise EvaluatorError("EVALUATION_RESOURCE_LIMIT")
                raise RuntimeError("Evaluation subprocess failed")
            if not result_path.is_file() or result_path.stat().st_size > 100000:
                raise RuntimeError("Evaluation subprocess returned no bounded result")
            try:
                message = json.loads(result_path.read_text())
                if not isinstance(message, dict):
                    raise ValueError
            except (OSError, ValueError):
                raise RuntimeError("Evaluation subprocess returned an invalid result") from None
            if "error" in message:
                if message["error"] in SAFE_EVALUATOR_MESSAGES:
                    raise EvaluatorError(message["error"])
                raise RuntimeError("Evaluation server failure")
            try:
                result = message["result"]
                if (result["primary_metric"] != "macro_f1"
                        or result["evaluator_version"] != payload["evaluator_version"]
                        or result["dataset_version"] != payload["dataset_version"]
                        or result["evaluation_metadata"]["sample_count"] != payload["dataset_config"]["sample_count"]):
                    raise ValueError
                for metric in (result["primary_score"], result["secondary_metrics"]["accuracy"]):
                    if type(metric) not in (int, float) or not math.isfinite(metric) or not 0 <= metric <= 1:
                        raise ValueError
                return result
            except (KeyError, TypeError, ValueError):
                raise RuntimeError("Evaluation subprocess returned an invalid score") from None
        finally:
            terminate_process(process)
            error_log.close()


class Lab02Evaluator(Evaluator):
    key = "lab02_sentiment_v1"

    def evaluate(self, request: EvaluationRequest) -> EvaluationResult:
        settings = get_settings()
        validate_dataset_config(request.context.dataset_config)
        if request.validated_metadata.get("model", {}).get("safetensors_validated") is not True:
            raise EvaluatorError("MODEL_WEIGHTS_INVALID")
        evaluator_version, dataset_version = evaluation_identity(request.context.dataset_config, settings)
        payload = dict(artifact_dir=str(request.artifact_path), dataset_config=request.context.dataset_config,
                       resources_root=str(Path(settings.lab02_resources_root).resolve()),
                       device=settings.lab02_device, batch_size=settings.lab02_batch_size, seed=settings.lab02_seed,
                       evaluator_version=evaluator_version, dataset_version=dataset_version)
        payload["dataset_config"] = {k: request.context.dataset_config[k] for k in
                                     ("path", "metadata_path", "version", "sha256", "sample_count")}
        result = run_subprocess(payload, deadline=request.context.deadline_monotonic or time.monotonic() + 900,
                                work_dir=request.context.work_dir)
        request.context.begin_scoring()
        return EvaluationResult(**result)
