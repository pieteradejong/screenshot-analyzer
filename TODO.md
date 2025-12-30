# TODO

## Now (doing in this pass)

- **Secrets**
  - **Add `.env.example`** with `ANTHROPIC_API_KEY=...` template.
  - **Load `.env` automatically** in `scripts/run.sh` (safe parsing; no `grep | xargs`).
  - **Update `.gitignore`** to ignore analyzer outputs (e.g. `_analysis/`, `*.db`, exports).

- **Docs / entrypoints**
  - Fix `README.md` (remove stray heredoc line, align paths/commands).
  - Add root `./init.sh`, `./test.sh`, `./run.sh` wrappers that delegate to `scripts/*` (matches repo “source of truth” rules).
  - Fix `src/analyzer.py` docstring examples (file name).

- **CLI correctness**
  - Fix `--skip-existing` so it can be disabled (`--no-skip-existing`).
  - Make `--output` work for nested paths (mkdir parents).

- **Reliability / cost safety**
  - Add retries with capped exponential backoff + jitter for transient Anthropic failures (429/5xx/timeouts).
  - Add configurable timeout and retry knobs.
  - Make API client usage thread-safe (client per thread via thread-local).

- **Performance**
  - Batch SQLite writes in transactions (commit every N rows) instead of per-row commits.

- **Quality gates**
  - Add `ruff` (lint+format) + `pytest` (offline unit tests).
  - Update `scripts/project.conf` so `scripts/test.sh` runs pytest instead of only `--help`.

## Next (near-term)

- **Better output hygiene**
  - Write JSON export atomically (temp file + rename).
  - Add `--resume-errors` / reprocess failed rows.

- **UX**
  - Add `--dry-run` (count images, estimate cost).
  - Add `--include/--exclude` glob filters.
  - Add `--model` flag and document supported models.

- **Metadata**
  - Add `image_width/height` and basic EXIF timestamps if available.
  - Add a stable content hash to detect moved/renamed duplicates.

## Later

- **Pipeline**
  - Optional OCR fallback for low-confidence text extraction.
  - Optional embeddings for semantic search.

- **Packaging**
  - Turn into an installable package + `screenshot-analyzer` console script.
  - Add CI (GitHub Actions) running `./test.sh`.

