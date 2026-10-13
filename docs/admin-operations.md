# Admin Operations

## Roster CSV

Upload a UTF-8 CSV with these columns:

```csv
student_number,real_name,section
20260001,Kim NLP,A
```

`student_number` and `real_name` are required. `section` is optional.

## Development Admin

The bootstrap command is manual and development-only. It never creates a default account during API startup and requires the password through `--password` or `DEV_ADMIN_PASSWORD`.

```bash
cd backend
APP_ENV=development DEV_ADMIN_PASSWORD='choose-a-strong-password' \
  .venv/bin/python -m app.scripts.create_admin --nickname RootTA
```

The administrator login ID is the exact nickname, so use `RootTA` in `student_number_or_nickname`. Running the same command again prints `Already exists` and exits successfully without creating a duplicate or changing the existing password. A nickname already owned by a student is rejected. `APP_ENV=test` and `APP_ENV=production` are rejected before database bootstrap.

Run the CLI and Uvicorn from the same `backend/` directory or give both the same explicit `DATABASE_URL`. The default SQLite URL is relative to the process working directory; different working directories can otherwise create different `dev.db` files.

For a CLI argument instead of an environment variable:

```bash
cd backend
APP_ENV=development .venv/bin/python -m app.scripts.create_admin \
  --nickname RootTA --password 'choose-a-strong-password'
```

The environment-variable form is preferred because command-line arguments can be visible in shell history and process listings.

Re-running the create command does not change an existing password. If a development administrator has forgotten the original password, reset it explicitly:

```bash
cd backend
APP_ENV=development DEV_ADMIN_PASSWORD='new-strong-password' \
  .venv/bin/python -m app.scripts.create_admin \
  --nickname RootTA --reset-password
```

The reset option is governed by the same development-only guard and never runs automatically.

## Roster-linked practice submissions

Students submit directly from public tasks without registration, login or passwords. Roster numbers validate enrollment and connect records, never prove identity. Preserve leading zeros and trim surrounding whitespace only. Roster upload remains UTF-8 CSV. Join Code has no UI/API usage.

Use `/admin/participants` for task-specific student-number summaries, link inspection, nickname/emoji edits, explicit successful Baseline reset, and CSV export. Use `/admin/submissions` for the entire record history, including unmatched legacy rows, and student-number filtering. Existing Job retry, quarantine metadata, submission invalidation, and artifact deletion remain; deletion/invalidation/reset actions have confirmation dialogs. No Participant hard-delete or roster relinking endpoint is provided.

`GET /admin/tasks/{slug}/results.csv` is Bearer-protected UTF-8, ordered by string student number ascending. Import that column as Text to retain zeros. It contains separate Baseline and best Development scores, null improvement when either is absent, total/success/failed/quarantined counts and last submission time. Compare it with LMS lists using student number. Students never submit this CSV or a Submission ID.

The first successful Baseline stays pinned. Further Baselines are allowed. Invalidated pinned Baseline is unavailable until explicitly reset; choose a successful Baseline belonging to the same participant/task. Highest successful Development wins; failed/quarantined/invalidated/post-deadline results are excluded. Equal scores prefer earliest successful completion. Baseline-only rows fall back to Baseline with null Development/improvement. Total counts retain drafts and invalidated records.

The website is for practice; official final Notebook, model ZIP and development report go to e-Class LMS. Admin authentication stays Bearer; development CLI remains available.

## Task Policy Maintenance

Use `/admin/tasks` to select an existing task and edit its allowed base models,
architectures, optional paths, and optional dtypes. The UI reloads the admin
task detail after a successful save. A red **정책 미설정** warning means model
uploads will be rejected until both an allowed model and architecture exist.

The corresponding APIs are `GET /tasks/admin/{slug}` and
`PATCH /tasks/{slug}`. Slugs are immutable. Policy lists must be non-empty,
unique strings; the backend remains authoritative even when the browser has
already validated the form.

Apply migrations before starting the updated API:

```bash
cd backend
.venv/bin/alembic -c alembic.ini upgrade head
```

Migration `0003_backfill_test_task_policy` only repairs a task whose slug is
`test`, whose allowed models are exactly `["course/bert-base"]`, and whose
artifact policy is empty. It sets the architecture already used by the secure
submission tests: `BertForSequenceClassification`. It does not modify other
tasks, non-empty policies, or broaden any model registry.

## Audit Log Policy

Audit rows cover roster upload, task creation/update, manual Job retry, submission invalidation, artifact deletion, Participant profile edits and Baseline resets. Public submission audit events have no authenticated actor.

## Hidden Test Data

Hidden datasets, answer keys, passwords, and secret keys must stay outside Git. Use environment variables and mounted read-only volumes in production.

## Artifact Operations

Use the authenticated `/admin/submissions`, `/admin/jobs`, and `/admin/quarantine` APIs for status. Quarantine returns metadata only; never execute or preview its contents. Retained, non-quarantined notebook/model downloads are available through the admin download endpoint and remain untrusted after download. Successful evaluations immediately enter automatic cleanup and are no longer downloadable or eligible for reevaluation.

The development malware adapter is disabled by design. Do not deploy with `MALWARE_SCANNER=disabled`; connect a fail-closed production scanner first. See `docs/submission-security.md` for the real-evaluator isolation checklist.

## Successful artifact cleanup and recovery

Apply migration `0005_successful_artifact_cleanup` before starting API/worker.
It adds `artifact_cleanup_status` (`retained`, `pending`, `deleted`),
`artifact_deleted_at`, `evaluator_version`, and `dataset_version` to Submission.
The deterministic Mock evaluator remains in use (`mock-v1`); the worker snapshots
`dataset_config.dataset_version` or `dataset_config.version` if configured.
Historical versions are left unknown rather than inferred from current config.

The score, secondary metrics, success states, completion time and Baseline pin
commit together with `pending`. Only afterwards does a fresh-session cleanup
verify the committed success and remove Notebook, ZIP and extracted model data
through ArtifactStorage. A second transaction records `deleted`, its UTC time,
and `submission.artifact_auto_deleted`. SubmissionFile rows and SHA-256 hashes
remain for audit; no Submission, Job, Score or Participant is removed. The fixed
Baseline, best Development, leaderboard and administrator result exports continue
to use DB records. Official files must be retained by students and submitted to
e-Class LMS; the practice site is not a file archive.

On deletion failure, successful evaluation and scores remain intact. Cleanup stays
`pending`, with `submission.artifact_cleanup_pending` audit code
`ARTIFACT_CLEANUP_FAILED`; exception details are restricted to server logs. No
cleanup exception is stored in public fields. Admin Submissions displays pending
cleanup and offers **파일 정리 재시도**; manual deletion of an already auto-deleted
submission is a no-op and does not invalidate its score. Ordinary manual deletion
of retained Draft/failed/invalidated artifacts retains its existing invalidation behavior. Historical successful submissions use the same score-preserving cleanup even before the first sweep.

The worker performs a bounded sweep at startup and every 30 seconds between Jobs
(up to 100 submissions per sweep). It also recovers older successful evaluations
whose cleanup status is still `retained`. Retrying missing/partially deleted files
is safe. If the process exits after evaluation commit or after file deletion but
before cleanup commit, the next sweep completes the remaining cleanup. For an
explicit recovery batch using the same DATABASE_URL/STORAGE_ROOT as the worker:

```bash
cd backend
.venv/bin/python -m app.scripts.cleanup_artifacts --limit 100
```

The sweep only selects COMPLETED Baseline/Development records with a COMPLETED Job
and score; it excludes Draft, active, failed, invalidated and Quarantine records.
Quarantine has a separate administrator preservation policy and is never removed
by this sweep. General failed-submission cleanup behavior is unchanged.
