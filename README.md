# NLP Course Leaderboard

Course project submission and leaderboard platform for a second-year NLP class.

## Structure

- `backend/`: FastAPI API, SQLAlchemy models, Alembic migration, tests, evaluator interfaces.
- `frontend/`: Next.js + TypeScript + Tailwind app shell.
- `docs/`: architecture, implementation plan, student submission spec, admin operations, handoff notes.
- `docker-compose.yml`: local Postgres, Redis, API, worker, and frontend.

## Local Setup

```bash
cp .env.example .env
docker compose up --build
```

API: `http://localhost:8000`

Frontend: `http://localhost:3000`

## Backend Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
uvicorn app.main:app --reload
```

Create a development admin:

```bash
cd backend
python -m app.scripts.create_admin --nickname RootTA --password "change-this"
```

## Database Migration

```bash
cd backend
alembic upgrade head
```

For local development the API also creates tables on startup so the MVP is easy to run.

## Roster CSV

```csv
student_number,real_name,section
20260001,Kim NLP,A
```

Students can register only when their student number and real name match the roster and the class join code is active.

## Adding A Task

Admins create tasks through `POST /tasks` with a configurable evaluator key, dataset config, allowed model list, metrics, split config, and scoring strategy. Do not hardcode hidden dataset paths or allowed base models in evaluator code.

## Adding An Evaluator

Implement `backend/app/evaluators/base.py`:

- `validate_submission()`
- `load_model()`
- `run_inference()`
- `compute_metrics()`
- `format_public_result()`
- `cleanup()`

Sentiment Analysis should be the first real evaluator. Machine Translation and Code Generation should reuse the same queue lifecycle while adding independent evaluator implementations.

## Hidden Tests

Hidden test files and answer keys must not be committed. Mount them into worker containers as read-only volumes and reference them through `task_configs.dataset_config`.

## GPU Worker

Phase 2 includes only the worker entry point. Phase 4 should add Redis queue dispatch and isolated evaluation with GPU concurrency set to one by default.

## Submission Files

See `docs/student-submission-spec.md`. The notebook is stored but never executed automatically. The model ZIP should use `model.safetensors` and include `submission.json`.

## Security Notes

Already included: password hashing, hashed join codes, role checks, roster-gated signup, reserved nickname blocking, and audit hooks.

Before production: add upload validation, ZIP bomb/path traversal checks, sandboxed evaluation containers, network-disabled workers, secret rotation, HTTPS/reverse proxy, backups, monitoring, and retention policies.

## Backup And Recovery

Back up PostgreSQL and submission storage together. Keep database snapshots and artifact backups from the same time window so scores and files remain consistent.

