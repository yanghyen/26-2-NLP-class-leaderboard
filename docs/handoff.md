# Handoff

## Current State

Phase 1-2 foundations and the secure submission/mock evaluation pipeline are implemented. The active branch is `feature/secure-submission-pipeline`. Student/admin frontend workflows are still the minimal Next.js status shell.

The submission path is now:

```text
multipart Notebook + model ZIP
-> streamed incoming UUID directory
-> Notebook / ZIP / JSON / safetensors / malware-adapter validation
-> atomic artifact promotion
-> EvaluationJob row + Redis FIFO Job UUID
-> concurrency-one worker
-> deterministic mock score
-> COMPLETED submission and task leaderboard
```

Notebooks are preserved but never executed or rendered. Student Python/custom modules, pickle/PyTorch checkpoints, native code, nested archives, unsafe ZIP entries, unregistered models/architectures, and remote-code configuration are rejected. `EvaluationContext.trust_remote_code` is immutable `False`.

## Important Files

- `backend/app/security/validation.py`: bounded Notebook, ZIP, JSON, model policy, and safetensors checks.
- `backend/app/storage/`: local trust-zone storage interface/adapter.
- `backend/app/services/submissions.py`: upload lifecycle, cleanup, promotion, Job creation, and enqueue.
- `backend/app/services/state.py`: allowed submission/Job transitions.
- `backend/app/queue.py`: Redis and in-memory FIFO adapters.
- `backend/app/worker.py`: sequential processing, score persistence, retry policy, and cleanup.
- `backend/app/api/routes/submissions.py`, `admin.py`, `tasks.py`: UI-facing APIs and authorization.
- `backend/alembic/versions/0002_secure_submission_pipeline.py`: artifact policy and validation metadata migration.
- `docs/submission-security.md`: threat model, residual risk, and Docker checklist.
- `docs/submission-api.md`: Phase 3 UI contract.

## Verification

Run before continuing:

```bash
backend/.venv/bin/pytest backend/tests -q
backend/.venv/bin/python -m compileall -q backend/app
cd frontend && npm run typecheck
```

The implementation machine has no Docker CLI. Compose build/runtime, Postgres enum migration behavior, Redis process integration, named-volume ownership, and container resource/isolation controls remain unverified here. The test suite uses SQLite, an in-memory queue adapter, and synthetic non-malware fixtures.

## Deliberately Deferred

- Real ClamAV adapter and quarantine management UI.
- Custom AppArmor/seccomp profiles.
- Notebook preview or browser rendering.
- Real GPU/model loading and hidden-test evaluation.
- Per-Job disposable evaluator container with no network and no secrets.
- Daily submission rate limits and configurable failed-validation attempt policy.

Do not enable a real Transformers evaluator inside the current worker process. It has database, Redis, and shared artifact access and is not the final hostile-model sandbox.

## Next Work

1. Build Phase 3 student UI against `docs/submission-api.md`: multipart submit form, progress/error codes, submission status polling, score detail, and public leaderboard.
2. Build admin queue/submission/quarantine metadata views and authenticated download actions.
3. On a Docker host, execute the checklist in `docs/submission-security.md`, including Postgres/Redis integration and worker restart/idempotency tests.
4. Add a real malware scanner adapter, then design the disposable real-evaluator container backend before any GPU inference.
