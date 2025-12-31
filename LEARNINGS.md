# Learnings

Architectural decisions, trade-offs, and lessons learned from building the Screenshot Analyzer.

## Schema Migrations vs Data Backfill

### The Problem

When adding new fields to the database schema (e.g., `has_people`), existing rows need those fields populated. However, there's a fundamental difference between:

1. **Schema migration** (adding a column) — fast, automatic
2. **Data backfill** (populating values) — slow, requires re-processing images

### The Design Decision

We separate these concerns:

- **Migrations** (`init_db()` in `analyzer.py`):
  - Automatically add missing columns via `ALTER TABLE`
  - Fast (no image processing)
  - Leaves existing rows with `NULL` values
  - Safe to run multiple times (idempotent)

- **Data population** (analysis loop):
  - By default, skips files already in database (`--skip-existing`)
  - Only processes new images
  - Requires explicit opt-in (`--no-skip-existing`) to re-analyze existing rows

### Why This Design?

**Performance optimization:**
- If you have 1,000 analyzed images and add 10 new ones, you only want to process the 10 new ones
- Re-processing 1,000 images (especially with OCR/VLM) is slow and expensive
- Default behavior assumes: "if it's already analyzed, trust that analysis"

**User control:**
- Schema migrations are automatic and fast (no user action needed)
- Data backfill is opt-in (user decides when to pay the cost)
- Allows incremental backfilling (process in batches if needed)

### The Trade-off

**When you add new fields:**
- Existing rows get `NULL` values (column exists, but no data)
- Users must explicitly run `--no-skip-existing` to populate those fields
- This can be surprising if you don't understand the architecture

**Example:**
```bash
# Database has 1,000 rows analyzed before has_people existed
# Migration adds column automatically (has_people=NULL for all rows)
# People tab shows 0 results

# Solution: force re-analysis
python src/analyzer.py /path/to/screenshots --no-skip-existing
# Now all 1,000 rows get has_people populated
```

### Verification

Use `scripts/verify_db.py` to check if fields are populated:

```bash
python scripts/verify_db.py
# Shows has_people=NULL for most rows? → Need to re-analyze
```

### Alternative Approaches Considered

1. **Auto-backfill on migration**: Rejected because it's expensive and unexpected
2. **Separate backfill command**: Could work, but adds complexity
3. **Version tracking**: Could mark rows as "needs backfill", but adds schema complexity

### Current Solution

The current approach balances:
- ✅ Fast schema updates (automatic migrations)
- ✅ User control over expensive operations
- ✅ Incremental processing capability
- ⚠️ Requires user awareness of the distinction

**Documentation:**
- Help text explains `--no-skip-existing` flag
- `scripts/verify_db.py` warns when fields are NULL
- This file documents the architectural decision

## Face Detection Reliability

### Current Implementation

Uses OpenCV Haar cascade (`haarcascade_frontalface_default.xml`):
- Fast (~10-50ms per image)
- Lightweight (no extra dependencies beyond opencv-python-headless)
- Limited accuracy (misses small faces, profiles, low-contrast faces)

### Known Limitations

1. **Small faces**: Minimum size `(30, 30)` may miss faces in screenshots
2. **Profile/partial faces**: Only detects frontal faces
3. **Image quality**: Runs on JPEG-compressed, downscaled images (max 600px)
4. **False negatives**: Common in real-world screenshots

### Future Improvements

1. **Better detector**: OpenCV DNN face detector (SSD-based) or MediaPipe
2. **Person detection**: YOLO/MobileNet-SSD detects bodies, not just faces
3. **Multi-scale detection**: Run at multiple resolutions
4. **Hybrid approach**: Fast detector + VLM fallback for negatives

### Verification

Check detection quality:
```bash
python scripts/verify_db.py
# Look at "People Detection Stats" section
# If has_people=0 for images you know have people → detector limitations
```
