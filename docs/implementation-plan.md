# Implementation Plan

## Phase 1 - Done

- Reviewed the full requirement document.
- Confirmed the workspace was empty and not a Git repository.
- Chose a pragmatic monorepo structure with `frontend`, `backend`, `worker`, PostgreSQL, and Redis.
- Defined normalized entities for users, roster, avatars, tasks, configs, submissions, jobs, scores, final selections, snapshots, announcements, and audit logs.

## Phase 2 - Done

- Added Docker Compose for `frontend`, `api`, `worker`, `postgres`, and `redis`.
- Added FastAPI app with startup DB creation for local development.
- Added SQLAlchemy models and an Alembic initial migration.
- Added password hashing and signed bearer tokens without storing plaintext passwords.
- Added default server-managed avatar IDs.
- Added roster-gated student registration, login, `/auth/me`, and admin-only controls.
- Added admin CSV roster upload and join-code creation.
- Added admin task creation with task config.
- Added student submission record creation with official attempt limits and evaluation job records.
- Added backend pytest coverage for registration, reserved names, authorization, submission job creation, and submission limits.

## Secure Submission Pipeline - Done

- Added streamed Notebook + model ZIP upload through an isolated incoming zone.
- Added allowlist validation, ZIP traversal/bomb/link controls, bounded Notebook/JSON parsing, and safetensors header/parser checks.
- Added local storage and malware scanner interfaces, atomic artifact promotion, failure cleanup, and quarantine metadata.
- Added Redis FIFO dispatch and a concurrency-one worker with state transitions, retry policy, cleanup, deterministic mock scores, and public task leaderboard.
- Added student/admin status APIs, owner checks, private-score filtering, authenticated admin downloads, retry/invalidation/deletion controls, and security tests.

## Phase 3 - Next

- Build real Student UI: login, signup with emoji/nickname preview, dashboard, task list/detail, submit page, my submissions, submission detail, leaderboard, profile/password.
- Build Admin UI: dashboard, roster upload/status, join code, task management, submissions/queue view, audit log.
- Add leaderboard endpoint and UI with public/private visibility rules, baseline rows, tie sorting, and “my rank nearby.”

## Real Evaluation Security - Later

- Add a disposable, network-disabled evaluator container backend before loading real student models.
- Connect ClamAV or an equivalent fail-closed scanner.
- Add real Sentiment hidden-test inference after allowed models/datasets are configured.
- Add quarantine UI and optional sanitized text-only Notebook preview.

## Phase 5

- Expand tests for file validation, worker failure isolation, queue ordering, public/private score exposure, leaderboard sorting, and audit log coverage.
- Add production deployment checklist, backup/recovery scripts, and stronger secret handling.
