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

For Docker-free frontend development, start the API and UI in separate terminals:

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload
cd frontend && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000 \
  NEXT_PUBLIC_SHOW_MOCK_EVALUATION=true npm run dev
```

The mock badge is controlled at frontend build time. Set
`NEXT_PUBLIC_SHOW_MOCK_EVALUATION=false` for a production build. This does not
select an evaluator. Lab02 requires separate resource/data preparation;
production GPU deployment remains unverified.

## Backend Development

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lab02.txt
pytest
uvicorn app.main:app --reload
```

Create a development admin:

```bash
cd backend
APP_ENV=development DEV_ADMIN_PASSWORD='choose-a-strong-password' \
  .venv/bin/python -m app.scripts.create_admin --nickname RootTA
```

The login ID is the nickname (`RootTA`). Re-running the command is safe and does not reset the existing password. The CLI refuses to run when `APP_ENV` is `test` or `production`.

## Database Migration

```bash
cd backend
alembic upgrade head
```

Always run Alembic before starting the updated API against an existing DB. Startup table creation does not upgrade existing columns. Migration `0004_roster_participants` must first be verified on a backup; it is forward-only. See `docs/handoff.md` for the legacy mapping and recovery policy.

## Roster CSV

```csv
student_number,real_name,section
20260001,Kim NLP,A
```

Students submit without signup, login, passwords or tokens. Their student number must be in the roster and links their practice records through a Participant; it is not authentication and is never displayed on the public leaderboard. Nickname/emoji are fixed at first submission and editable only by admins. Submission count is unlimited.

## Adding A Task

Admins create tasks through `POST /tasks` with a configurable evaluator key, dataset config, allowed model list, metrics, split config, and scoring strategy. Do not hardcode hidden dataset paths or allowed base models in evaluator code.

## Adding An Evaluator

Implement `Evaluator.evaluate(EvaluationRequest) -> EvaluationResult` in
`backend/app/evaluators/base.py`. Requests are internal objects containing validated
artifact metadata and paths; results contain score, secondary metrics and version
snapshots. `mock_v1` and prepared `lab02_sentiment_v1` are executable; historical `mock`
keys remain a compatibility alias. Task creation/update validates the explicit evaluator key.

Lab02 now creates the fixed server BERT classifier, strictly loads safetensors,
and runs offline local JSONL sentiment evaluation in a bounded Job subprocess.
IMDb public test is the temporary evaluation data, not a hidden set. Existing
Tasks and Mock scores are not automatically changed. See `docs/lab02-evaluator.md`
for dependency installation, pinned resource/data preparation, CPU/CUDA settings,
score identities and the stronger production container boundary still required.

## Hidden Tests

Hidden test files and answer keys must not be committed. Mount them into worker containers as read-only volumes and reference them through `task_configs.dataset_config`.

## Evaluation Worker

Redis dispatch and the deterministic mock evaluator are connected end to end. The worker handles one Job at a time, retries infrastructure failures once, and cleans scratch directories after every Job. Run it with `python -m app.worker`. This process is suitable for the mock evaluator only; real model loading requires the isolated container boundary documented in `docs/submission-security.md`.

## Submission Files

See `docs/student-submission-spec.md`. The notebook is stored but never executed automatically. The model ZIP should use `model.safetensors` and include `submission.json`.

## Security Notes

Included: administrator password hashing/Bearer authorization, roster-gated public submissions, reserved nickname validation, admin-only artifacts/CSV and audit hooks. Join Code and student authentication APIs/UI are removed.

Implemented: upload trust zones, bounded streaming, ZIP traversal/bomb/link checks, data-only allowlists, safetensors parsing, Notebook non-execution, admin authorization and public response allowlists, safe errors, and mock worker isolation by process responsibility.

Before production: connect a real fail-closed malware scanner, add a per-Job network-disabled evaluation container for real models, rotate secrets, configure HTTPS/reverse proxy, and establish backups, monitoring, quotas, and retention. See `docs/submission-security.md` and `docs/submission-api.md`.

## Frontend Verification

```bash
cd frontend
npm run lint
npm run typecheck
npm test
npm run build
```

See `docs/frontend-manual-test.md` for the browser workflow.

## Backup And Recovery

Back up PostgreSQL and submission storage together. Keep database snapshots and artifact backups from the same time window so scores and files remain consistent.

## Practice and official submission policy

The first successfully evaluated Baseline is fixed. The highest successful Development is selected automatically; equal scores prefer earlier successful completion. Failed/quarantined/invalidated/post-deadline results are excluded. Improvement is best Development minus Baseline, or null when either is missing. Baseline-only participants use Baseline as leaderboard fallback. Admins can invalidate/reset a wrong Baseline and export student-number summaries to compare with LMS lists.

This website and leaderboard support practice/model development. Official final submission is Notebook, model ZIP and a short development report in e-Class LMS. Students do not submit a Submission ID. My Submissions shows only UUIDs saved by the current browser; clearing storage or switching devices loses automatic history. No public student-number history search is provided.

## Successful evaluation file retention

This is a practice leaderboard. Immediately after a successful Baseline or
Development evaluation commits its score, secondary metrics, COMPLETED Submission
and Job, and pinned Baseline reference, the worker deletes the submission's
Notebook, model ZIP, and extracted model directory. No file is deleted before
that transaction commits. Scores and evaluation metadata remain in the DB;
Submission/Job, Participant links, kind/model name, SHA-256 digests, safe validation
metadata, evaluation/dataset versions (when configured), timestamps, and Baseline/
best Development aggregation are preserved.

Successful submissions cannot be downloaded or evaluated again, including by
administrators. Students must keep their official files themselves and submit
Notebook, model ZIP, and the development report separately to **e-Class LMS**.
Drafts and in-progress submissions are excluded from this automatic cleanup.
The existing failed-submission cleanup policy is unchanged. Quarantine files have
a separate administrator retention policy and are never touched by this cleanup.
