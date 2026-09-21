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

Phase 2 writes audit rows for join code creation, roster upload, and task creation. Future admin operations that must be logged include nickname edits, score edits, reevaluation, invalidation, and deadline changes.

## Hidden Test Data

Hidden datasets, answer keys, passwords, and secret keys must stay outside Git. Use environment variables and mounted read-only volumes in production.

