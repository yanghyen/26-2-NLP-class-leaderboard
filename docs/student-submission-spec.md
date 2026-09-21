# Student Submission Spec

Each evaluated submission must eventually include two files:

- A development notebook: `.ipynb`
- A model archive: `.zip`

The notebook is stored for review and reproducibility. The server must not execute notebooks automatically.

The model ZIP should contain:

```text
submission/
  model/
    config.json
    model.safetensors
    tokenizer files
  submission.json
```

`submission.json` must include at least:

```json
{
  "task": "sentiment",
  "student_id": "20260001",
  "model_name": "my-model",
  "base_model": "configured-by-task",
  "seed": 42
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

