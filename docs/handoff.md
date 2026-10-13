# Handoff — roster-linked practice submissions (2026-10-12)

## Operating policy

Students have no signup/login/password/access token/session. Student numbers are identifiers for roster validation and record grouping, not authentication. There is no student submission-count or pending-job limit. Public leaderboard/profile/history never display roster student numbers/names. Admins retain existing password/Bearer login, `/auth/me`, route/API protection and the development-only idempotent admin CLI; no cookie migration was made.

The website supports practice and development. Official final submission is the final Notebook, final model ZIP and short development report in e-Class LMS. Students do not submit a Submission ID or administrator CSV. Admins compare the CSV and LMS student lists by student number.

## Models and migration

- `Participant`: UUID, unique/non-null `roster_entry_id`, nickname, emoji, created/updated timestamps. No duplicated student number or credentials.
- `Submission.participant_id`: current ownership. Nullable only to preserve unmatched legacy records. New uploads always assign it and leave legacy `user_id` null. Participant/task submission-number constraint replaces the user/task constraint.
- `BaselineReference`: unique participant/task, points to the first successfully evaluated Baseline. Worker pins after success in the score/status transaction.
- `0004_roster_participants` follows the user's pre-existing `0003_backfill_test_task_policy`. Initial revision now loads a frozen historical schema instead of evolving runtime ORM metadata; otherwise a new DB would create Participant tables in 0001 and collide at 0004.

Automatically migrate a legacy student only when `CourseRoster.registered_user_id` explicitly links the student User and stored student numbers match exactly. Preserve Submission UUIDs/user links, Job IDs, Score IDs, artifact metadata/storage paths and final-selection history. Create Participant from legacy nickname and avatar emoji; backfill earliest completed SMOKE Baseline per task. All legacy student accounts are deactivated and their password hash replaced by an unusable marker; legacy tokens are also rejected by role checks before authorization. Admin rows remain unchanged.

Missing/inconsistent roster links are not guessed. Their submissions keep `participant_id = NULL`, remain visible to admins with legacy student number/profile where available, and do not enter new leaderboard/CSV aggregation. For manual reconciliation: identify unmatched rows in admin Submissions; verify enrollment and the authoritative student-to-roster association externally; back up DB/artifacts; prepare a reviewed follow-up Alembic migration that assigns an existing/new Participant, resolves participant/task numbering conflicts, and establishes Baseline only from successful scores. Verify copies before deployment. Do not invent student numbers or delete legacy records.

Migration is intentionally forward-only because new submissions have no User and disabled student credentials cannot be reconstructed. Rollback restores a coordinated pre-migration DB/artifact backup. Do not run it directly against the original `backend/dev.db` without a backup. This task tested a read-only SQLite backup copy; the original was not migrated. Original copy contained 4 Users and no submissions/jobs/scores/files; seeded migration tests cover those relations.

## Submission and aggregation

Public multipart fields: `student_number,nickname,emoji,model_name,submission_type,notebook,artifact`; optional model metadata remains. Reuse existing submission enum: Baseline=`BASELINE_PRACTICE`, Development=`EVALUATION`, draft=`DRAFT`. Required model name is bounded; numbers follow existing trim-only roster normalization, preserving separators/zeros. First profile is fixed; later uploads cannot change it, including uploads from other browsers.

No public history query by student number exists. Public status uses UUID and response allowlists; no names/numbers/file paths/original filenames/private metrics/internal errors. Public task config excludes dataset/split config. Schema-validation errors never echo submission inputs. Artifacts/CSV remain admin-only; fixed download filenames do not contain student numbers.

First successful Baseline stays fixed; validation/evaluation failures do not pin it. Further Baselines are allowed. Invalidated pinned reference becomes unavailable and never automatically moves to another baseline; an admin can explicitly reset it. Highest completed PUBLIC Development wins, excluding failed/quarantined/invalidated/draft/post-deadline results. Ties choose earlier successful completion, then creation time/UUID. Legacy completion timestamps may fall back to creation time. UTC comparisons use task dev deadline, falling back to the existing final deadline. A result completed after that deadline is not a representative score even if uploaded earlier.

`improvement = best_development_score - baseline_score`; if either score is absent, improvement is null. Only-Baseline rows use Baseline as leaderboard fallback with null Development/improvement. One row per scored Participant/task; competition rank for equal scores. Admin total counts retain all records, including draft/invalidated; success count means current COMPLETED status. CSV is UTF-8 sorted lexicographically by string student number; import student numbers as Text to retain zeros. Formula-leading strings are escaped.

## UI and admin operations

Public task/upload/leaderboard routes are directly accessible. The form explains student-number privacy and first-profile immutability, disables the button during upload and retains XHR progress/error handling. `nlp-autocomplete` stores convenience form values and `nlp-submission-ids` stores successful upload UUIDs; neither is authentication. My Submissions/Profile show only current-browser UUID results and nickname/emoji, with storage-deletion/device limitations. Storage failure does not prevent upload. Public shell displays the full practice/e-Class LMS notice.

`/admin/participants`: task summaries with number/profile/link IDs/scores/counts/time, profile editing, confirmed Baseline reset, CSV download. `/admin/submissions`: all records with student-number filter, unmapped legacy record identification, existing invalidation/deletion/download actions. Jobs and Quarantine management remain; quarantine preview/download is prohibited. No Participant hard delete or roster reassignment API is provided.

Removed APIs/UI: student signup, student login handling, student token/route flow, Join Code, authenticated student profile/history/stats, manual final selection. Deprecated DB data: student User fields/role, roster registered_user pointer, Join Code/final-selection tables, submission user pointer and official-attempt/task count-limit columns. New calculations ignore those legacy fields. After verified reconciliation and a retention decision, use a separate reviewed migration to archive/remove them; do not drop historical data during this policy change.

## Validation and limitations

See final test counts below. Checked: all Backend pytest (including existing security/worker tests), Frontend Vitest, TypeScript, ESLint, Next production build, Python compile, Alembic single-head history, new SQLite upgrade/check, original-DB copy upgrade/check, seeded SQLite old-data migration, new PostgreSQL full-chain upgrade, seeded PostgreSQL old-data migration and ORM check, and `git diff --check`.

Browser UI verification was started and then explicitly stopped at the user's request. No full manual browser E2E claim is made. Automated API/component E2E covers admin roster upload, public Baseline/Development upload, memory FIFO → Worker → Mock, stable Participant, one-row leaderboard, improvement, privacy/admin CSV and access restrictions. Docker and real Redis executables are absent, so real Redis/Docker integration is unverified. All temporary API/frontend/PostgreSQL processes were stopped.

Deferred: real GPU evaluator, real hidden-test evaluation, real ClamAV integration and disposable network-disabled per-job evaluator containers. The current evaluator is deterministic Mock and does not load models. Existing ZIP traversal/link/bomb/nested archive/executable/checkpoint/safetensors controls, non-executed Notebook policy, atomic promotion/cleanup, FIFO adapter and concurrency-one Worker remain. Identifier-only submission permits another person knowing a roster number to submit under it; official LMS submission remains authoritative. Public-input nicknames/model names should avoid personal information. Queue/disk abuse, retention, monitoring, HTTPS and coordinated backups remain operating responsibilities.

## Git boundary

The workspace already had many modified/untracked backend/frontend/docs files before this task, including migration 0003 and the student/admin UI. The initial tracked diff was preserved in `/tmp/leaderboard-before.patch`. Related edits reuse that existing work; unrelated changes, `test.csv`, `test.csv.zip`, original DBs, secrets and uploaded artifacts were not changed or staged. A standalone commit would require including pre-existing UI/migration prerequisites or leave the tree unable to run; therefore no partial/incomplete commit is made. The working tree remains reviewable and no user changes are committed.

Final automated results: Backend **67 passed** (one upstream Starlette deprecation warning), Frontend **26 passed** across 8 files. TypeScript, ESLint, Next production build, Python compile, all described Alembic checks and whitespace checks passed. No security tests were removed. Manual browser checks and real Redis/Docker remain unverified as described above.
