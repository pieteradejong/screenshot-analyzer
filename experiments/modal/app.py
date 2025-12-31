"""
Modal Cloud App for Screenshot Analysis.

GPU-accelerated OCR processing with fire-and-forget execution.
Processes images from a Modal Volume and POSTs results to a webhook.

Deploy with: modal deploy app.py
"""

import io
import json
import re
import time
from datetime import datetime
from pathlib import Path

import modal

# =============================================================================
# MODAL APP CONFIGURATION
# =============================================================================

app = modal.App("screenshot-analyzer")

# Persistent volume for images and results
volume = modal.Volume.from_name("screenshot-analyzer-data", create_if_missing=True)
VOLUME_PATH = "/data"

# Container image with all dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgl1-mesa-glx", "libglib2.0-0")  # OpenCV deps
    .pip_install(
        "easyocr>=1.7.0",
        "pillow>=10.0.0",
        "torch>=2.0.0",
        "torchvision>=0.15.0",
        "requests>=2.31.0",
    )
)

# =============================================================================
# OCR PROCESSING (standalone, copied from src/backends/ocr.py)
# =============================================================================

MAX_DIMENSION = 1200
MIN_SCALE = 0.5


def prepare_image_for_ocr(path: Path) -> tuple[bytes, int, int]:
    """Load and resize image for OCR."""
    from PIL import Image

    with Image.open(path) as img:
        orig_width, orig_height = img.size

        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")

        max_dim = max(orig_width, orig_height)
        if max_dim > MAX_DIMENSION:
            scale = max(MAX_DIMENSION / max_dim, MIN_SCALE)
            new_width = int(orig_width * scale)
            new_height = int(orig_height * scale)
            img = img.resize((new_width, new_height), Image.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=80)
        return buffer.getvalue(), orig_width, orig_height


# App/content patterns (simplified from src/backends/ocr.py)
APP_PATTERNS = {
    "twitter": [r"\bretweet\b", r"\btweet\b", r"@\w+.*\d+[hm]\b"],
    "instagram": [r"\blikes?\b", r"\bfollowers?\b", r"\binstagram\b"],
    "slack": [r"\bslack\b", r"#[a-z0-9_-]+", r"\bthread\b"],
    "discord": [r"\bdiscord\b", r"\bserver\b.*\bmembers?\b"],
    "terminal": [r"\$\s+\w+", r"\bcommand not found\b"],
    "browser": [r"https?://", r"\bbookmarks?\b"],
}

CONTENT_PATTERNS = {
    "code": [r"\bdef\s+\w+\s*\(", r"\bclass\s+\w+", r"\bimport\s+\w+"],
    "receipt": [r"\$\d+\.\d{2}", r"\btotal\b", r"\bsubtotal\b"],
    "conversation": [r"\d{1,2}:\d{2}\s*(am|pm)?", r"\bsent\b", r"\bdelivered\b"],
    "error_message": [r"\berror\b", r"\bfailed\b", r"\bexception\b"],
    "social_post": [r"\blikes?\b", r"\bcomments?\b", r"\bshares?\b"],
}


def classify_text(text: str, patterns: dict) -> tuple[str, float]:
    """Classify text against pattern dictionary."""
    text_lower = text.lower()
    scores = {}

    for category, pattern_list in patterns.items():
        score = sum(len(re.findall(p, text_lower, re.IGNORECASE)) for p in pattern_list)
        if score > 0:
            scores[category] = score

    if not scores:
        return "unknown", 0.3

    best = max(scores, key=scores.get)
    confidence = min(scores[best] / 5.0, 1.0)
    return best, round(confidence, 2)


def extract_mentions(text: str) -> list[str]:
    """Extract @mentions from text."""
    return list(set(re.findall(r"@(\w+)", text)))[:10]


def analyze_image(path: Path, reader) -> dict:
    """Analyze a single image with OCR."""
    try:
        image_bytes, width, height = prepare_image_for_ocr(path)
        results = reader.readtext(image_bytes)
        full_text = " ".join([r[1] for r in results])
        has_text = len(full_text.strip()) > 0

        source_app, app_conf = classify_text(full_text, APP_PATTERNS)
        content_type, type_conf = classify_text(full_text, CONTENT_PATTERNS)

        return {
            "filename": path.name,
            "filepath": str(path),
            "source_app": source_app,
            "content_type": content_type,
            "has_text": has_text,
            "primary_text": full_text[:500] if full_text else None,
            "people_mentioned": extract_mentions(full_text),
            "confidence": round((app_conf + type_conf) / 2, 2),
            "image_width": width,
            "image_height": height,
            "error": None,
        }
    except Exception as e:
        return {
            "filename": path.name,
            "filepath": str(path),
            "error": str(e),
        }


# =============================================================================
# MODAL FUNCTIONS
# =============================================================================


@app.function(
    image=image,
    gpu="T4",
    timeout=600,
    volumes={VOLUME_PATH: volume},
)
def process_batch(image_paths: list[str], batch_id: int, total_batches: int) -> list[dict]:
    """
    Process a batch of images on GPU.

    Each worker initializes its own EasyOCR reader.
    """
    import easyocr
    import os

    worker_id = os.getpid()
    print(f"[worker-{worker_id}] Starting batch {batch_id}/{total_batches} ({len(image_paths)} images)")

    # Initialize OCR reader (cached after first call)
    start_init = time.time()
    reader = easyocr.Reader(["en"], gpu=True, verbose=False)
    init_time = time.time() - start_init
    print(f"[worker-{worker_id}] ✓ EasyOCR initialized ({init_time:.1f}s)")

    results = []
    for i, path_str in enumerate(image_paths):
        path = Path(path_str)
        result = analyze_image(path, reader)
        results.append(result)

        if (i + 1) % 10 == 0:
            print(f"[worker-{worker_id}] Batch {batch_id}: {i + 1}/{len(image_paths)} images processed")

    print(f"[worker-{worker_id}] ✓ Batch {batch_id} complete ({len(results)} images)")
    return results


@app.function(
    image=image,
    timeout=1800,  # 30 min max
    volumes={VOLUME_PATH: volume},
)
def run_analysis(
    job_id: str,
    callback_url: str | None = None,
    batch_size: int = 50,
    dry_run: bool = False,
) -> dict:
    """
    Main orchestrator function.

    Discovers images in volume, fans out to GPU workers, collects results,
    saves to volume, and POSTs to callback URL.
    """
    import requests

    print(f"[main] Starting job {job_id}")
    print(f"[main] Callback URL: {callback_url or 'none'}")
    print(f"[main] Dry run: {dry_run}")

    start_time = time.time()

    # Discover images in volume
    images_dir = Path(VOLUME_PATH) / "images" / job_id
    if not images_dir.exists():
        return {"error": f"Images directory not found: {images_dir}"}

    supported_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    image_paths = [
        str(p) for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in supported_ext
    ]

    print(f"[main] Found {len(image_paths)} images")

    if dry_run:
        # Cloud dry run - just validate setup
        print("[main] Dry run mode - skipping GPU processing")
        result = {
            "job_id": job_id,
            "status": "dry_run",
            "images_found": len(image_paths),
            "would_process": len(image_paths),
            "estimated_time_sec": len(image_paths) * 0.02,
            "estimated_cost_usd": len(image_paths) * 0.000004,
        }

        if callback_url:
            print(f"[main] Testing callback to {callback_url}")
            try:
                resp = requests.post(callback_url, json=result, timeout=10)
                print(f"[main] ✓ Callback test: {resp.status_code}")
                result["callback_test"] = "success"
            except Exception as e:
                print(f"[main] ✗ Callback test failed: {e}")
                result["callback_test"] = f"failed: {e}"

        return result

    # Create batches
    batches = [
        image_paths[i:i + batch_size]
        for i in range(0, len(image_paths), batch_size)
    ]
    total_batches = len(batches)
    print(f"[main] Created {total_batches} batches of ~{batch_size} images each")

    # Fan out to GPU workers
    print("[main] Dispatching to GPU workers...")
    all_results = []
    errors = 0

    # Process batches in parallel using Modal's map
    batch_args = [
        (batch, i + 1, total_batches)
        for i, batch in enumerate(batches)
    ]

    for batch_results in process_batch.starmap(batch_args):
        all_results.extend(batch_results)
        batch_errors = sum(1 for r in batch_results if r.get("error"))
        errors += batch_errors

        processed = len(all_results)
        elapsed = time.time() - start_time
        remaining = (len(image_paths) - processed) * (elapsed / processed) if processed > 0 else 0
        print(f"[main] Progress: {processed}/{len(image_paths)} ({100*processed//len(image_paths)}%) | {elapsed:.1f}s elapsed | ~{remaining:.0f}s remaining")

    duration = time.time() - start_time
    print(f"[main] ✓ All batches complete ({duration:.1f}s)")

    # Save results to volume
    results_dir = Path(VOLUME_PATH) / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_file = results_dir / f"{job_id}.json"

    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2)

    volume.commit()
    print(f"[main] ✓ Results saved to {results_file}")

    # Prepare response
    response = {
        "job_id": job_id,
        "status": "complete",
        "processed": len(all_results),
        "errors": errors,
        "duration_sec": round(duration, 1),
        "results_path": str(results_file),
        "log_url": f"https://modal.com/apps/screenshot-analyzer/logs",
    }

    # POST to callback
    if callback_url:
        print(f"[main] Sending callback to {callback_url}")
        try:
            resp = requests.post(callback_url, json=response, timeout=30)
            print(f"[main] ✓ Callback sent ({resp.status_code})")
        except Exception as e:
            print(f"[main] ✗ Callback failed: {e}")
            response["callback_error"] = str(e)

    return response


@app.function(
    image=image,
    timeout=60,
    volumes={VOLUME_PATH: volume},
)
def list_jobs() -> list[dict]:
    """List all jobs and their status."""
    results_dir = Path(VOLUME_PATH) / "results"
    if not results_dir.exists():
        return []

    jobs = []
    for f in results_dir.glob("*.json"):
        with open(f) as fp:
            data = json.load(fp)
        jobs.append({
            "job_id": f.stem,
            "processed": len(data),
            "errors": sum(1 for r in data if r.get("error")),
        })

    return jobs


@app.function(
    image=image,
    timeout=60,
    volumes={VOLUME_PATH: volume},
)
def get_results(job_id: str) -> list[dict]:
    """Get results for a specific job."""
    results_file = Path(VOLUME_PATH) / "results" / f"{job_id}.json"
    if not results_file.exists():
        return []

    with open(results_file) as f:
        return json.load(f)


# =============================================================================
# LOCAL ENTRYPOINT (for testing)
# =============================================================================


@app.local_entrypoint()
def main():
    """Test the app locally."""
    print("Screenshot Analyzer Modal App")
    print("Deploy with: modal deploy app.py")
    print("Trigger with: python trigger.py /path/to/images --callback URL")
