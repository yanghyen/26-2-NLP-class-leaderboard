# Submission Security Boundary

## Threat Model

Every notebook and model ZIP is untrusted. A submission may contain path traversal, links or device entries, archive bombs, executable/native code, pickle checkpoints, malformed parsers inputs, hostile notebook HTML, external paths, or metadata intended to enable Hugging Face custom code. It may also be designed to disclose another student's files, hidden tests, credentials, or host paths.

The API streams uploads into `incoming/<server UUID>` outside the web document root. It never uses a client filename as a path. Only artifacts that pass structural validation are atomically renamed into `artifacts/<submission UUID>`. Validation failures are deleted; malware scanner findings move to `quarantine/<submission UUID>` and are not downloadable or queued. Worker scratch data lives separately under `work/<job UUID>` and is removed in `finally`.

## Enforced Controls

- Notebook JSON is parsed and bounded by bytes, cells, source, and output size. It is stored but never executed, previewed, or inserted into browser HTML.
- ZIP local/central structure is checked before extraction. Absolute, drive, UNC/backslash, null, dot-segment, overlong, deep, duplicate, and case-colliding paths are rejected.
- Encrypted, unsupported-compression, concatenated, symlink, executable-bit, FIFO, socket, device, nested archive, excessive-file, excessive-size, and excessive-ratio entries are rejected.
- Extraction copies each entry into a confined temporary directory while rechecking actual byte counts. `extractall()` is not used.
- Task `artifact_policy.allowed_paths` is the file allowlist. Python, shell, JavaScript, native binaries, executables, pickle/PyTorch checkpoints, and unknown files are rejected before parser use. Executable signatures are rejected even under an allowed name.
- Required JSON files have depth, key, string, numeric, URL/path, and custom-code-field limits. `auto_map`, custom pipelines, external paths, and any non-false `trust_remote_code` setting are rejected.
- The task must register both the base model and architecture. Only safetensors weights are accepted. Header size, dtype, tensor count/name/shape/dimensions, offsets, aggregate bytes, file consistency, and the official safetensors parser are checked without loading tensor contents.
- `EvaluationContext.trust_remote_code` is immutable and always `False`. Student directories are never added to `PYTHONPATH`; no student command or module is run.
- Redis receives only a database Job UUID after validation and artifact promotion. A worker handles one Job at a time. Student artifact errors are not retried; server errors retry once. Every Job has isolated exception handling and scratch cleanup.
- Student APIs return safe codes/messages only. Internal validation details and malware signatures are admin-only fields. Student detail queries are owner-scoped and omit private scores.

## Malware Scanning

`MalwareScanner` is an adapter boundary. The checked-in development adapter reports `DISABLED`; this is visible in submission metadata and does not replace structural validation. Any configured but unavailable production scanner returns `ERROR` and validation fails closed. A real ClamAV adapter is intentionally deferred.

## Current Boundary And Deferred Hardening

The mock evaluator derives a deterministic score from a server-computed content digest and does not load the submitted model. The current worker process still has database, Redis, and artifact-volume access, so it is not an acceptable boundary for real model loading. Before a real evaluator is enabled, launch each evaluation in a disposable, non-root container with no network, read-only root and model mounts, hidden tests on a separate read-only mount, no secrets, dropped capabilities, `no-new-privileges`, PID/CPU/RAM/GPU/time limits, and a writable tmpfs only. Do not mount the Docker socket or host filesystem.

Deferred items: real ClamAV integration, quarantine management UI, custom AppArmor/seccomp profiles, notebook preview/sanitized rendering, real GPU inference, and hidden-test evaluation.

## Docker Verification Checklist

Docker was unavailable on the implementation machine. On a Docker host, verify:

- `docker compose config` and `docker compose build` succeed.
- API and worker run as the image's non-root `app` user with all capabilities dropped.
- Read-only root filesystems and `no-new-privileges` are active; only named storage and declared tmpfs paths are writable.
- Postgres/Redis reconnect and worker restart do not duplicate completed scores.
- Named-volume ownership permits uploads while cross-container permissions remain minimal.
- CPU, memory, PID, timeout, and disk exhaustion tests terminate one Job without stopping the next.
- The future real-evaluator container has no network route, credentials, Docker socket, host paths, or access to other submissions.
