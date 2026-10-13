# Student Submission Spec

Each evaluated submission must eventually include two files:

- A development notebook: `.ipynb`
- A model archive: `.zip`

The notebook is stored for review and reproducibility. The server must not execute notebooks automatically.

The model ZIP root must contain:

```text
submission.json
model/
  config.json
  model.safetensors
  tokenizer files allowed by the task
```

`submission.json` must include at least:

```json
{
  "base_model": "course/registered-base-model"
}
```

Do not include optimizer state, intermediate checkpoints, datasets, caches, or training logs in the ZIP.

## Colab Export Helper Sketch

```python
from pathlib import Path
import json
import shutil

def export_submission(model, tokenizer, metadata, output_zip="submission.zip"):
    root = Path("submission")
    model_dir = root / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(model_dir, safe_serialization=True)
    tokenizer.save_pretrained(model_dir)
    (root / "submission.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    shutil.make_archive("submission", "zip", root)
```

Python modules, shell scripts, native libraries, executables, pickle files, `.pt`, `.pth`, `.bin`, nested archives, external URLs, custom Hugging Face code, and `auto_map` are rejected. The task must register the base model and architecture. Model weights must be safetensors. `trust_remote_code=False` is mandatory.

Notebook outputs may contain unsafe browser content. The platform stores the original until successful evaluation, but never executes it or renders its raw HTML. Admin review/download is available only while the file is retained. Treat a downloaded notebook as an untrusted file.

## Operating policy

No student account, password, login or token is required. Enter your roster student number when submitting; it links records and stays off the public leaderboard. Nickname/emoji are fixed by your first submission. Ask an admin to correct them. Avoid personal information in public nickname/model name. Submissions are unlimited within the task period. The first successfully evaluated Baseline is fixed, and best successful Development is automatic; improvement is Development minus Baseline (unknown if either is missing).

This is a practice website. Submit the final Notebook, final model ZIP and short development report to e-Class LMS. Submission ID is not an LMS deliverable. Local browser history is convenience only, not official submission proof or authentication.

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
