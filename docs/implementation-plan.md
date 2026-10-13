# Implementation status

Current policy supersedes the historical student-account design. Student signup/login/password/tokens, Join Code UI/APIs, owner-history APIs and final-selection UI/APIs are removed. Admin Bearer login/CLI remains.

Implemented: roster-linked Participant submissions, safe public UUID status, first-success Baseline pinning, automatic best Development/improvement, browser-local UUID history/autocomplete, public practice/LMS guidance, admin profile edits/Baseline resets and student-number CSV. Existing secure upload pipeline, FIFO adapter, concurrency-one Mock Worker, Job and quarantine management remain.

Legacy rows and deprecated Join Code/final-selection/attempt-limit columns are retained; migration and manual reconciliation plan is in `handoff.md`. SQLite and PostgreSQL migration validation uses disposable databases.

Remaining: real Redis/Docker integration verification, isolated disposable evaluator containers, real GPU/hidden-test evaluation, real fail-closed ClamAV integration, retention/monitoring/backups, and production deployment checks. No student authentication replacement is planned.
