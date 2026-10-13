# Practice submission API

Students have no signup, login, password, session, access token, PIN, or personal submission code. Student numbers identify roster entries and link records; they do not authenticate a person. Admin login and `/auth/me` use the existing Bearer token. Swagger public operations have no security requirement; admin operations require Bearer authentication.

## Public endpoints

- `GET /tasks`, `GET /tasks/{slug}`: public task metadata and upload policy. Dataset/split configuration and hidden-test paths are not returned.
- `POST /submissions/{task_slug}`: unauthenticated multipart upload. Required fields: `student_number`, `nickname`, `emoji`, `model_name`, `notebook` (.ipynb), `artifact` (.zip). `submission_type` reuses `BASELINE_PRACTICE`, `EVALUATION` (Development), and `DRAFT`; default is `EVALUATION`. Optional fields: `base_model`, `seed`, `metadata_json` (JSON object).
- `GET /submissions/{uuid}`: safe status, model name, type, submission time, and visible SMOKE/PUBLIC scores after successful completion. No student number, name, user/participant ID, original filename, artifact path, internal error, private score, or arbitrary metrics payload. Upload responses include the internal UUID and safe Job state.
- `GET /tasks/{slug}/leaderboard`: one scored row per Participant, nickname/emoji/model/score and baseline/development/improvement. No student number, name, email, submission count, or submission/participant ID.

Student numbers use the roster's existing normalization rule: surrounding whitespace is trimmed; separators and leading zeros are preserved. An unlisted number returns a generic 400 validation message without echoing the value. First submission creates a Participant after validating nickname and active emoji; subsequent submissions reuse it and ignore supplied profile changes. Nicknames need 2–16 characters and cannot impersonate reserved admin/baseline names. Nicknames need not be unique.

No student submission count or pending-job limit is enforced. Existing byte limits, task opening/deadline checks, ZIP/Notebook/safetensors validation and queue behavior remain. Input-schema errors on submission endpoints return a generic 422 without echoing submitted values. `TASK_POLICY_NOT_CONFIGURED` rejects uploads before a Submission or artifact is stored. Structural failure creates a FAILED record; malware detection creates a QUARANTINED record; neither pins Baseline nor enters the queue.

## Scoring policy

The first successfully evaluated Baseline is persisted in `baseline_references`. Further Baseline uploads are allowed but never replace it automatically. Invalidating that reference makes its score unavailable; an admin must explicitly select another successful same-participant, same-task Baseline to reset it.

Development uses the highest completed PUBLIC score, excluding failed, quarantined, invalidated, draft, and post-deadline results. Ties prefer the earlier successful completion, then submission time, then UUID. Legacy completed records without a completion timestamp fall back to submission time. The deadline is `dev_deadline`, falling back to the existing `final_deadline`; both input and successful evaluation must occur by that deadline. Times are compared in UTC; naive database times are treated as UTC.

`improvement = best_development_score - baseline_score`. Missing Baseline or Development yields `null`. With only Baseline, leaderboard score falls back to Baseline, while Development and improvement remain `null`. Admin counts include retained draft/invalidated records in total; successful count counts current COMPLETED records. Leaderboard ranks use competition ranking for tied scores.

## Admin endpoints

Existing roster/task/submission/Job/quarantine/retry/invalidation/artifact APIs retain Bearer protection. Artifact downloads use fixed `notebook.ipynb`/`model.zip` filenames and never permit quarantine downloads.

- `GET /admin/tasks/{slug}/participants`: student number, profile, roster/participant link IDs, score summary, counts, last submission time.
- `PATCH /admin/participants/{id}`: validated `{nickname, emoji}`; audited.
- `PUT /admin/participants/{id}/tasks/{slug}/baseline`: `{submission_id}` for an evaluated successful Baseline of that participant/task; audited.
- `GET /admin/tasks/{slug}/results.csv`: authenticated UTF-8 CSV sorted by student number ascending as a string. Columns: `student_number,nickname,emoji,baseline_score,best_development_score,improvement,total_submission_count,successful_submission_count,failed_submission_count,quarantined_submission_count,last_submitted_at`. Leading zeros remain in the CSV text; import the student-number column as Text in spreadsheet software. Formula-leading text is escaped with an apostrophe. Counts do not claim official LMS submission.

`/auth/register`, Join Code APIs, `/submissions/me`, `/submissions/stats`, final-selection APIs are removed. No public student-number history lookup exists.

The website is for practice and development. Official final submission requires Notebook, model ZIP, and a short development report in e-Class LMS. Submission ID is not required by LMS.

## Post-evaluation artifact retention

Successful Baseline/Development files are automatically deleted immediately after
scores, secondary metrics, success states, metadata and Baseline pin commit.
The public UUID status and leaderboard APIs continue returning completed status
and visible scores from DB records; original filenames, storage paths and cleanup
errors are never returned. Files are not a permanent site archive; students must
keep official Notebook/ZIP files and submit them separately to e-Class LMS.
Draft and Quarantine files are excluded; Quarantine has its own admin retention
policy. The general failed-submission policy remains unchanged.

`GET /admin/submissions` adds `artifact_cleanup_status`, `artifact_deleted_at`,
`evaluator_version`, and `dataset_version`. Admin download requests for `pending`
or `deleted` artifacts, and historical completed evaluations before cleanup, return **409** with a fixed safe explanation, without
resolving a storage path. Otherwise missing files return **404**. Unauthenticated
or invalid-token requests still return **401**, with no file information.
`POST /admin/jobs/{id}/retry` returns **409** for pending/deleted artifacts, and
for otherwise retryable jobs whose artifact directory is missing. Successful
Jobs remain non-retryable.

`DELETE /admin/submissions/{id}/artifact` retries pending cleanup without changing
success or scores; failure returns a safe **409**. An already deleted artifact
returns **204** without invalidating the successful Submission. Historical successful
evaluations also use score-preserving cleanup. Manual deletion of other retained
artifacts continues to invalidate the record and records deletion status/time.
