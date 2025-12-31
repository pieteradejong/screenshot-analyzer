#!/usr/bin/env python3
"""
Screenshot Analyzer - Batch process screenshots using local vision models.

Supports multiple backends:
- ocr: EasyOCR + regex heuristics (fast, low memory)
- vlm: Vision-Language Model (smart, higher memory)

Performance optimizations:
- Aggressive image resizing (MAX_DIM=1200) for faster OCR
- Multiprocessing with separate model per worker (default: 6 workers)
- GPU acceleration via MPS (Apple Silicon) or CUDA
- File size filtering (skip icons <10KB and photos >10MB)

Configuration (via .env file):
    HOME_DIR=/Users/yourname           # Secret base path
    PROJECT_DIR=dev/projects/...       # Project location (relative to HOME_DIR)
    SOURCE_DIRS=screenshots            # Directories to scan (relative to HOME_DIR)

Usage:
    python analyzer.py                 # Uses SOURCE_DIRS from .env
    python analyzer.py /path/to/dir    # Override with specific directory
    python analyzer.py --limit 10
    python analyzer.py --backend vlm
"""

import argparse
import json
import multiprocessing as mp
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root
load_dotenv(Path(__file__).parent.parent / ".env")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# File size filters (skip non-screenshot files)
MIN_FILE_SIZE = 10 * 1024  # 10KB - skip tiny icons/thumbnails
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB - skip photos/videos

# Default number of workers (higher for 16GB+ machines)
DEFAULT_WORKERS = min(os.cpu_count() or 1, 6)


# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================


def get_source_dirs() -> list[Path]:
    """Resolve SOURCE_DIRS relative to HOME_DIR from environment."""
    home_dir = os.environ.get("HOME_DIR", "")
    source_dirs = os.environ.get("SOURCE_DIRS", "")

    if not home_dir or not source_dirs:
        return []

    home = Path(home_dir)
    return [home / d.strip() for d in source_dirs.split(":") if d.strip()]


def get_output_dir() -> Path:
    """Get output directory from HOME_DIR/PROJECT_DIR/analysis."""
    home_dir = os.environ.get("HOME_DIR", "")
    project_dir = os.environ.get("PROJECT_DIR", "")

    if home_dir and project_dir:
        return Path(home_dir) / project_dir / "analysis"
    return Path("analysis")  # fallback to current directory


# =============================================================================
# DATABASE
# =============================================================================


def init_db(db_path: Path, verbose: bool = False) -> sqlite3.Connection:
    """Initialize SQLite database with schema and migrate if needed."""
    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS screenshots (
            id INTEGER PRIMARY KEY,
            filepath TEXT UNIQUE,
            filename TEXT,
            file_size INTEGER,
            file_modified TEXT,
            analyzed_at TEXT,
            source_app TEXT,
            content_type TEXT,
            has_text INTEGER,
            primary_text TEXT,
            people_mentioned TEXT,
            topics TEXT,
            language TEXT,
            sentiment TEXT,
            description TEXT,
            confidence REAL,
            image_width INTEGER,
            image_height INTEGER,
            backend TEXT,
            raw_response TEXT,
            error TEXT,
            has_people INTEGER
        )
    """)

    # Migrate: add missing columns for older databases
    cursor = conn.execute("PRAGMA table_info(screenshots)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    migrations = []
    if "image_width" not in existing_cols:
        conn.execute("ALTER TABLE screenshots ADD COLUMN image_width INTEGER")
        migrations.append("image_width")
    if "image_height" not in existing_cols:
        conn.execute("ALTER TABLE screenshots ADD COLUMN image_height INTEGER")
        migrations.append("image_height")
    if "backend" not in existing_cols:
        conn.execute("ALTER TABLE screenshots ADD COLUMN backend TEXT")
        migrations.append("backend")
    if "has_people" not in existing_cols:
        conn.execute("ALTER TABLE screenshots ADD COLUMN has_people INTEGER")
        migrations.append("has_people")

    if migrations and verbose:
        print(f"  Migrated database: added columns {migrations}")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_app ON screenshots(source_app)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_type ON screenshots(content_type)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topics ON screenshots(topics)")
    conn.commit()
    return conn


def save_result(conn: sqlite3.Connection, filepath: Path, analysis: dict, backend: str):
    """Save analysis result to database."""
    stat = filepath.stat()

    conn.execute(
        """
        INSERT OR REPLACE INTO screenshots 
        (filepath, filename, file_size, file_modified, analyzed_at,
         source_app, content_type, has_text, primary_text, people_mentioned,
         topics, language, sentiment, description, confidence, 
         image_width, image_height, backend, raw_response, error, has_people)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            str(filepath),
            filepath.name,
            stat.st_size,
            datetime.fromtimestamp(stat.st_mtime).isoformat(),
            datetime.now().isoformat(),
            analysis.get("source_app"),
            analysis.get("content_type"),
            1 if analysis.get("has_text") else 0,
            analysis.get("primary_text"),
            json.dumps(analysis.get("people_mentioned", [])),
            json.dumps(analysis.get("topics", [])),
            analysis.get("language"),
            analysis.get("sentiment"),
            analysis.get("description"),
            analysis.get("confidence"),
            analysis.get("image_width"),
            analysis.get("image_height"),
            backend,
            json.dumps(analysis),
            analysis.get("error"),
            1 if analysis.get("has_people") else 0,
        ),
    )


def find_images(
    directories: list[Path],
    skip_analyzed: set[str] | None = None,
    filter_size: bool = True,
) -> tuple[list[Path], int, int]:
    """
    Find all supported image files in the given directories (flat, no recursion).

    Args:
        directories: List of directories to search (each scanned flat)
        skip_analyzed: Set of filepaths to skip
        filter_size: If True, skip files outside MIN/MAX_FILE_SIZE

    Returns:
        (images, skipped_small, skipped_large)
    """
    skip_analyzed = skip_analyzed or set()
    images = []
    skipped_small = 0
    skipped_large = 0

    for directory in directories:
        if not directory.is_dir():
            continue

        # Flat scan - only direct children, no recursion
        for path in directory.iterdir():
            if not path.is_file():
                continue

            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            if str(path) in skip_analyzed:
                continue

            if filter_size:
                try:
                    size = path.stat().st_size
                    if size < MIN_FILE_SIZE:
                        skipped_small += 1
                        continue
                    if size > MAX_FILE_SIZE:
                        skipped_large += 1
                        continue
                except OSError:
                    continue

            images.append(path)

    return images, skipped_small, skipped_large


def get_already_analyzed(conn: sqlite3.Connection) -> set[str]:
    """Get set of filepaths already in database."""
    cursor = conn.execute("SELECT filepath FROM screenshots WHERE error IS NULL")
    return {row[0] for row in cursor.fetchall()}


def cleanup_deleted_files(
    conn: sqlite3.Connection,
    source_directories: list[Path],
    remove_from_db: bool = False,
    verbose: bool = False,
) -> int:
    """
    Check database records against filesystem and mark deleted files.

    Args:
        conn: Database connection
        source_directories: Directories that were scanned (for context)
        remove_from_db: If True, delete records; if False, mark with error
        verbose: Print details about deleted files

    Returns:
        Number of deleted files found
    """
    cursor = conn.execute("SELECT filepath FROM screenshots WHERE error IS NULL")
    db_paths = {row[0] for row in cursor.fetchall()}

    deleted_count = 0
    for filepath_str in db_paths:
        filepath = Path(filepath_str)
        if not filepath.exists():
            if remove_from_db:
                conn.execute(
                    "DELETE FROM screenshots WHERE filepath = ?", (filepath_str,)
                )
            else:
                conn.execute(
                    "UPDATE screenshots SET error = ? WHERE filepath = ?",
                    (f"File deleted: {filepath_str}", filepath_str),
                )
            deleted_count += 1
            if verbose:
                action = "Removed" if remove_from_db else "Marked as deleted"
                print(f"  {action}: {filepath.name}")

    if deleted_count > 0:
        conn.commit()

    return deleted_count


# =============================================================================
# BACKEND FACTORY
# =============================================================================


def get_backend(name: str):
    """Get the appropriate backend by name."""
    from backends import OCRBackend, VLM_AVAILABLE, VLMBackend

    if name == "ocr":
        return OCRBackend()
    elif name == "vlm":
        if not VLM_AVAILABLE:
            print("Error: VLM backend requires 'transformers' package.")
            print("Install with: pip install transformers accelerate")
            sys.exit(1)
        return VLMBackend()
    else:
        print(f"Error: Unknown backend '{name}'. Use 'ocr' or 'vlm'.")
        sys.exit(1)


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Analyze screenshots with local vision models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Backends:
  ocr   EasyOCR + regex heuristics (fast, ~2GB memory per worker)
  vlm   Vision-Language Model (smart, ~4-8GB memory)

Performance:
  --workers controls parallel processing (default: {DEFAULT_WORKERS})
  Each worker loads its own model (~2GB RAM each)
  Images resized to max 1200px, files <10KB or >10MB skipped

Configuration:
  Set SOURCE_DIRS in .env to configure default directories.
  Output goes to PROJECT_DIR/analysis/ by default.

Examples:
  %(prog)s                           # Use SOURCE_DIRS from .env
  %(prog)s /path/to/screenshots      # Override with specific directory
  %(prog)s --workers 8
  %(prog)s --limit 10 --backend ocr
""",
    )
    parser.add_argument(
        "directory",
        type=Path,
        nargs="?",
        help="Directory to scan (overrides SOURCE_DIRS from .env)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory (default: PROJECT_DIR/analysis)",
    )
    parser.add_argument("--limit", type=int, help="Limit number of images to process")
    parser.add_argument(
        "--backend",
        choices=["ocr", "vlm"],
        default="ocr",
        help="Analysis backend (default: ocr)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip already analyzed files (default: true). Use --no-skip-existing to re-analyze and populate new fields.",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Re-analyze all files, even if already in database. Use this to populate new fields (e.g., has_people) for existing rows after schema migrations.",
    )
    parser.add_argument(
        "--remove-deleted",
        action="store_true",
        help="Remove deleted files from database instead of marking them",
    )
    parser.add_argument(
        "--workers",
        "-j",
        type=int,
        default=DEFAULT_WORKERS,
        help=f"Parallel workers (default: {DEFAULT_WORKERS}, each uses ~2GB RAM)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug info")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count images and estimate time without processing",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        default=True,
        help="Generate HTML report (default: true)",
    )
    parser.add_argument(
        "--no-html",
        action="store_false",
        dest="html",
        help="Skip HTML report generation",
    )

    args = parser.parse_args()

    # Resolve directories to scan
    if args.directory:
        # Command-line argument overrides .env
        if not args.directory.is_dir():
            print(f"Error: {args.directory} is not a directory")
            sys.exit(1)
        source_directories = [args.directory]
    else:
        # Use SOURCE_DIRS from .env
        source_directories = get_source_dirs()
        if not source_directories:
            print("Error: No directories to scan.")
            print("Either provide a directory argument or set SOURCE_DIRS in .env")
            print("  Example: python analyzer.py /path/to/screenshots")
            print("  Or set: SOURCE_DIRS=screenshots in your .env file")
            sys.exit(1)

        # Validate all directories exist
        missing = [d for d in source_directories if not d.is_dir()]
        if missing:
            print("Error: The following directories do not exist:")
            for d in missing:
                print(f"  - {d}")
            sys.exit(1)

    # Debug info
    if args.verbose:
        print("=== Debug Info ===")
        print(f"  Source directories: {[str(d) for d in source_directories]}")
        print(f"  Backend: {args.backend}")
        print(f"  Workers: {args.workers}")
        print(f"  Dry run: {args.dry_run}")
        print()

    # Setup output
    output_dir = args.output or get_output_dir()

    # For dry-run, we don't need to create output dir or init backend
    if args.dry_run:
        all_images, skipped_small, skipped_large = find_images(source_directories)
        if args.limit:
            all_images = all_images[: args.limit]

        # Estimate time based on backend and workers
        if args.backend == "ocr":
            # With aggressive resizing: ~0.05-0.1s per image per worker
            time_per_img = 0.08
        else:
            time_per_img = 3.0

        est_time = (len(all_images) * time_per_img) / args.workers

        print("=== Dry Run ===")
        print(f"  Directories: {[str(d) for d in source_directories]}")
        print(f"  Backend: {args.backend}")
        print(f"  Workers: {args.workers}")
        print(f"  Total images found: {len(all_images)}")
        if skipped_small or skipped_large:
            print(
                f"  Skipped: {skipped_small} tiny (<10KB), {skipped_large} large (>10MB)"
            )
        print(f"  Would process: {len(all_images)} images")
        print(f"  Estimated time: ~{est_time / 60:.1f} minutes")
        print(f"  Output would be: {output_dir}")
        print()
        print("Run without --dry-run to process.")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "screenshots.db"
    json_path = output_dir / "screenshots.json"

    conn = init_db(db_path, verbose=args.verbose)

    # Find images to process
    skip_set = get_already_analyzed(conn) if args.skip_existing else set()

    # Check for deleted files if skipping existing
    if args.skip_existing:
        deleted_count = cleanup_deleted_files(
            conn,
            source_directories,
            remove_from_db=args.remove_deleted,
            verbose=args.verbose,
        )
        if deleted_count > 0:
            action = "removed from" if args.remove_deleted else "marked in"
            print(f"Found {deleted_count} deleted files ({action} database)")
            print()

    images, skipped_small, skipped_large = find_images(source_directories, skip_set)

    if args.limit:
        images = images[: args.limit]

    print(f"Found {len(images)} images to analyze")
    print(f"Scanning: {[str(d) for d in source_directories]}")
    if skipped_small or skipped_large:
        print(f"Skipped: {skipped_small} tiny (<10KB), {skipped_large} large (>10MB)")
    print(f"Backend: {args.backend}")
    print(f"Workers: {args.workers}")
    print(f"Output: {output_dir}")
    print(f"Database: {db_path}")
    print()

    if not images:
        print("Nothing new to process.")
        # Still generate report from existing data if --html
        if args.html:
            report_path = output_dir / "report.html"
            from report import generate_report

            generate_report(db_path, report_path)
            print(f"HTML report: {report_path}")
        return

    # Process images
    processed = 0
    errors = 0
    start_time = time.time()

    # Determine GPU usage
    from backends.base import get_device

    device = get_device()
    use_gpu = device.type in ("mps", "cuda")

    print(f"Device: {device}")
    print(f"Initializing {args.workers} worker(s)...")
    print()

    if args.backend == "ocr" and args.workers > 1:
        # Use multiprocessing for OCR backend
        from backends.ocr import analyze_image_standalone

        # Prepare arguments for each image
        work_items = [(str(img), use_gpu, args.verbose) for img in images]

        # Use spawn method to avoid issues with forking
        ctx = mp.get_context("spawn")

        with ctx.Pool(processes=args.workers) as pool:
            # Process with imap_unordered for better progress reporting
            for path_str, result in pool.imap_unordered(
                analyze_image_standalone, work_items, chunksize=10
            ):
                img_path = Path(path_str)
                save_result(conn, img_path, result, args.backend)

                processed += 1
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                eta = (len(images) - processed) / rate if rate > 0 else 0
                pct = int(processed / len(images) * 100)

                if result.get("error"):
                    errors += 1
                    error_msg = result["error"]
                    print(f"✗ [{processed}/{len(images)}] {img_path.name}")
                    print(f"  ERROR: {error_msg[:80]}")
                else:
                    source = result.get("source_app", "unknown")
                    ctype = result.get("content_type", "unknown")
                    conf = result.get("confidence", 0)
                    has_text = result.get("has_text", False)
                    text_preview = ""
                    if has_text and result.get("primary_text"):
                        text_preview = result["primary_text"][:50].replace("\n", " ")
                        text_preview = f' "{text_preview}..."'

                    print(f"✓ [{processed}/{len(images)}] {img_path.name}")
                    print(f"  → {source} / {ctype} (conf: {conf:.0%}){text_preview}")

                # Progress line (less frequent to reduce noise)
                if processed % 50 == 0 or processed == len(images):
                    errors_str = f", {errors} failed" if errors > 0 else ""
                    print(
                        f"  ── {pct}% done | {rate:.1f}/s | ~{eta / 60:.0f}m remaining{errors_str}"
                    )
                    print()

                # Batch commit every 100 images
                if processed % 100 == 0:
                    conn.commit()

        # Final commit
        conn.commit()

    else:
        # Single-process mode (for VLM or --workers 1)
        backend = get_backend(args.backend)
        backend.initialize()

        for img_path in images:
            result = backend.analyze(img_path, verbose=args.verbose)
            save_result(conn, img_path, result, args.backend)

            processed += 1
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(images) - processed) / rate if rate > 0 else 0
            pct = int(processed / len(images) * 100)

            if result.get("error"):
                errors += 1
                error_msg = result["error"]
                print(f"✗ [{processed}/{len(images)}] {img_path.name}")
                print(f"  ERROR: {error_msg[:80]}")
            else:
                source = result.get("source_app", "unknown")
                ctype = result.get("content_type", "unknown")
                conf = result.get("confidence", 0)
                has_text = result.get("has_text", False)
                text_preview = ""
                if has_text and result.get("primary_text"):
                    text_preview = result["primary_text"][:50].replace("\n", " ")
                    text_preview = f' "{text_preview}..."'

                print(f"✓ [{processed}/{len(images)}] {img_path.name}")
                print(f"  → {source} / {ctype} (conf: {conf:.0%}){text_preview}")

            # Progress line
            if processed % 10 == 0 or processed == len(images):
                errors_str = f", {errors} failed" if errors > 0 else ""
                print(
                    f"  ── {pct}% done | {rate:.1f}/s | ~{eta / 60:.0f}m remaining{errors_str}"
                )
                print()

            # Batch commit
            if processed % 100 == 0:
                conn.commit()

        conn.commit()

    # Export to JSON
    cursor = conn.execute("SELECT * FROM screenshots")
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)

    # Generate HTML report
    report_path = output_dir / "report.html"
    if args.html:
        from report import generate_report

        generate_report(db_path, report_path)

    elapsed_total = time.time() - start_time
    rate_final = processed / elapsed_total if elapsed_total > 0 else 0

    print()
    print(f"Done! Processed {processed} images ({errors} errors)")
    print(f"Time: {elapsed_total / 60:.1f} minutes ({rate_final:.1f} images/sec)")
    print(f"Backend: {args.backend}")
    print(f"Database: {db_path}")
    print(f"JSON export: {json_path}")
    if args.html:
        print(f"HTML report: {report_path}")
    print()
    print("Query examples:")
    print(
        f'  sqlite3 {db_path} "SELECT source_app, COUNT(*) FROM screenshots GROUP BY source_app"'
    )
    print(
        f"  sqlite3 {db_path} \"SELECT filename, description FROM screenshots WHERE source_app='instagram'\""
    )


if __name__ == "__main__":
    main()
