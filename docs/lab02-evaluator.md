# Lab02 sentiment evaluator

## Scope and fixed policy

`lab02_sentiment_v1` is explicitly registered alongside unchanged `mock_v1`/`mock`.
No existing Task changes automatically. The model is server-created
`BertForSequenceClassification`, full-model safetensors, labels 0=negative and
1=positive. Student config is compared against the contract and server dimensions;
it never selects a class or triggers `from_pretrained` on a student directory.
Tokenizer is the fixed local server `BertTokenizerFast`, uncased, right truncation,
128 tokens including special tokens. Raw review text is unchanged: no HTML
stripping, Notebook execution, or student preprocessing code.

Pinned public sources:

- Model/config and tokenizer: `google-bert/bert-base-uncased` revision
  `86b5e0934494bd15c9632b12f734a8a67f723594`.
  [Immutable model snapshot](https://huggingface.co/google-bert/bert-base-uncased/tree/86b5e0934494bd15c9632b12f734a8a67f723594)
- IMDb: `stanfordnlp/imdb`, revision
  `e6281661ce1c48d982bc483cf8a173c1bbeb5d31`, public **test** split.
  [Immutable dataset snapshot](https://huggingface.co/datasets/stanfordnlp/imdb/tree/e6281661ce1c48d982bc483cf8a173c1bbeb5d31)

IMDb test is temporary **public** evaluation data, not a hidden dataset. Full
leaderboard configuration must use all 25,000 test reviews. Scores on this data
are not directly comparable to a later replacement dataset. The Notebook should
use the same model/tokenizer revision in its pretrained-loading calls; do not
require new manifest fields or change the existing three-file ZIP format.

## Administrator preparation

Install the real-evaluator dependencies in the backend environment:

```bash
cd backend
.venv/bin/pip install -r requirements-lab02.txt
.venv/bin/python -m app.scripts.prepare_lab02 model --output /srv/lab02/resources
.venv/bin/python -m app.scripts.prepare_lab02 imdb --output /srv/lab02/imdb-public-test-v1
```

Use writable administrator directories appropriate to the host. Preparation
refuses to overwrite an existing output. The model command downloads only the
pinned config/tokenizer files, never pretrained weights. It writes `resources.json`
with revisions and SHA-256 for each server file. The data command downloads only
the pinned test Parquet and writes ordered `reviews.jsonl` plus `metadata.json`
with source/revision/split/scope/version/count/SHA-256. It prints the dataset
configuration to put in the Task. Jobs never download either resource.

For a distinct development dataset:

```bash
.venv/bin/python -m app.scripts.prepare_lab02 imdb --output /srv/lab02/imdb-smoke-8 --limit 8
```

This is a separate `smoke` identity, never the full-test identity. It takes the
first N records without shuffling; that is a pipeline check, not a performance
estimate or class-balanced benchmark. The actual verification in this work used
indices 0, 1, 12500 and 12501 under a separate four-review smoke version.

## Data schema and replacement

Each UTF-8 JSONL record has exactly:

```json
{"text":"review text","label":0}
```

Text must be a non-empty string; label must be integer 0 or 1, not boolean/string.
Empty data, blank/malformed records and extra fields fail the entire evaluation.
The evaluator checks version, byte SHA-256 and exact sample count against both
the Task config and sidecar metadata. It preserves file order and evaluates every
sample. No sample is silently skipped.

Prepare a replacement with the same schema without any IMDb dependency:

```bash
.venv/bin/python -m app.scripts.prepare_lab02 local \
  --input /srv/source/new-reviews.jsonl --output /srv/lab02/new-data-v1 --version course-new-data-v1
```

Create a separate Task for each dataset when possible. Otherwise explicitly
update the Task's entire `dataset_config` to the preparation output. Do not relabel
old scores or reuse old sidecars. The current leaderboard/CSV representative
selection excludes a Submission whose evaluator/dataset identity differs from
the current Task. Mock, old datasets and old evaluation policies cannot win the
new leaderboard. Counts/history and individual scores remain for audit.

The pinned Baseline reference is preserved. An old-identity Baseline becomes
unavailable, so improvement is null until an administrator explicitly resets it
to a newly successful same-task/participant Baseline. The reset API rejects an
incompatible version. Automatic first-Baseline behavior is unchanged. Successful
submission files are deleted after commit; old submissions usually cannot be
reevaluated. Students must keep/reupload their files; official files belong in
e-Class LMS. Never manufacture replacement scores or undo retention to migrate.

## Task activation and runtime settings

Set the same profile settings on API and Worker, then restart both:

```bash
export LAB02_RESOURCES_ROOT=/srv/lab02/resources
export LAB02_DEVICE=cpu             # or cuda; unavailable CUDA is a configuration error
export LAB02_BATCH_SIZE=8
export LAB02_SEED=42
```

CPU supports genuine smoke tests. Full CPU evaluation may need a much longer
Task timeout; no full-set timing was benchmarked here. CUDA is supported in code
but requires a suitable PyTorch/GPU environment and was not verified on this Mac.
The existing Docker image installs baseline dependencies only: a real-evaluator
deployment must additionally install `requirements-lab02.txt` and provide
read-only prepared resources/data. Existing container security settings must be
kept; this work does not claim a verified GPU image or container deployment.

In the authenticated task editor, select Lab02 and paste the preparation JSON;
set allowed models/architecture to the contract. Equivalently use Task POST/PATCH:

```json
{
  "evaluator_key":"lab02_sentiment_v1",
  "timeout_seconds":14400,
  "config":{
    "allowed_models":["google-bert/bert-base-uncased"],
    "artifact_policy":{"allowed_architectures":["BertForSequenceClassification"]},
    "metric_config":{"primary":"macro_f1","scale":"0_1"},
    "dataset_config":{
      "path":"/srv/lab02/imdb-public-test-v1/reviews.jsonl",
      "metadata_path":"/srv/lab02/imdb-public-test-v1/metadata.json",
      "version":"COPY_THE_PREPARATION_OUTPUT",
      "sha256":"COPY_THE_64_CHARACTER_SHA256",
      "sample_count":25000
    }
  }
}
```

The timeout is an example for CPU, not a guaranteed full-set duration. Task creation
also needs its existing slug/title fields. Model/metric/scale/data schema checks
happen before saving the selection. For real or mixed Tasks, set the existing frontend
`NEXT_PUBLIC_SHOW_MOCK_EVALUATION=false` at build time to hide the global development
Mock badge; individual results display their stored `macro_f1` or `mock_score` metric. Missing/tampered prepared resources fail at
Job execution with a safe configuration error, not network fallback.

## Execution, metadata and safety

Each Job launches fixed server code in a fresh subprocess. Model construction uses
the hashed server config; tokenizer loading is `local_files_only=True` and
`trust_remote_code=False`. Safetensors are the sole weight format: missing/extra
keys, shape mismatches, non-floating dtypes (only F32/F16/BF16 accepted), NaN/Inf
weights or logits are rejected. No `.pt`, `.bin`, pickle, Notebook or submitted
Python is loaded. Existing ZIP/link/bomb/JSON/safetensors validation remains.

Inference uses `model.eval()`, `torch.inference_mode()`, a fixed batch size and
one chosen device for model and inputs. Predictions are `logits.argmax`; metrics
are computed once over all labels/predictions: Macro F1 with labels `[0,1]`,
`average="macro"`, `zero_division=0`, plus Accuracy. Both are 0–1, higher is better.

The Worker supplies the overall monotonic deadline, including process startup.
On timeout the parent terminates the process group, escalates to SIGKILL if needed,
and waits for exit before returning. Scratch files are removed on success/failure.
Linux parent-death signaling and a parent watcher stop orphan inference; no model
or GPU state is reused across Jobs. CUDA OOM/MemoryError are resource-limit errors;
data/config/weight/timeout errors are non-retryable safe codes, while unexpected
server failures retain the existing infrastructure retry policy. Concurrency is 1.

The child receives no API/DB credentials or user Python import paths. HF network
fallback/telemetry is disabled. Aggregate results are bounded JSON; review text,
labels, predictions, paths and traceback never enter public results. Native/error
diagnostics are internal server logs only. This subprocess isolates lifecycle and
timeout; it is **not** a network/filesystem namespace or hostile-model production
container. The stronger per-Job production boundary in `submission-security.md`
still applies. No existing Docker/capability/read-only security rule is relaxed.

Submission stores result versions and safe `validation_report.evaluation` metadata:
data hash/source/revision/scope/count, model/tokenizer revisions, length/truncation,
device/batch/seed, elapsed seconds and library versions. Evaluator identity hashes
the fixed revisions/policy/library pins/runtime profile. Dataset identity combines
the configured version and file SHA-256. Scores/metadata/success/Baseline pin commit
before the existing artifact deletion and deletion-status commit.

## Verification boundary

Network-independent tests generate a real tiny server BERT/tokenizer and safetensors
in temporary directories and execute real loading/inference, including a Job child
process. That test-only entry point never appears in Task config or the registry.
The production runner additionally enforces the full pinned BERT-base dimensions.

The provided full Lab2 ZIP also passed production validation, CPU model loading,
four-review public IMDb smoke inference, metric calculation, SQLite Worker saving,
leaderboard inclusion and artifact-copy deletion. Macro F1 was 0.7333333333333334,
Accuracy 0.75 on those four samples; these are **not** full IMDb leaderboard scores.
The original supplied ZIP was preserved. That initial smoke check did not verify
full IMDb, CUDA/GPU, real Redis/PostgreSQL or Docker. The 2026-10-16 follow-up verified
real Redis, a separate PostgreSQL server, actual HTTP uploads, CPU inference,
Baseline/Development aggregation, cleanup and interrupted Worker recovery.
See [operations verification](lab02-operations-verification.md) for evidence,
the user-run browser checklist and remaining Docker/GPU checks. No existing
server/database was touched; no new migration is required.
