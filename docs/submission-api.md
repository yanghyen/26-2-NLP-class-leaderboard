# Submission API Contract

## Student Upload

`POST /submissions/{task_slug}` uses `multipart/form-data`.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `notebook` | file | yes | `.ipynb`; stored, never executed |
| `model_zip` | file | yes | `.zip`; data-only allowlist |
| `kind` | string | yes | `DRAFT`, `BASELINE_PRACTICE`, or `EVALUATION` |
| `model_name` | string | no | display metadata, max 160 |
| `base_model` | string | no | display metadata; ZIP policy remains authoritative |
| `seed` | integer | no | display metadata |
| `metadata_json` | JSON string | no | object, defaults to `{}` |

Success is HTTP 201 with `{ "submission": SubmissionOut, "evaluation_job": EvaluationJobOut | null }`. Drafts return `COMPLETED` with a null Job. Evaluated submissions return `QUEUED` only after validation and Redis enqueue.

Validation failure is HTTP 400. `detail` contains `code`, a safe `message`, and `submission_id`; it never contains a server path or stack trace. Stable codes include `INVALID_ARCHIVE`, `UNSUPPORTED_FILE`, `INVALID_MODEL_FORMAT`, `MODEL_TOO_LARGE`, `MALWARE_DETECTED`, `VALIDATION_FAILED`, `EVALUATION_TIMEOUT`, and `EVALUATION_FAILED`.

## Student Read APIs

- `GET /submissions/me`: caller's submission summaries.
- `GET /submissions/{submission_id}`: owner-only status and visible `SMOKE`/`PUBLIC` scores. A foreign ID returns 404.
- `GET /tasks/{task_slug}/leaderboard`: best completed public score per student, exposing nickname/avatar only.

No student endpoint returns storage paths, validation internals, real names/student numbers of peers, quarantine files, or private scores.

## Admin APIs

- `GET /admin/submissions`: all submissions with validation report, scan status, digest, and internal error.
- `GET /admin/jobs`: queue/job status and safe error category.
- `GET /admin/quarantine`: quarantined metadata only; no raw download.
- `GET /admin/submissions/{id}/download/{notebook|model_zip}`: authenticated download of non-quarantined artifacts.
- `POST /admin/jobs/{id}/retry`: retries eligible infrastructure failures.
- `POST /admin/submissions/{id}/invalidate`: invalidates a non-running submission when the state machine permits it.
- `DELETE /admin/submissions/{id}/artifact`: deletes a non-running artifact and invalidates the record.

Task creation accepts `config.allowed_models` and `config.artifact_policy` (`allowed_paths`, `allowed_architectures`, `allowed_dtypes`). An empty model or architecture registry intentionally rejects uploads.
