# Screenshot Analyzer

Batch analyze screenshots using local vision models. Auto-categorizes by source app, content type, extracts text, and stores structured metadata in SQLite.

**Runs 100% locally** — no API keys, no cloud, no cost per image.

## Features

- **Two analysis backends**:
  - `ocr` — EasyOCR + regex heuristics (fast, ~2GB memory)
  - `vlm` — Vision-Language Model (smart, ~4-8GB memory)
- **Fast** — 6 parallel workers, aggressive resizing (~50 images/sec)
- **GPU acceleration** — Uses MPS (Apple Silicon) or CUDA automatically
- **Structured output** — SQLite database + JSON export + HTML report
- **Resume support** — Skips already-analyzed images (use `--no-skip-existing` to force re-analysis)

## Setup

```bash
./scripts/init.sh
```

Or manually:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

```bash
# Analyze with OCR backend (fast, default)
python src/analyzer.py /path/to/screenshots

# More workers for faster processing (default: 6)
python src/analyzer.py /path/to/screenshots --workers 8

# Test on 10 images first
python src/analyzer.py /path/to/screenshots --limit 10

# Use VLM backend (smarter analysis)
python src/analyzer.py /path/to/screenshots --backend vlm

# Dry run (count images, estimate time)
python src/analyzer.py /path/to/screenshots --dry-run

# Custom output location
python src/analyzer.py /path/to/screenshots --output ./results

# Re-analyze all images (populate new fields after schema changes)
python src/analyzer.py /path/to/screenshots --no-skip-existing
```

## Backends

### OCR Backend (default)

Uses EasyOCR to extract text, then applies regex patterns to classify:

- **Speed**: ~50 images/sec (6 workers), ~12 images/sec (1 worker)
- **Memory**: ~2GB per worker
- **Quality**: Good for text-heavy screenshots

### VLM Backend

Uses a local Vision-Language Model (Moondream2) for semantic understanding:

- **Speed**: ~2-5 seconds per image
- **Memory**: ~4-8GB (uses MPS/GPU)
- **Quality**: Better for complex screenshots, understands context

First run downloads the model (~2GB).

## Output

Creates `_analysis/` folder in target directory with:

- `screenshots.db` — SQLite database
- `screenshots.json` — Full export

## Querying Results

```bash
# Breakdown by source app
sqlite3 _analysis/screenshots.db "SELECT source_app, COUNT(*) FROM screenshots GROUP BY source_app ORDER BY 2 DESC"

# Find Instagram posts
sqlite3 _analysis/screenshots.db "SELECT filename, description FROM screenshots WHERE source_app='instagram'"

# Search by topic
sqlite3 _analysis/screenshots.db "SELECT filename, topics FROM screenshots WHERE topics LIKE '%finance%'"

# Full-text search in extracted text
sqlite3 _analysis/screenshots.db "SELECT filename, primary_text FROM screenshots WHERE primary_text LIKE '%error%'"

# See which backend was used
sqlite3 _analysis/screenshots.db "SELECT backend, COUNT(*) FROM screenshots GROUP BY backend"
```

## Schema

| Field | Type | Description |
|-------|------|-------------|
| source_app | text | instagram, twitter, slack, terminal, browser, etc. |
| content_type | text | social_post, conversation, code, receipt, etc. |
| primary_text | text | Extracted text (first 500 chars) |
| people_mentioned | json | @handles and names |
| topics | json | Up to 5 topic tags |
| description | text | 1-2 sentence summary |
| confidence | real | 0.0-1.0 |
| backend | text | ocr or vlm |
| image_width | int | Image width in pixels |
| image_height | int | Image height in pixels |

## Performance

| Backend | Speed | Memory | Best For |
|---------|-------|--------|----------|
| ocr | ~1-3s/img | ~2GB | Text-heavy screenshots, fast batch processing |
| vlm | ~2-5s/img | ~4-8GB | Complex images, semantic understanding |

Both backends use GPU (MPS on Apple Silicon, CUDA on NVIDIA) when available.
