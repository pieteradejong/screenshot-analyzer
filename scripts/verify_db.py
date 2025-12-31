#!/usr/bin/env python3
"""
Database Verification Script for Screenshot Analyzer.

Inspects screenshots.db and prints a human-readable summary of:
- Schema presence (key columns)
- Row counts and error status
- Text extraction stats (has_text, primary_text)
- People detection stats (has_people)
- Backend breakdown
- Migration hints

Usage:
    python scripts/verify_db.py
    python scripts/verify_db.py --db /path/to/screenshots.db
    python scripts/verify_db.py --limit 20
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def check_db_exists(db_path: Path) -> bool:
    """Check if database file exists."""
    if not db_path.exists():
        print(f"Error: Database not found: {db_path}")
        print(f"  Expected location: {db_path.absolute()}")
        return False
    return True


def get_schema_columns(conn: sqlite3.Connection) -> set[str]:
    """Get set of column names from screenshots table."""
    cursor = conn.execute("PRAGMA table_info(screenshots)")
    return {row[1] for row in cursor.fetchall()}


def print_section(title: str):
    """Print a section header."""
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_subsection(title: str):
    """Print a subsection header."""
    print()
    print(f"  {title}")
    print("  " + "-" * 68)


def verify_db(db_path: Path, sample_limit: int = 10) -> None:
    """Verify database contents and print summary."""
    if not check_db_exists(db_path):
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    print_section("Database Verification Report")
    print(f"  Database: {db_path.absolute()}")

    # Schema check
    print_section("Schema Check")
    columns = get_schema_columns(conn)
    required_columns = [
        "has_text",
        "primary_text",
        "has_people",
        "backend",
        "error",
        "source_app",
        "content_type",
    ]

    for col in required_columns:
        status = "✓" if col in columns else "✗ MISSING"
        print(f"    {status:12} {col}")

    # Basic counts
    print_section("Row Counts")
    cursor = conn.execute("SELECT COUNT(*) FROM screenshots")
    total = cursor.fetchone()[0]
    print(f"    Total rows: {total}")

    cursor = conn.execute("SELECT COUNT(*) FROM screenshots WHERE error IS NULL")
    ok_count = cursor.fetchone()[0]
    print(f"    Successful (error IS NULL): {ok_count}")

    cursor = conn.execute("SELECT COUNT(*) FROM screenshots WHERE error IS NOT NULL")
    error_count = cursor.fetchone()[0]
    print(f"    Failed (error IS NOT NULL): {error_count}")

    if total == 0:
        print("\n  ⚠ Database is empty. Run analyzer first.")
        conn.close()
        return

    # Text stats
    print_section("Text Extraction Stats")
    cursor = conn.execute(
        """
        SELECT 
            SUM(CASE WHEN has_text=1 THEN 1 ELSE 0 END) AS has_text_yes,
            SUM(CASE WHEN has_text=0 THEN 1 ELSE 0 END) AS has_text_no,
            SUM(CASE WHEN has_text IS NULL THEN 1 ELSE 0 END) AS has_text_null
        FROM screenshots WHERE error IS NULL
    """
    )
    row = cursor.fetchone()
    has_text_yes = row[0] or 0
    has_text_no = row[1] or 0
    has_text_null = row[2] or 0
    print(f"    has_text=1:  {has_text_yes}")
    print(f"    has_text=0:  {has_text_no}")
    print(f"    has_text=NULL: {has_text_null}")

    cursor = conn.execute(
        """
        SELECT COUNT(*) FROM screenshots 
        WHERE error IS NULL 
        AND primary_text IS NOT NULL 
        AND LENGTH(TRIM(primary_text)) > 0
    """
    )
    nonempty_text = cursor.fetchone()[0]
    print(f"    Non-empty primary_text: {nonempty_text}")

    print_subsection(f"Sample rows with text (top {sample_limit} by length)")
    cursor = conn.execute(
        """
        SELECT filename, LENGTH(primary_text) AS n, 
               SUBSTR(primary_text, 1, 100) AS preview
        FROM screenshots 
        WHERE error IS NULL 
        AND primary_text IS NOT NULL 
        AND LENGTH(TRIM(primary_text)) > 0
        ORDER BY n DESC 
        LIMIT ?
    """,
        (sample_limit,),
    )
    for row in cursor:
        print(f"      {row['filename']:40} [{row['n']:4} chars] {row['preview'][:60]}...")

    # People stats
    print_section("People Detection Stats")
    cursor = conn.execute(
        """
        SELECT 
            SUM(CASE WHEN has_people=1 THEN 1 ELSE 0 END) AS people_yes,
            SUM(CASE WHEN has_people=0 THEN 1 ELSE 0 END) AS people_no,
            SUM(CASE WHEN has_people IS NULL THEN 1 ELSE 0 END) AS people_null
        FROM screenshots WHERE error IS NULL
    """
    )
    row = cursor.fetchone()
    people_yes = row[0] or 0
    people_no = row[1] or 0
    people_null = row[2] or 0
    print(f"    has_people=1:  {people_yes}")
    print(f"    has_people=0:  {people_no}")
    print(f"    has_people=NULL: {people_null}")

    if people_null > ok_count * 0.5:
        print()
        print(
            "  ⚠ WARNING: Most rows have NULL has_people. This likely means"
        )
        print(
            "     the database was created before has_people was added."
        )
        print(
            "     Re-run analyzer with --no-skip-existing to populate:"
        )
        print(f"       python src/analyzer.py /path/to/screenshots --no-skip-existing")

    if people_yes > 0:
        print_subsection(f"Sample rows with people detected (first {sample_limit})")
        cursor = conn.execute(
            """
            SELECT filename, backend, analyzed_at
            FROM screenshots 
            WHERE error IS NULL AND has_people=1
            ORDER BY analyzed_at DESC
            LIMIT ?
        """,
            (sample_limit,),
        )
        for row in cursor:
            print(f"      {row['filename']:40} [{row['backend'] or 'unknown':8}] {row['analyzed_at']}")

    # Backend breakdown
    print_section("Backend Breakdown")
    cursor = conn.execute(
        """
        SELECT backend, COUNT(*) AS count
        FROM screenshots 
        WHERE error IS NULL
        GROUP BY backend
        ORDER BY count DESC
    """
    )
    for row in cursor:
        backend = row["backend"] or "NULL"
        count = row["count"]
        print(f"    {backend:15} {count:6} rows")

    print_subsection("People detection by backend")
    cursor = conn.execute(
        """
        SELECT backend, 
               SUM(CASE WHEN has_people=1 THEN 1 ELSE 0 END) AS people_yes
        FROM screenshots 
        WHERE error IS NULL
        GROUP BY backend
        ORDER BY people_yes DESC
    """
    )
    for row in cursor:
        backend = row["backend"] or "NULL"
        people_count = row["people_yes"] or 0
        print(f"    {backend:15} {people_count:6} with people")

    conn.close()

    print()
    print("=" * 70)
    print("  Verification complete")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Verify screenshot analyzer database contents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="Path to screenshots.db (default: ./analysis/screenshots.db)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of sample rows to show (default: 10)",
    )

    args = parser.parse_args()

    # Default to ./analysis/screenshots.db if not provided
    db_path = args.db or Path("analysis") / "screenshots.db"

    verify_db(db_path, sample_limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
