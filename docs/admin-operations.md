# Admin Operations

## Roster CSV

Upload a UTF-8 CSV with these columns:

```csv
student_number,real_name,section
20260001,Kim NLP,A
```

`student_number` and `real_name` are required. `section` is optional.

## Development Admin

Create an admin after dependencies are installed:

```bash
cd backend
python -m app.scripts.create_admin --nickname RootTA --password "change-this"
```

## Join Code

Admins create active signup codes through `POST /admin/join-code`. Codes are hashed before storage. By default, creating a new code deactivates existing active codes.

## Audit Log Policy

Audit rows cover join code creation, roster upload, task creation, manual Job retry, submission invalidation, and artifact deletion. Future nickname/score/deadline edits must use the same audit service.

## Hidden Test Data

Hidden datasets, answer keys, passwords, and secret keys must stay outside Git. Use environment variables and mounted read-only volumes in production.

## Artifact Operations

Use the authenticated `/admin/submissions`, `/admin/jobs`, and `/admin/quarantine` APIs for status. Quarantine returns metadata only; never execute or preview its contents. Non-quarantined notebook/model downloads are available through the admin download endpoint and remain untrusted after download.

The development malware adapter is disabled by design. Do not deploy with `MALWARE_SCANNER=disabled`; connect a fail-closed production scanner first. See `docs/submission-security.md` for the real-evaluator isolation checklist.
