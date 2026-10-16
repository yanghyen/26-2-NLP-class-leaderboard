# Frontend verification

For the latest user-run Lab02 browser checklist and the separately verified
real HTTP/API results, see [2026-10-16 operations verification](lab02-operations-verification.md).
Browser verification is intentionally left to the user per their request.

Run `npm test`, `npm run typecheck`, `npm run lint`, `npm run build` in `frontend/`. Public routes are `/tasks`, `/tasks/{slug}`, `/submit`, `/submissions`, `/submissions/{uuid}`, `/leaderboard`, `/profile` (local records), and `/dashboard` (tasks). `/` redirects to `/tasks`. `/login` is admin-only; `/register` and `/admin/join-code` no longer exist. Admin routes are protected by the shell and by backend Bearer authorization.

## Manual checklist (user-run)

1. Admin login; upload synthetic UTF-8 Roster CSV; configure task allowed base models and architectures.
2. Log out. Open a public task, then Submit. No student signup/login should be needed.
3. Enter a listed student number, nickname, active emoji, model name, Baseline, Notebook and model ZIP. Confirm the student-number privacy notice and immutable first-submission profile notice.
4. Submit once. Button disables during upload, percentage progresses, then a result page displays type/status/model/time and eventually a visible score.
5. Submit Development with the same number from another browser. It must reuse the Participant and keep original nickname/emoji. No browser token or student session is needed.
6. Verify one leaderboard row, fixed Baseline, highest successful Development, and subtraction-based improvement. No Baseline/Development produces a dash for unknown improvement. Failed/quarantined/invalidated results must not become best.
7. My Submissions/Profile must show only UUIDs saved in this browser, nickname/emoji and safe results. Student number is only a submission-form input/autocomplete value; it must not appear in history, profile or leaderboard. Storage deletion/another-device limitations are stated.
8. The localStorage keys `nlp-autocomplete` and `nlp-submission-ids` are convenience data, never credentials. Blocking localStorage does not block the upload; browser history may then be unavailable.
9. Admin Participants page: inspect student number, link IDs, task scores/counts/time; edit profile; reset a successful Baseline after confirmation. Whole-submission page: filter by student number, inspect unmapped legacy records, invalidate/download/delete under admin protection. Jobs/Quarantine retain existing restrictions.
10. Download admin CSV and compare student numbers with LMS roster (import as Text to preserve zeros). Anonymous CSV/artifact/admin requests must be rejected.
11. All public app pages display: practice website; e-Class LMS receives final Notebook/model ZIP/development report. No student final-selection action or instruction to submit/copy a Submission ID exists.
12. Student/admin route transitions and logout remain usable; only admins store an admin Bearer token in sessionStorage. No HttpOnly-cookie migration occurred.

## Verification boundary

Automated component tests verify anonymous shell access, privacy fields/notices, autocomplete, disabled duplicate uploads, local UUID history, missing student auth links and LMS notice. API tests exercise multipart validation → memory FIFO → real Worker → deterministic Mock evaluator → safe results/leaderboard/admin CSV, plus failure/quarantine handling.

On 2026-10-12 a browser check was started, then stopped at the user's request. Full manual browser E2E was not completed; do not infer it from Vitest. Real Redis/Docker E2E is unverified because neither executable is installed. Run the checklist after Docker setup. Do not use real student data in test fixtures or browser logs.
