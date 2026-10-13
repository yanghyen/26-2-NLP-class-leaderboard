# Evaluator interface and Lab02 contract

## Current executable boundary

`mock_v1` and `lab02_sentiment_v1` are registered in `app/evaluators/registry.py`. Historical DB/API
`mock` keys are an explicit compatibility alias; newly created/edited Tasks store
`mock_v1`. `Task.evaluator_key` already exists, so no DB migration is required.
Task title, slug, submitted filenames and student metadata never select code.
The registry is a fixed mapping of server-owned evaluators: no dynamic imports,
module paths, commands or student code are evaluated.

`lab02_sentiment_v1` now runs offline BERT sentiment inference in a Job subprocess.
Its Task must have prepared local data metadata and the Lab02 model/metric policy;
otherwise selection returns `EVALUATOR_CONFIG_INVALID`. Unknown keys still return
`UNKNOWN_EVALUATOR`. Existing Tasks are not automatically switched. See
`docs/lab02-evaluator.md` for preparation, resource settings, dataset replacement
and the production isolation boundary.

## Common interface

`EvaluationRequest` is an internal frozen dataclass with submission/task IDs,
explicit evaluator key, the validated/extracted artifact directory, validated
manifest, safe validation metadata, and `EvaluationContext`. Context retains
split, task/dataset/metric config, digest, allowlisted models and immutable
`trust_remote_code=False`. Paths and Worker callbacks are never public schemas.

`Evaluator.evaluate(request) -> EvaluationResult` is the sole evaluation entry
point used by the Worker. `EvaluationResult` contains `primary_metric`,
`primary_score`, `secondary_metrics`, `evaluator_version`, and `dataset_version`.
There is no new public metadata/paths payload. Existing public APIs still omit
arbitrary evaluator metrics and private scores; secondary metrics remain in DB.
`cleanup(request)` is a server-side resource cleanup hook and is independent of
the artifact retention service.

After validation/preparation/inference, a staged evaluator calls
`request.context.begin_scoring()`. It performs the Worker timeout checkpoint and
commits RUNNING -> SCORING for Job/Submission. A one-shot evaluator can simply
return the result; the Worker then enters SCORING before saving it. After `evaluate` returns, the Worker
checks timeout again, saves Score and result versions, pins Baseline, commits
COMPLETED/pending cleanup, then deletes artifacts through the existing separate
transaction. Evaluator implementations do not write scores or delete artifacts.
Existing student-error, timeout and infrastructure retry behavior remains;
configuration errors get their own safe code and are not retried as inference.

Mock's existing staged helpers remain internal hooks for regression/failure
fixtures. The digest computation, score rounding, `mock_score`, and secondary
`{mock_score, deterministic: true}` metrics are unchanged. Golden values from
checkpoint b5833e7 verify compatibility. Its evaluator version stays `mock-v1`;
default dataset version is the fixed `mock-dataset-v1` (no real dataset). Explicit
historical `dataset_config.dataset_version` or `dataset_config.version` values
remain compatible. Submission version fields already exist and store result
versions in the successful score transaction.

## Lab02 sentiment contract

Contract key: `lab02_sentiment_v1`. Required `manifest.json` fields:

```json
{
  "format_version": "1.0",
  "task": "sentiment",
  "base_model": "google-bert/bert-base-uncased",
  "architecture": "BertForSequenceClassification",
  "artifact_type": "full_model",
  "num_labels": 2,
  "label_mapping": {"0": "negative", "1": "positive"}
}
```

Types are exact: `num_labels` is integer 2, not boolean, float or string.
The label order is index 0=negative, index 1=positive. JSON object insertion order
does not change that mapping. Extra safe descriptive metadata is not used to
select code or change evaluation policy. If `max_length` or `tokenizer_source`
is declared, it must match the server policy.

Server policy is a fixed server-provided tokenizer, `max_length=128`, primary
`macro_f1`, secondary `accuracy`. These are not required fields in the notebook
manifest, and no student tokenizer/config can change them. Tokenizer provisioning is performed by the admin preparation command; Jobs use
only the prepared local server tokenizer.

The ZIP must contain exactly three top-level regular files, without extra
directories, execution code, tokenizer files or nested model layouts:

- `manifest.json`
- `config.json`
- `model.safetensors`

`config.json` must declare `model_type="bert"` and the exact architecture list
`["BertForSequenceClassification"]`. Explicit `num_labels` must be integer 2.
The actual supplied notebook config omits `num_labels` and uses `id2label`; that
format is accepted. Supplied `id2label`/`label2id` must match the contract, and
`_name_or_path`, if present, must match the registered base model. Missing both
`num_labels` and `id2label` cannot establish cardinality and is rejected.
Safe JSON checks reject `auto_map`, custom code, remote-code requests, external
URLs/absolute paths and oversized/nested values; no student architecture is run.

## Validation entry points and fixtures

`validate_lab02_contract(manifest, config, artifact_files,
safetensors_validated=...)` checks already-parsed metadata. The security flag
must be a trusted server result, never a submitted manifest assertion. False or
missing security validation must not be treated as a valid model. This function
does not load weights or perform inference.

`validate_and_extract_model_zip(..., contract_key="lab02_sentiment_v1")` reuses
existing ZIP envelope/path/link/bomb/allowlist checks, confined extraction,
data-only JSON validation, executable detection and safetensors parsing before
contract validation. Omitting `contract_key` retains the existing Mock upload
layout (`submission.json`, `model/config.json`, `model/model.safetensors`). The
contract branch is selected explicitly for Lab02 Task uploads; Mock retains its
original layout.

Contract errors are `LAB02_MANIFEST_INVALID` or `LAB02_CONFIG_INVALID`. Shared
ZIP/weight security violations retain existing security codes. Fixed public
messages do not echo submitted data, paths or traceback details.

The two tiny JSON fixtures in `backend/tests/fixtures/lab02/` are the unchanged
metadata read from the supplied submission ZIP. Its approximately 438 MB weights
were not read/extracted during that earlier contract inspection. Runtime loading
and inference verification of the supplied weights is described below.

## Runtime and verification

The real Lab02 implementation uses this interface and contract. It creates a
server-owned BertForSequenceClassification from the pinned server config, loads
safetensors strictly, uses local JSONL data, and returns whole-dataset Macro F1 and
Accuracy. Offline CPU tests use a real tiny BERT; full supplied Lab2 weights were
also verified on a distinct four-review IMDb smoke dataset through Worker storage
and artifact deletion. No full-test-set performance claim is made.

The subprocess enforces lifecycle/timeout and prevents inference overlap. It is
not a replacement for the stronger per-Job production container boundary in
`submission-security.md`. Docker/real Redis/PostgreSQL/GPU integration remains
unverified on the current Mac. See `lab02-evaluator.md` for details.
