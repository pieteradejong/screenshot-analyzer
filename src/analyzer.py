#!/usr/bin/env python3
"""
Screenshot Analyzer - Batch process screenshots using local OCR
Outputs structured metadata to SQLite + JSON

Usage:
    python analyzer.py /path/to/screenshots
    python analyzer.py /path/to/screenshots --limit 10
"""

import easyocr
import json
import sqlite3
import sys
import re
import argparse
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from PIL import Image

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

# Initialize EasyOCR reader (done lazily to avoid loading on --help)
_reader = None


def get_reader(verbose: bool = False) -> easyocr.Reader:
    """Get or create EasyOCR reader (singleton)."""
    global _reader
    if _reader is None:
        if verbose:
            print("Initializing EasyOCR (first run downloads models)...")
        _reader = easyocr.Reader(["en"], gpu=False, verbose=verbose)
        if verbose:
            print("EasyOCR ready.")
    return _reader


# =============================================================================
# HEURISTIC CLASSIFIERS
# =============================================================================

# Patterns for source_app detection
APP_PATTERNS = {
    "twitter": [
        r"\bretweet\b",
        r"\btweet\b",
        r"\blikes?\b.*\bretweets?\b",
        r"\breplies\b",
        r"@\w+.*\d+[hm]\b",  # @username 2h ago pattern
        r"\bfollow\b.*\bfollowing\b",
    ],
    "instagram": [
        r"\blikes?\b",
        r"\bcomments?\b",
        r"\bfollowers?\b",
        r"\bfollowing\b",
        r"\bstory\b",
        r"\breels?\b",
        r"\binstagram\b",
    ],
    "slack": [
        r"\bslack\b",
        r"#[a-z0-9_-]+",  # channel names
        r"\bthread\b",
        r"\breply in thread\b",
        r"\bedited\b.*\bago\b",
    ],
    "discord": [
        r"\bdiscord\b",
        r"#[a-z0-9_-]+",
        r"\bserver\b.*\bmembers?\b",
        r"\bonline\b.*\bmembers?\b",
    ],
    "whatsapp": [
        r"\bwhatsapp\b",
        r"\bdelivered\b",
        r"\bread\b.*\breceipts?\b",
        r"\blast seen\b",
    ],
    "messages": [
        r"\bimessage\b",
        r"\bdelivered\b",
        r"\bread\b",
        r"\btoday\b.*\d{1,2}:\d{2}",
    ],
    "email": [
        r"\bfrom:\b",
        r"\bto:\b",
        r"\bsubject:\b",
        r"\binbox\b",
        r"\bsent\b.*\bmail\b",
        r"\breply\b.*\bforward\b",
    ],
    "terminal": [
        r"\$\s+\w+",  # shell prompt
        r"^\s*\w+@\w+:",  # user@host:
        r"\bcommand not found\b",
        r"\bexit\b.*\bcode\b",
    ],
    "vscode": [
        r"\bvs\s*code\b",
        r"\bextensions?\b",
        r"\bproblems?\b.*\boutput\b",
        r"\bdebug console\b",
        r"\bterminal\b.*\boutput\b",
    ],
    "browser": [
        r"https?://",
        r"\bsearch\b.*\bgoogle\b",
        r"\bbookmarks?\b",
        r"\btabs?\b.*\bwindow\b",
        r"\bprivate\b.*\bbrowsing\b",
    ],
    "finder": [
        r"\bfinder\b",
        r"\bdesktop\b",
        r"\bdocuments?\b",
        r"\bdownloads?\b",
        r"\bapplications?\b",
        r"\bitems?\b.*\bavailable\b",
    ],
}

# Patterns for content_type detection
CONTENT_PATTERNS = {
    "code": [
        r"\bdef\s+\w+\s*\(",
        r"\bfunction\s+\w+\s*\(",
        r"\bclass\s+\w+",
        r"\bimport\s+\w+",
        r"\bfrom\s+\w+\s+import\b",
        r"\bconst\s+\w+\s*=",
        r"\blet\s+\w+\s*=",
        r"\bvar\s+\w+\s*=",
        r"=>\s*\{",
        r"\breturn\s+",
        r"```",
    ],
    "receipt": [
        r"\$\d+\.\d{2}",
        r"\btotal\b",
        r"\bsubtotal\b",
        r"\btax\b",
        r"\breceipt\b",
        r"\border\b.*\b#?\d+",
        r"\bpayment\b",
        r"\bcard\b.*\b\d{4}\b",
    ],
    "conversation": [
        r"\d{1,2}:\d{2}\s*(am|pm)?",  # timestamps
        r"\bsent\b",
        r"\bdelivered\b",
        r"\bread\b",
        r"\btyping\b",
        r"\bonline\b",
    ],
    "error_message": [
        r"\berror\b",
        r"\bfailed\b",
        r"\bexception\b",
        r"\bwarning\b",
        r"\bcritical\b",
        r"\btraceback\b",
        r"\bstack\s*trace\b",
    ],
    "article": [
        r"\bread\s*more\b",
        r"\bshare\b",
        r"\bpublished\b",
        r"\bauthor\b",
        r"\bmin\s*read\b",
        r"\bcomments?\s*\(\d+\)",
    ],
    "settings": [
        r"\bsettings?\b",
        r"\bpreferences?\b",
        r"\boptions?\b",
        r"\bconfigure\b",
        r"\benable\b",
        r"\bdisable\b",
        r"\btoggle\b",
    ],
    "dashboard": [
        r"\bdashboard\b",
        r"\banalytics?\b",
        r"\bmetrics?\b",
        r"\bstatistics?\b",
        r"\boverview\b",
        r"\d+%",
    ],
    "form": [
        r"\bsubmit\b",
        r"\bcancel\b",
        r"\brequired\b",
        r"\benter\s+your\b",
        r"\bpassword\b",
        r"\bemail\b.*\baddress\b",
    ],
    "social_post": [
        r"\blikes?\b",
        r"\bcomments?\b",
        r"\bshares?\b",
        r"\bretweets?\b",
        r"\bfollowers?\b",
    ],
}


def classify_source_app(text: str) -> tuple[str, float]:
    """Classify the source app based on extracted text patterns."""
    text_lower = text.lower()
    scores = {}

    for app, patterns in APP_PATTERNS.items():
        score = 0
        for pattern in patterns:
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
            score += matches
        if score > 0:
            scores[app] = score

    if not scores:
        return "unknown", 0.3

    best_app = max(scores, key=scores.get)
    # Normalize confidence (cap at 1.0)
    confidence = min(scores[best_app] / 5.0, 1.0)
    return best_app, round(confidence, 2)


def classify_content_type(text: str) -> tuple[str, float]:
    """Classify the content type based on extracted text patterns."""
    text_lower = text.lower()
    scores = {}

    for content_type, patterns in CONTENT_PATTERNS.items():
        score = 0
        for pattern in patterns:
            matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
            score += matches
        if score > 0:
            scores[content_type] = score

    if not scores:
        # Default based on text length
        if len(text) < 50:
            return "photo", 0.3
        elif len(text) > 500:
            return "article", 0.4
        return "unknown", 0.3

    best_type = max(scores, key=scores.get)
    confidence = min(scores[best_type] / 5.0, 1.0)
    return best_type, round(confidence, 2)


def detect_language(text: str) -> str:
    """Simple language detection based on character patterns."""
    if not text:
        return "unknown"

    # Very basic heuristics
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[áéíóúñ¿¡]", text, re.IGNORECASE):
        return "es"
    if re.search(r"[àâçéèêëïîôùûü]", text, re.IGNORECASE):
        return "fr"
    if re.search(r"[äöüß]", text, re.IGNORECASE):
        return "de"
    if re.search(r"[ïëéèüáó]", text, re.IGNORECASE):
        return "nl"

    return "en"


def detect_sentiment(text: str) -> str:
    """Simple sentiment detection based on keywords."""
    text_lower = text.lower()

    positive = len(
        re.findall(
            r"\b(great|awesome|love|excellent|amazing|good|happy|thanks|beautiful|perfect)\b",
            text_lower,
        )
    )
    negative = len(
        re.findall(
            r"\b(error|failed|bad|terrible|awful|hate|angry|sad|broken|wrong|issue|problem)\b",
            text_lower,
        )
    )

    if positive > negative:
        return "positive"
    elif negative > positive:
        return "negative"
    elif positive > 0 and negative > 0:
        return "mixed"
    return "neutral"


def extract_people(text: str) -> list[str]:
    """Extract @mentions and potential names from text."""
    mentions = re.findall(r"@(\w+)", text)
    return list(set(mentions))[:10]  # Limit to 10


def extract_topics(text: str, source_app: str, content_type: str) -> list[str]:
    """Extract topic tags from text and classifications."""
    topics = []

    # Add source and content as topics
    if source_app != "unknown":
        topics.append(source_app)
    if content_type != "unknown":
        topics.append(content_type)

    # Extract hashtags
    hashtags = re.findall(r"#(\w+)", text)
    topics.extend(hashtags[:3])

    # Look for common topic keywords
    text_lower = text.lower()
    topic_keywords = [
        "finance",
        "tech",
        "programming",
        "design",
        "music",
        "travel",
        "food",
        "sports",
        "news",
        "gaming",
        "ai",
        "crypto",
        "startup",
        "health",
    ]
    for keyword in topic_keywords:
        if keyword in text_lower:
            topics.append(keyword)

    return list(set(topics))[:5]


def generate_description(
    text: str, source_app: str, content_type: str, has_text: bool
) -> str:
    """Generate a brief description of the screenshot."""
    if not has_text:
        return f"Screenshot from {source_app}, appears to be {content_type} content with no readable text."

    # Get first meaningful sentence or chunk
    sentences = re.split(r"[.!?\n]", text)
    preview = ""
    for s in sentences:
        s = s.strip()
        if len(s) > 20:
            preview = s[:100]
            break

    if preview:
        return f"{source_app.title()} {content_type}: {preview}..."
    return f"Screenshot from {source_app} showing {content_type} content."


# =============================================================================
# CORE ANALYSIS
# =============================================================================


def analyze_image(reader: easyocr.Reader, path: Path, verbose: bool = False) -> dict:
    """Analyze image using EasyOCR and heuristics."""
    try:
        # Get image info
        with Image.open(path) as img:
            width, height = img.size

        # Extract text with EasyOCR
        results = reader.readtext(str(path))

        # Combine all detected text
        text_parts = [result[1] for result in results]
        full_text = " ".join(text_parts)
        has_text = len(full_text.strip()) > 0

        # Classify
        source_app, app_confidence = classify_source_app(full_text)
        content_type, type_confidence = classify_content_type(full_text)
        language = detect_language(full_text)
        sentiment = detect_sentiment(full_text)
        people = extract_people(full_text)
        topics = extract_topics(full_text, source_app, content_type)
        description = generate_description(
            full_text, source_app, content_type, has_text
        )

        # Average confidence
        confidence = round((app_confidence + type_confidence) / 2, 2)

        return {
            "source_app": source_app,
            "content_type": content_type,
            "has_text": has_text,
            "primary_text": full_text[:500] if full_text else None,
            "people_mentioned": people,
            "topics": topics,
            "language": language,
            "sentiment": sentiment,
            "description": description,
            "confidence": confidence,
            "image_width": width,
            "image_height": height,
        }

    except Exception as e:
        if verbose:
            print(f"  Error analyzing {path.name}: {e}")
        return {"error": str(e)}


def init_db(db_path: Path) -> sqlite3.Connection:
    """Initialize SQLite database with schema."""
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
            raw_response TEXT,
            error TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_app ON screenshots(source_app)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_type ON screenshots(content_type)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_topics ON screenshots(topics)")
    conn.commit()
    return conn


def save_result(conn: sqlite3.Connection, filepath: Path, analysis: dict):
    """Save analysis result to database."""
    stat = filepath.stat()

    conn.execute(
        """
        INSERT OR REPLACE INTO screenshots 
        (filepath, filename, file_size, file_modified, analyzed_at,
         source_app, content_type, has_text, primary_text, people_mentioned,
         topics, language, sentiment, description, confidence, 
         image_width, image_height, raw_response, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(analysis),
            analysis.get("error"),
        ),
    )
    conn.commit()


def find_images(root: Path, skip_analyzed: set[str] = None) -> list[Path]:
    """Recursively find all supported image files."""
    skip_analyzed = skip_analyzed or set()
    images = []

    for path in root.rglob("*"):
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            if str(path) not in skip_analyzed:
                images.append(path)

    return images


def get_already_analyzed(conn: sqlite3.Connection) -> set[str]:
    """Get set of filepaths already in database."""
    cursor = conn.execute("SELECT filepath FROM screenshots WHERE error IS NULL")
    return {row[0] for row in cursor.fetchall()}


def main():
    parser = argparse.ArgumentParser(
        description="Analyze screenshots with local OCR (EasyOCR)"
    )
    parser.add_argument("directory", type=Path, help="Directory containing screenshots")
    parser.add_argument(
        "--output", type=Path, help="Output directory (default: <directory>/_analysis)"
    )
    parser.add_argument("--limit", type=int, help="Limit number of images to process")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip already analyzed files (default: true)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Parallel workers (default: 1, OCR is CPU-heavy)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug info")

    args = parser.parse_args()

    # Validate directory
    if not args.directory.is_dir():
        print(f"Error: {args.directory} is not a directory")
        sys.exit(1)

    # Initialize OCR
    if args.verbose:
        print("=== Debug Info ===")
        print(f"  Directory: {args.directory}")
        print(f"  Workers: {args.workers}")
        print()

    reader = get_reader(verbose=args.verbose)

    # Setup output
    output_dir = args.output or args.directory / "_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "screenshots.db"
    json_path = output_dir / "screenshots.json"

    conn = init_db(db_path)

    # Find images to process
    skip_set = get_already_analyzed(conn) if args.skip_existing else set()
    images = find_images(args.directory, skip_set)

    if args.limit:
        images = images[: args.limit]

    print(f"Found {len(images)} images to analyze")
    print(f"Output: {output_dir}")
    print(f"Database: {db_path}")
    print()

    if not images:
        print("Nothing to process.")
        return

    # Process images
    processed = 0
    errors = 0
    start_time = time.time()

    def process_one(img_path: Path) -> tuple[Path, dict]:
        result = analyze_image(reader, img_path, verbose=args.verbose)
        return img_path, result

    # Note: EasyOCR is not thread-safe by default, so we use 1 worker
    # For parallel processing, each worker would need its own reader
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process_one, img): img for img in images}

        for future in as_completed(futures):
            img_path, result = future.result()
            save_result(conn, img_path, result)

            processed += 1
            if result.get("error"):
                errors += 1
                error_msg = result["error"]
                if args.verbose:
                    status = f"ERROR: {error_msg}"
                else:
                    status = (
                        f"ERROR: {error_msg[:50]}..."
                        if len(error_msg) > 50
                        else f"ERROR: {error_msg}"
                    )
            else:
                status = f"{result.get('source_app', '?')} / {result.get('content_type', '?')}"

            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(images) - processed) / rate if rate > 0 else 0

            print(f"[{processed}/{len(images)}] {img_path.name[:40]:<40} → {status}")
            print(
                f"         Rate: {rate:.2f}/s | ETA: {eta / 60:.1f}m | Errors: {errors}"
            )

    # Export to JSON
    cursor = conn.execute("SELECT * FROM screenshots")
    columns = [desc[0] for desc in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    with open(json_path, "w") as f:
        json.dump(rows, f, indent=2)

    print()
    print(f"Done! Processed {processed} images ({errors} errors)")
    print(f"Database: {db_path}")
    print(f"JSON export: {json_path}")
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
