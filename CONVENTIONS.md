# Conventions

Code style, patterns, and decisions for the Screenshot Analyzer project.

## Code Style

### Formatting

- **Formatter**: `ruff format`
- **Linter**: `ruff check`
- **Line length**: 88 characters (ruff default)
- **Quotes**: Double quotes for strings

Run before committing:

```bash
ruff format src
ruff check src --fix
```

### Imports

Order (enforced by ruff):

1. Standard library
2. Third-party packages
3. Local imports

```python
import json
import sys
from pathlib import Path

import torch
from PIL import Image

from backends.base import AnalysisBackend
```

## Patterns

### Backend Plugin Pattern

All analysis backends inherit from `AnalysisBackend`:

```python
class MyBackend(AnalysisBackend):
    def initialize(self) -> None:
        """Called once before first use. Load models here."""
        pass

    def analyze(self, path: Path, verbose: bool = False) -> dict:
        """Return standardized dict with all required fields."""
        pass
```

Always return all fields, even if empty/default.

### Device Detection

Use the shared `get_device()` helper:

```python
from backends.base import get_device

device = get_device()  # Returns mps, cuda, or cpu
model = model.to(device)
```

Never hardcode device strings.

### Confidence Scoring

For heuristic classifiers:

```python
# Count pattern matches, normalize to 0-1
confidence = min(match_count / 5.0, 1.0)

# Always provide a floor for unknown
if no_matches:
    return "unknown", 0.3
```

### Error Handling in Backends

Return errors in the result dict, don't raise:

```python
def analyze(self, path, verbose=False):
    try:
        # ... analysis ...
        return {"source_app": "twitter", ...}
    except Exception as e:
        if verbose:
            print(f"Error: {e}")
        return {"error": str(e)}
```

This allows batch processing to continue on failures.

## Testing

### Test Naming

```
test_<what>_<condition>.py
test_<component>.py
```

Examples:

- `test_ocr_classifiers.py`
- `test_database.py`
- `test_analyzer_cli.py`

### Test Structure

```python
class TestFeatureName:
    def test_happy_path(self):
        ...

    def test_edge_case(self):
        ...

    def test_error_case(self):
        ...
```

### Assertions for Confidence

Don't use exact equality for confidence scores:

```python
# Bad - brittle
assert confidence == 0.6

# Good - threshold-based
assert confidence >= 0.4
assert confidence <= 1.0
```

### Fixtures Over Setup

Use pytest fixtures, not setUp/tearDown:

```python
@pytest.fixture
def sample_data():
    return {"key": "value"}

def test_something(sample_data):
    assert sample_data["key"] == "value"
```

## Scripts

### Idempotent init.sh

`./init.sh` is safe to run multiple times:

- Skips venv creation if exists
- Skips pip install if packages present
- Use `--force` to reinstall everything

### Three-Script Pattern

| Script | Purpose | Exit 0 means |
|--------|---------|--------------|
| `./init.sh` | Setup environment | Ready to develop |
| `./test.sh` | Run all checks | Safe to deploy |
| `./run.sh` | Start analyzer | Running |

## Performance

### Image Resizing for OCR

Always resize large images before OCR:

```python
MAX_DIMENSION = 1600  # Never process images larger than this
MIN_SCALE = 0.5       # Never shrink more than 50%
```

**Why?**
- OCR time scales with pixel count (4x pixels = 4x time)
- Retina screenshots are 2x-3x larger than needed for text extraction
- Text must remain ≥10px tall for accurate OCR

### Multiprocessing vs Threading

Use **multiprocessing** for CPU-bound ML tasks:

```python
# Bad: EasyOCR is not thread-safe
with ThreadPoolExecutor(max_workers=4) as executor:
    ...

# Good: Each process gets its own model
with multiprocessing.Pool(processes=4) as pool:
    ...
```

**Key learnings**:
- EasyOCR loads a neural network (~100MB) per reader
- Threading shares the reader → race conditions
- Multiprocessing isolates readers → safe parallelism
- Use `spawn` context on macOS (fork has issues with PyTorch)

### Standalone Functions for Multiprocessing

Multiprocessing requires picklable functions. Use module-level functions, not methods:

```python
# Bad: Can't pickle instance method
class Backend:
    def analyze(self, path):
        ...

# Good: Module-level function with lazy init
_reader = None

def analyze_standalone(args):
    global _reader
    if _reader is None:
        _reader = easyocr.Reader(...)
    ...
```

### Batch Database Commits

Commit every N rows, not every row:

```python
# Bad: Disk I/O after every image
for img in images:
    save_result(conn, img, result)
    conn.commit()

# Good: Batch commits
for i, img in enumerate(images):
    save_result(conn, img, result)
    if i % 100 == 0:
        conn.commit()
conn.commit()  # Final commit
```

## Git

### Commit Messages

```
<type>: <description>

Types: add, update, fix, refactor, test, docs
```

Examples:

- `add: VLM backend with Moondream2 support`
- `fix: confidence threshold in Instagram detection`
- `test: add database CRUD tests`

### What to Commit

- Source code
- Tests
- Documentation
- requirements.txt

### What NOT to Commit

- `.venv/`
- `__pycache__/`
- `_analysis/` (output directory)
- `.env` (secrets)
- `*.db` (generated databases)
