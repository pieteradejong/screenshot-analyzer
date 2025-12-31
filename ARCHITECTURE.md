# Architecture

This document describes the architecture of the Screenshot Analyzer.

## Overview

Screenshot Analyzer is a batch image analysis tool that processes screenshots locally using pluggable backends. It extracts structured metadata and stores results in SQLite.

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI (analyzer.py)                        │
│  - Argument parsing                                              │
│  - Image discovery                                               │
│  - Multiprocessing orchestration                                 │
│  - Progress reporting                                            │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│   Worker 1    │       │   Worker 2    │       │   Worker N    │
│   (EasyOCR)   │       │   (EasyOCR)   │       │   (EasyOCR)   │
│               │       │               │       │               │
│ - Load image  │       │ - Load image  │       │ - Load image  │
│ - Resize      │       │ - Resize      │       │ - Resize      │
│ - OCR         │       │ - OCR         │       │ - OCR         │
│ - Classify    │       │ - Classify    │       │ - Classify    │
└───────────────┘       └───────────────┘       └───────────────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Stage 1: Storage                          │
│                                                                  │
│   screenshots.db (SQLite)    │    screenshots.json               │
│   - Queryable                │    - Portable export              │
│   - Indexed                  │    - Full data                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Stage 2: Reporting                          │
│                                                                  │
│   report.py                  →    report.html                    │
│   - Reads from SQLite        │    - Self-contained               │
│   - Generates HTML           │    - Filterable grid              │
│                              │    - Search & modal               │
└─────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
screenshot-analyzer/
├── src/
│   ├── analyzer.py          # Main CLI entry point
│   ├── report.py            # HTML report generator
│   ├── backends/
│   │   ├── __init__.py      # Backend exports
│   │   ├── base.py          # Abstract base class, device detection
│   │   ├── ocr.py           # EasyOCR + regex heuristics + multiprocessing
│   │   └── vlm.py           # Vision-Language Model (Moondream2)
│   └── tests/
│       ├── conftest.py      # Pytest fixtures
│       ├── test_analyzer_cli.py
│       ├── test_database.py
│       └── test_ocr_classifiers.py
├── scripts/
│   ├── init.sh              # Environment setup (idempotent)
│   ├── run.sh               # Run analyzer with defaults
│   └── test.sh              # Run tests
├── requirements.txt
├── README.md
├── ARCHITECTURE.md          # This file
└── CONVENTIONS.md           # Code style and patterns
```

## Backends

### Base Class

All backends inherit from `AnalysisBackend` (defined in `backends/base.py`):

```python
class AnalysisBackend(ABC):
    @abstractmethod
    def initialize(self) -> None:
        """Load models, setup resources."""
        pass

    @abstractmethod
    def analyze(self, path: Path, verbose: bool = False) -> dict:
        """Analyze image and return structured metadata."""
        pass
```

### OCR Backend

**File**: `backends/ocr.py`

Uses EasyOCR to extract text, then applies regex patterns to classify source app and content type.

**Flow**:
1. Load and resize image (if > 1600px) with PIL
2. Convert to JPEG bytes for memory efficiency
3. Extract text with EasyOCR
4. Apply regex patterns to classify source_app
5. Apply regex patterns to classify content_type
6. Extract @mentions, hashtags, topics
7. Detect language and sentiment
8. Generate description

**Patterns**: Defined as dictionaries mapping app/content type to list of regex patterns. Scores are computed by counting matches.

**Multiprocessing**: For parallel processing, `analyze_image_standalone()` is a module-level function that initializes its own EasyOCR reader per process.

### VLM Backend

**File**: `backends/vlm.py`

Uses a Vision-Language Model (Moondream2 by default) to semantically analyze screenshots.

**Flow**:
1. Load image with PIL
2. Encode image with model
3. Send structured prompt requesting JSON output
4. Parse JSON response
5. Apply defaults for missing fields

**Models supported**:
- `vikhyatk/moondream2` (default, ~2GB)
- Other HuggingFace vision models (requires code changes)

## Device Detection

Both backends use automatic GPU detection (`backends/base.py`):

```python
def get_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")  # Apple Silicon
    elif torch.cuda.is_available():
        return torch.device("cuda")  # NVIDIA
    return torch.device("cpu")
```

This enables:
- **Apple Silicon**: Metal Performance Shaders (MPS)
- **NVIDIA GPU**: CUDA
- **Fallback**: CPU

## Database Schema

SQLite database with the following schema:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| filepath | TEXT | Full path to image (unique) |
| filename | TEXT | Image filename |
| file_size | INTEGER | File size in bytes |
| file_modified | TEXT | File modification timestamp (ISO) |
| analyzed_at | TEXT | Analysis timestamp (ISO) |
| source_app | TEXT | Detected source application |
| content_type | TEXT | Detected content type |
| has_text | INTEGER | 1 if text was extracted |
| primary_text | TEXT | First 500 chars of extracted text |
| people_mentioned | TEXT | JSON array of @mentions |
| topics | TEXT | JSON array of topic tags |
| language | TEXT | Detected language code |
| sentiment | TEXT | positive/negative/neutral/mixed |
| description | TEXT | Generated description |
| confidence | REAL | Confidence score (0.0-1.0) |
| image_width | INTEGER | Image width in pixels |
| image_height | INTEGER | Image height in pixels |
| backend | TEXT | Backend used (ocr/vlm) |
| raw_response | TEXT | Full JSON analysis result |
| error | TEXT | Error message if failed |

**Indexes**:
- `idx_source_app` on `source_app`
- `idx_content_type` on `content_type`
- `idx_topics` on `topics`

## Adding a New Backend

1. Create `backends/mybackend.py`
2. Inherit from `AnalysisBackend`
3. Implement `initialize()` and `analyze()`
4. Add to `backends/__init__.py`
5. Add to `get_backend()` in `analyzer.py`

Example skeleton:

```python
from .base import AnalysisBackend, get_device

class MyBackend(AnalysisBackend):
    def __init__(self):
        self._device = get_device()
        self._model = None

    def initialize(self):
        # Load your model here
        pass

    def analyze(self, path, verbose=False):
        # Return dict with required fields
        return {
            "source_app": "unknown",
            "content_type": "unknown",
            "has_text": False,
            "primary_text": None,
            "people_mentioned": [],
            "topics": [],
            "language": "en",
            "sentiment": "neutral",
            "description": "...",
            "confidence": 0.5,
            "image_width": 0,
            "image_height": 0,
        }
```

## Testing

### Test Structure

Tests are in `src/tests/` and use pytest:

```
src/tests/
├── conftest.py              # Shared fixtures
├── test_analyzer_cli.py     # CLI argument tests
├── test_database.py         # SQLite operations
└── test_ocr_classifiers.py  # Regex heuristic tests
```

### Running Tests

```bash
./test.sh              # Full suite (tests + lint + format)
./test.sh --quick      # Skip format/type checks
./test.sh backend      # Just tests
./test.sh lint         # Just linting
```

### Test Categories

| Test File | What It Tests | Dependencies |
|-----------|---------------|--------------|
| `test_ocr_classifiers.py` | Regex patterns, confidence scoring | None (pure Python) |
| `test_database.py` | SQLite schema, CRUD operations | SQLite only |
| `test_analyzer_cli.py` | CLI args, imports | Subprocess |

### Fixtures

Key fixtures in `conftest.py`:

- `temp_dir` — Temporary directory for test outputs
- `sample_texts` — Dict of sample text for each app/content type
- `sample_image_path` — Minimal valid PNG for integration tests

### Confidence Scoring

The OCR backend computes confidence as:

```python
confidence = min(pattern_matches / 5.0, 1.0)
```

- 5+ matches → confidence 1.0
- 2 matches → confidence 0.4
- 0 matches → confidence 0.3 (default)

Tests should use `>= 0.3` or `>= 0.4` thresholds, not strict equality.

## Performance Optimizations

### Aggressive Image Resizing

Large images (Retina screenshots at 2880×1800) take 4x longer to OCR than smaller versions with minimal accuracy loss.

**Configuration** (in `backends/ocr.py`):

```python
MAX_DIMENSION = 1200  # Aggressive resize for speed (use 1600 for accuracy)
MIN_SCALE = 0.5       # Never shrink more than 50% (preserve text readability)
```

**Resizing heuristics**:
- Only resize if `max(width, height) > MAX_DIMENSION`
- Scale factor = `MAX_DIMENSION / max(width, height)`
- Apply floor: `scale = max(scale, MIN_SCALE)`
- Use LANCZOS resampling for quality
- Convert to JPEG at 80% quality (faster encoding)

**Why these values?**
- 1200px prioritizes speed over accuracy for batch processing
- 50% minimum ensures text remains at least 10-12px tall (OCR minimum)
- Retina (2x) screenshots: 2880×1800 → 1200×750 (~5x faster OCR)

### File Size Filtering

Skip files that are unlikely to be screenshots:

```python
MIN_FILE_SIZE = 10 * 1024       # 10KB - skip icons/thumbnails
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB - skip photos/videos
```

**Why?**
- Icons/thumbnails (<10KB) have no text to extract
- Large photos/videos (>10MB) are rarely screenshots
- Skipping early saves OCR initialization overhead

### Multiprocessing

EasyOCR loads a neural network (~100MB) that is not thread-safe. We use **multiprocessing** instead of threading.

**Architecture**:

```
Main Process
    │
    ├── Worker 1 (own EasyOCR reader)
    ├── Worker 2 (own EasyOCR reader)
    ├── Worker 3 (own EasyOCR reader)
    └── Worker 4 (own EasyOCR reader)
```

**Implementation**:
- `multiprocessing.Pool` with `spawn` context (avoids fork issues on macOS)
- `imap_unordered` for streaming results as they complete
- Each worker initializes its own reader on first use (lazy loading)
- Results are saved to SQLite in the main process

**Memory usage**: ~2GB per worker (EasyOCR model). With 4 workers = ~8GB RAM.

**Configuration**:
```bash
# Default: min(cpu_count, 4)
./run.sh --workers 4    # Use 4 parallel workers
./run.sh --workers 1    # Single process (less RAM)
```

### Batch SQLite Commits

Instead of committing after every row:

```python
if processed % 100 == 0:
    conn.commit()
```

This reduces disk I/O overhead by ~20%.

### Performance Benchmarks

| Configuration | Speed | Memory | Best For |
|--------------|-------|--------|----------|
| 1 worker, no resize | ~3 img/s | ~2GB | Low memory systems |
| 1 worker, aggressive resize | ~12 img/s | ~2GB | 8GB RAM machines |
| 6 workers, aggressive resize | ~50 img/s | ~12GB | 16GB+ RAM (default) |

**2,000 images** (typical batch):
- Before optimizations: ~11 minutes
- After optimizations (6 workers): ~40 seconds

**Optimizations applied**:
1. MAX_DIMENSION reduced from 1600 → 1200px
2. JPEG quality reduced from 85% → 80%
3. Default workers increased from 4 → 6
4. File size filtering (skip <10KB and >10MB)

## HTML Report

The analyzer generates a self-contained HTML report (`report.html`) with:

- Thumbnail grid of all analyzed screenshots
- Filter buttons by source app and content type
- Search box for descriptions and extracted text
- Click-to-expand modal with full details
- All CSS/JS inline (no external dependencies)

**Flow**:
```
SQLite DB → report.py → report.html → Browser
```

The report reads from the database, not the original images. This allows:
- Re-generating reports without re-analyzing
- Querying data directly with SQL
- Multiple views of the same data

## Future Enhancements

See `TODO.md` for planned improvements:

- Hybrid backend (OCR for text + VLM for classification)
- Additional VLM models (Qwen2-VL, LLaVA)
- Embedding generation for semantic search
