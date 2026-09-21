# Implementation Plan

## Phase 1 - Done

- Reviewed the full requirement document.
- Confirmed the workspace was empty and not a Git repository.
- Chose a pragmatic monorepo structure with `frontend`, `backend`, `worker`, PostgreSQL, and Redis.
- Defined normalized entities for users, roster, avatars, tasks, configs, submissions, jobs, scores, final selections, snapshots, announcements, and audit logs.

## Phase 2 - In Progress, Executable Foundation Added

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

## Phase 3 - Next

- Build real Student UI: login, signup with emoji/nickname preview, dashboard, task list/detail, submit page, my submissions, submission detail, leaderboard, profile/password.
- Build Admin UI: dashboard, roster upload/status, join code, task management, submissions/queue view, audit log.
- Add leaderboard endpoint and UI with public/private visibility rules, baseline rows, tie sorting, and “my rank nearby.”

## Phase 4

- Implement file uploads for `.ipynb` and `.zip`.
- Add storage abstraction with local storage first.
- Add ZIP security validation: extension/MIME assist, size limits, zip slip, symlink, zip bomb guard, required files, `submission.json` schema, and safetensors-only policy.
- Add Redis queue dispatch and worker processing.
- Add mock evaluator job success/failure tests.
- Add Sentiment evaluator interface implementation without committing hidden data.

## Phase 5

- Expand tests for file validation, worker failure isolation, queue ordering, public/private score exposure, leaderboard sorting, and audit log coverage.
- Add production deployment checklist, backup/recovery scripts, and stronger secret handling.

