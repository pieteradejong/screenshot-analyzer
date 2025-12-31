# TODO

## Completed

- [x] **Local Vision Backends** — Replaced Claude API with local backends:
  - `ocr` — EasyOCR + regex heuristics (fast, ~2GB memory)
  - `vlm` — Vision-Language Model/Moondream2 (smart, ~4-8GB memory)
- [x] **GPU Acceleration** — MPS (Apple Silicon) / CUDA auto-detection
- [x] **Backend Abstraction** — Pluggable `backends/` module structure
- [x] **CLI `--backend` flag** — Choose between `ocr` and `vlm`
- [x] **CLI `--no-skip-existing`** — Re-analyze all files
- [x] **CLI `--dry-run`** — Count images, estimate time
- [x] **`--output` nested paths** — mkdir parents automatically
- [x] **Documentation** — Updated README.md, created ARCHITECTURE.md, CONVENTIONS.md
- [x] **Secrets Cleanup** — Removed API key requirement
- [x] **image_width/height** — Added to schema and output
- [x] **Quality gates** — pytest test suite, ruff lint/format
- [x] **HTML Report** — Self-contained report.html with filtering, search, modal
- [x] **Easy run.sh** — Default directory via `SCREENSHOT_DIR` or `~/Pictures`
- [x] **Performance: Aggressive Image Resizing** — MAX_DIM=1200, JPEG 80%
- [x] **Performance: Multiprocessing** — Separate EasyOCR reader per worker (default: 6)
- [x] **Performance: Batch SQLite Commits** — Commit every 100 rows
- [x] **Performance: File Size Filtering** — Skip <10KB icons, >10MB photos

## Now (doing in this pass)

- **Secrets**
  - **Load `.env` automatically** in `scripts/run.sh` (safe parsing).
  - **Update `.gitignore`** to ignore analyzer outputs (`_analysis/`, `*.db`).

- **Docs / entrypoints**
  - Root `./init.sh`, `./test.sh`, `./run.sh` wrappers already exist.

## Next (near-term)

- **Better output hygiene**
  - Write JSON export atomically (temp file + rename).
  - Add `--resume-errors` / reprocess failed rows.

- **UX**
  - Add `--quality` flag to toggle speed vs accuracy mode.
  - Add `--include/--exclude` glob filters.
  - Add `--model` flag to select VLM model.

- **Metadata**
  - Add basic EXIF timestamps if available.
  - Add a stable content hash to detect moved/renamed duplicates.

- **Additional VLM models**
  - Qwen2-VL-2B
  - LLaVA-1.5-7B
  - Hybrid backend (OCR + VLM)

## Later

- **Pipeline**
  - Optional embeddings for semantic search.

- **Packaging**
  - Turn into an installable package + `screenshot-analyzer` console script.
  - Add CI (GitHub Actions) running `./test.sh`.
