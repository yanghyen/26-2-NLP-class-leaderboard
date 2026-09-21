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

- `users`: login credentials, role, private identity, and public profile pointers.
- `course_roster`: admin-uploaded student number/name allowlist.
- `avatars`: server-managed avatar IDs mapped to emoji.
- `join_codes`: active/inactive class signup codes stored as hashes.
- `tasks` and `task_configs`: task metadata, stages, submission limits, evaluator key, datasets, allowed models, metrics, split config, and scoring strategy.
- `submissions`: draft, baseline practice, and official evaluation records.
- `submission_files`: notebook and model ZIP hashes, sizes, display names, MIME hints, and server-owned storage keys.
- `evaluation_jobs`: queue lifecycle records with split, attempts, status, and safe errors.
- `scores`: public/private/smoke metrics.
- `final_selections`: student-selected final submissions.
- `leaderboard_snapshots`, `announcements`, `audit_logs`: operational support.

Private identifiers are not needed for leaderboard views. Leaderboards should join only public profile fields: avatar ID/emoji and nickname.

## Task Extension Strategy

Each task uses an evaluator key and config rather than hardcoded datasets or model names. Evaluators implement:

- `validate_submission()`
- `prepare()`
- `run_inference()`
- `compute_metrics()`
- `format_result()`
- `cleanup()`

`mock` now completes the queue/score/leaderboard flow using the server-computed artifact digest. Sentiment Analysis should be the first real evaluator, but only after the isolated execution backend in `docs/submission-security.md` is implemented.

## Security Boundaries

Password hashing, roster-gated signup, role checks, upload trust zones, ZIP/Notebook/safetensors validation, safe errors, owner-scoped reads, and worker cleanup are implemented. The mock evaluator does not load student tensors. Real model loading remains blocked on a disposable network-disabled evaluation container; the current worker itself is not that sandbox.

See `docs/submission-security.md` for the threat model and explicit residual risks, and `docs/submission-api.md` for the UI contract.
