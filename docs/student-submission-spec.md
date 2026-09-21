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

Notebook outputs may contain unsafe browser content. The platform preserves the original for authenticated review but never executes it or renders its raw HTML. Treat a downloaded notebook as an untrusted file.
