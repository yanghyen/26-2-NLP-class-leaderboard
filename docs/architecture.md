# Architecture And Data Model

## Scope

This repository starts with a maintainable MVP for a 60-student NLP course leaderboard. Phase 1 fixes the architecture and data model. Phase 2 implements the executable backend foundation: Docker Compose, database models, authentication, role checks, roster-gated signup, task creation, and submission records that can enqueue evaluation jobs.

## Services

- `frontend`: Next.js + TypeScript + Tailwind entry point. Full student/admin workflows begin in Phase 3.
- `api`: FastAPI application for accounts, roster, tasks, submissions, scores, and admin operations.
- `worker`: separate backend image entry point. It is a placeholder in Phase 2 and will own validation/evaluation in Phase 4.
- `postgres`: primary relational database.
- `redis`: queue backend for the future worker.

The API never evaluates models inside the HTTP request. The Phase 2 submission endpoint creates a submission and an `evaluation_jobs` row; Phase 4 will add Redis queue dispatch and worker execution.

## Data Model

- `users`: login credentials, role, private identity, and public profile pointers.
- `course_roster`: admin-uploaded student number/name allowlist.
- `avatars`: server-managed avatar IDs mapped to emoji.
- `join_codes`: active/inactive class signup codes stored as hashes.
- `tasks` and `task_configs`: task metadata, stages, submission limits, evaluator key, datasets, allowed models, metrics, split config, and scoring strategy.
- `submissions`: draft, baseline practice, and official evaluation records.
- `submission_files`: notebook and model ZIP metadata, to be wired in Phase 4.
- `evaluation_jobs`: queue lifecycle records with split, attempts, status, and safe errors.
- `scores`: public/private/smoke metrics.
- `final_selections`: student-selected final submissions.
- `leaderboard_snapshots`, `announcements`, `audit_logs`: operational support.

Private identifiers are not needed for leaderboard views. Leaderboards should join only public profile fields: avatar ID/emoji and nickname.

## Task Extension Strategy

Each task uses an evaluator key and config rather than hardcoded datasets or model names. Evaluators implement:

- `validate_submission()`
- `load_model()`
- `run_inference()`
- `compute_metrics()`
- `format_public_result()`
- `cleanup()`

`mock` exists now to keep the interface executable. Sentiment Analysis should be the first real evaluator, using configured dataset paths and metrics.

## Security Boundaries

Phase 2 includes password hashing, roster-gated signup, join code hashing, role checks, reserved nickname blocking, and audit log hooks for admin operations. Phase 4 must add file validation, ZIP safety checks, process/container isolation, network-blocked evaluation containers, timeout cleanup, and hidden-test-safe errors.

