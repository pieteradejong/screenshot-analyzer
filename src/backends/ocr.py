"""
OCR Backend: EasyOCR + regex heuristics for screenshot analysis.

Fast, low memory (~2GB), but limited to pattern matching.

Performance optimizations:
- Smart image resizing for faster OCR (MAX_DIM=1600)
- GPU acceleration via MPS (Apple Silicon) or CUDA
"""

import io
import re
import time
import warnings
from pathlib import Path

from PIL import Image

from .base import AnalysisBackend, get_device

# Suppress PyTorch MPS warnings
warnings.filterwarnings("ignore", message=".*pin_memory.*")

import easyocr  # noqa: E402

# =============================================================================
# IMAGE PREPROCESSING
# =============================================================================

# Maximum dimension (width or height) before resizing
# 1600px balances OCR accuracy with speed
MAX_DIMENSION = 1600

# Never scale below 50% of original (preserve text readability)
MIN_SCALE = 0.5


def prepare_image_for_ocr(path: Path) -> tuple[bytes, int, int, bool]:
    """
    Load and optionally resize image for faster OCR.

    Returns:
        tuple: (image_bytes, original_width, original_height, was_resized)

    Resizing heuristics:
    - Only resize if max(width, height) > MAX_DIMENSION
    - Never scale below MIN_SCALE (50%) to preserve text readability
    - Use LANCZOS resampling for quality
    - Returns JPEG bytes for OCR (faster than PNG for large images)
    """
    with Image.open(path) as img:
        orig_width, orig_height = img.size

        # Convert to RGB if necessary (for JPEG encoding)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Check if resizing is needed
        max_dim = max(orig_width, orig_height)
        if max_dim > MAX_DIMENSION:
            # Calculate scale factor
            scale = MAX_DIMENSION / max_dim

            # Apply minimum scale floor
            scale = max(scale, MIN_SCALE)

            # Resize
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
            img_resized = img.resize((new_width, new_height), Image.LANCZOS)

            # Convert to bytes
            buffer = io.BytesIO()
            img_resized.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue(), orig_width, orig_height, True
        else:
            # No resize needed, convert to bytes
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            return buffer.getvalue(), orig_width, orig_height, False


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
        r"@\w+.*\d+[hm]\b",
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
        r"#[a-z0-9_-]+",
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
        r"\$\s+\w+",
        r"^\s*\w+@\w+:",
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
        r"\d{1,2}:\d{2}\s*(am|pm)?",
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
    return list(set(mentions))[:10]


def extract_topics(text: str, source_app: str, content_type: str) -> list[str]:
    """Extract topic tags from text and classifications."""
    topics = []

    if source_app != "unknown":
        topics.append(source_app)
    if content_type != "unknown":
        topics.append(content_type)

    hashtags = re.findall(r"#(\w+)", text)
    topics.extend(hashtags[:3])

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
# OCR BACKEND
# =============================================================================


class OCRBackend(AnalysisBackend):
    """
    EasyOCR + regex heuristics backend.

    Performance optimizations:
    - Smart image resizing (MAX_DIM=1600, MIN_SCALE=0.5)
    - GPU acceleration via MPS or CUDA
    - JPEG encoding for memory efficiency
    """

    def __init__(self):
        self._reader = None
        self._device = get_device()

    def initialize(self) -> None:
        """Initialize EasyOCR reader with GPU if available."""
        if self._reader is not None:
            return

        print("Initializing OCR engine...")
        print(f"  Device: {self._device}")
        print(f"  Max image dimension: {MAX_DIMENSION}px")
        print("  (First run downloads ~100MB of models)")
        start = time.time()

        # Enable GPU for MPS/CUDA, but EasyOCR uses its own GPU detection
        # We pass gpu=True and let it figure out the backend
        use_gpu = self._device.type in ("mps", "cuda")
        self._reader = easyocr.Reader(["en"], gpu=use_gpu, verbose=False)

        elapsed = time.time() - start
        print(f"  OCR ready ({elapsed:.1f}s)")
        print()

    def analyze(self, path: Path, verbose: bool = False) -> dict:
        """Analyze image using EasyOCR and heuristics."""
        self.initialize()

        try:
            # Prepare image (resize if needed for faster OCR)
            image_bytes, orig_width, orig_height, was_resized = prepare_image_for_ocr(
                path
            )

            # Extract text with EasyOCR (from bytes)
            results = self._reader.readtext(image_bytes)

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
                "image_width": orig_width,
                "image_height": orig_height,
            }

        except Exception as e:
            if verbose:
                print(f"  Error analyzing {path.name}: {e}")
            return {"error": str(e)}


# =============================================================================
# MULTIPROCESSING SUPPORT
# =============================================================================

# Global reader for multiprocessing (initialized per process)
_process_reader = None


def _init_process_reader(use_gpu: bool) -> None:
    """Initialize reader for this process (called once per worker)."""
    global _process_reader
    if _process_reader is None:
        _process_reader = easyocr.Reader(["en"], gpu=use_gpu, verbose=False)


def analyze_image_standalone(args: tuple) -> tuple[str, dict]:
    """
    Standalone function for multiprocessing.

    Each process has its own EasyOCR reader instance.

    Args:
        args: (image_path_str, use_gpu, verbose)

    Returns:
        (image_path_str, result_dict)
    """
    global _process_reader
    path_str, use_gpu, verbose = args
    path = Path(path_str)

    # Initialize reader if needed (once per process)
    if _process_reader is None:
        _init_process_reader(use_gpu)

    try:
        # Prepare image
        image_bytes, orig_width, orig_height, was_resized = prepare_image_for_ocr(path)

        # Extract text
        results = _process_reader.readtext(image_bytes)

        # Combine text
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

        confidence = round((app_confidence + type_confidence) / 2, 2)

        return path_str, {
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
            "image_width": orig_width,
            "image_height": orig_height,
        }

    except Exception as e:
        if verbose:
            print(f"  Error analyzing {path.name}: {e}")
        return path_str, {"error": str(e)}
