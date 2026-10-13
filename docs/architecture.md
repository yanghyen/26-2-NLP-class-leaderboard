# Architecture And Data Model

## Scope

This repository contains a maintainable MVP foundation for a 60-student NLP course leaderboard. The current backend includes secure file ingestion, Redis dispatch, and deterministic mock evaluation in addition to authentication and task management.

## Services

- `frontend`: Next.js + TypeScript + Tailwind entry point. Full student/admin workflows begin in Phase 3.
- `api`: FastAPI application for accounts, roster, tasks, submissions, scores, and admin operations.
- `worker`: separate, concurrency-one backend entry point. It consumes validated Job IDs and runs the configured server-owned evaluator.
- `postgres`: primary relational database.
- `redis`: FIFO evaluation queue containing Job UUIDs only.

The API performs bounded structural validation but never evaluates or imports student code in the HTTP request. It queues only after validation and atomic promotion into the artifact trust zone. The worker owns evaluation lifecycle transitions and score persistence.

## Data Model

- `users`: admin authentication plus disabled legacy student rows retained for audit/foreign keys.
- `participants`: unique roster link, nickname/emoji and timestamps; no credentials.
- `baseline_references`: persistent first-success reference per participant/task.
- `course_roster`: admin-uploaded student number/name allowlist.
- `avatars`: server-managed avatar IDs mapped to emoji.
- `join_codes`: deprecated historical data; no runtime endpoints.
- `tasks` and `task_configs`: task metadata, stages, deprecated legacy limits, evaluator key, datasets, allowed models, metrics, split config, and scoring strategy.
- `submissions`: draft, baseline practice, and Development evaluation records linked to Participants; legacy unmatched user links retained.
- `submission_files`: notebook and model ZIP hashes, sizes, display names, MIME hints, and server-owned storage keys.
- `evaluation_jobs`: queue lifecycle records with split, attempts, status, and safe errors.
- `scores`: public/private/smoke metrics.
- `final_selections`: deprecated historical data; all new aggregation ignores it.
- `leaderboard_snapshots`, `announcements`, `audit_logs`: operational support.

Private identifiers are not needed for leaderboard views. Leaderboards should join only public profile fields: avatar ID/emoji and nickname.

## Task Extension Strategy

Each task explicitly selects a server-owned evaluator with `Task.evaluator_key`.
The Worker calls `Evaluator.evaluate(EvaluationRequest) -> EvaluationResult` and
then `cleanup(request)`. Internal requests contain validated artifact/manifest
metadata, paths and context; results contain primary score/metric, secondary
metrics and evaluator/dataset versions. Public schemas contain no internal paths.

`mock_v1` retains its digest score and `mock` compatibility alias.
`lab02_sentiment_v1` runs offline fixed BERT/safetensors inference on prepared local
JSONL in a per-Job subprocess with a hard deadline. Task selection is explicit;
existing Tasks are unchanged. Aggregate scores are filtered by the current
evaluator/dataset identity. IMDb public test is temporary public evaluation data.
See `docs/evaluator-contract.md` and `docs/lab02-evaluator.md`. Hidden datasets and
stronger per-Job production containers remain deferred; CUDA support is implemented
but GPU integration is unverified on this Mac.

## Security Boundaries

Admin password hashing/Bearer checks, roster-linked public submissions, upload trust zones, ZIP/Notebook/safetensors validation, safe errors, public allowlisted UUID reads, and worker cleanup are implemented. The mock evaluator does not load student tensors. Real model loading remains blocked on a disposable network-disabled evaluation container; the current worker itself is not that sandbox.

See `docs/submission-security.md` for the threat model and explicit residual risks, and `docs/submission-api.md` for the UI contract.

## Post-commit retention

The Mock Worker commits Score (including secondary metrics), COMPLETED Submission/
Job, completion time, evaluator/dataset version snapshots and BaselineReference
with cleanup `pending`. Only then does `services/artifact_cleanup.py`, in a fresh
DB session, delete the whole trusted artifact directory through ArtifactStorage
and commit cleanup `deleted`/UTC deletion time and audit. Failed deletion leaves
a retryable pending record and never reverses evaluation success. The startup/
periodic Worker sweep and `app.scripts.cleanup_artifacts` recover interrupted
cleanup and older successes. Draft, failed, active and Quarantine files are excluded.
DB-only leaderboard and best Development/Baseline calculations keep all their
records. Successful files cannot be downloaded/reevaluated; official file storage
is the student's responsibility through e-Class LMS.
