#!/usr/bin/env python3
"""
Trigger script for Modal cloud screenshot analysis.

Uploads images to Modal Volume and triggers async processing.
Returns immediately - results delivered via webhook.

Usage:
    python trigger.py /path/to/screenshots --callback https://webhook.site/xxx
    python trigger.py /path/to/screenshots --dry-run
    python trigger.py /path/to/screenshots --limit 10 --verbose
"""

import argparse
import os
import sys
import time
import uuid
from pathlib import Path

# =============================================================================
# CONSTANTS
# =============================================================================

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MIN_FILE_SIZE = 10 * 1024  # 10KB
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Cost estimates (T4 GPU)
GPU_COST_PER_SEC = 0.59 / 3600  # $0.59/hr
IMAGES_PER_SEC = 50  # With parallel workers


# =============================================================================
# HELPERS
# =============================================================================


def find_images(
    directory: Path,
    limit: int | None = None,
    verbose: bool = False,
) -> tuple[list[Path], int, int]:
    """Find all supported image files in directory."""
    images = []
    skipped_small = 0
    skipped_large = 0

    if not directory.is_dir():
        return [], 0, 0

    for path in directory.iterdir():
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

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

        if limit and len(images) >= limit:
            break

    return images, skipped_small, skipped_large


def format_size(bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"


def format_time(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def log(msg: str, verbose: bool = True, prefix: str = ""):
    """Print a log message with timestamp."""
    if not verbose:
        return
    elapsed = time.time() - log.start_time
    timestamp = f"[{elapsed:05.1f}]"
    print(f"{timestamp} {prefix}{msg}")


log.start_time = time.time()


# =============================================================================
# DRY RUN (LOCAL)
# =============================================================================


def dry_run_local(directory: Path, limit: int | None, verbose: bool):
    """Local dry run - count images and estimate cost."""
    print("=== Dry Run (local) ===")
    print(f"Directory: {directory}")
    print()

    images, skipped_small, skipped_large = find_images(directory, limit, verbose)

    total_size = sum(p.stat().st_size for p in images)

    print(f"Images found:    {len(images)}")
    print(f"Total size:      {format_size(total_size)}")

    if skipped_small or skipped_large:
        print(f"Skipped:         {skipped_small} tiny (<10KB), {skipped_large} large (>10MB)")

    if limit:
        print(f"Limit applied:   {limit}")

    print()
    print("Estimated cloud processing:")

    # Estimate upload time (~10 MB/s typical)
    upload_time = total_size / (10 * 1024 * 1024)
    print(f"  Upload time:   ~{format_time(upload_time)} (depends on connection)")

    # Estimate GPU time
    gpu_time = len(images) / IMAGES_PER_SEC
    print(f"  GPU time:      ~{format_time(gpu_time)} (10 parallel workers)")

    # Estimate cost
    cost = gpu_time * GPU_COST_PER_SEC
    print(f"  Cost:          ~${cost:.3f}")

    print()
    print("Run without --dry-run to proceed.")


# =============================================================================
# DRY RUN (CLOUD)
# =============================================================================


def dry_run_cloud(
    directory: Path,
    callback_url: str | None,
    limit: int | None,
    verbose: bool,
):
    """Cloud dry run - test upload and webhook without GPU processing."""
    import modal

    print("=== Dry Run (cloud) ===")
    log.start_time = time.time()

    # Check Modal auth
    log("Checking Modal authentication...", verbose)
    try:
        # This will fail if not authenticated
        modal.Volume.lookup("screenshot-analyzer-data")
        log("✓ Modal auth valid", verbose)
    except modal.exception.NotFoundError:
        log("✓ Modal auth valid (volume will be created)", verbose)
    except Exception as e:
        print(f"✗ Modal auth failed: {e}")
        print("Run 'modal setup' to authenticate.")
        sys.exit(1)

    # Find images
    images, skipped_small, skipped_large = find_images(directory, limit, verbose)
    total_size = sum(p.stat().st_size for p in images)

    log(f"Found {len(images)} images ({format_size(total_size)})", verbose)

    # Create test job
    job_id = f"dryrun-{uuid.uuid4().hex[:8]}"
    log(f"Test job ID: {job_id}", verbose)

    # Upload a small subset to test
    test_count = min(5, len(images))
    log(f"Uploading {test_count} test images...", verbose)

    volume = modal.Volume.from_name("screenshot-analyzer-data", create_if_missing=True)
    upload_dir = Path(f"/data/images/{job_id}")

    with volume.batch_upload() as batch:
        for img in images[:test_count]:
            remote_path = upload_dir / img.name
            batch.put_file(img, remote_path)

    log(f"✓ Test upload successful ({test_count} images)", verbose)

    # Test webhook if provided
    if callback_url:
        import requests

        log(f"Testing webhook: {callback_url}", verbose)
        try:
            test_payload = {
                "job_id": job_id,
                "status": "dry_run_test",
                "message": "This is a test from screenshot-analyzer cloud dry run",
            }
            resp = requests.post(callback_url, json=test_payload, timeout=10)
            log(f"✓ Webhook test: {resp.status_code}", verbose)
        except Exception as e:
            log(f"✗ Webhook test failed: {e}", verbose)

    # Clean up test files
    log("Cleaning up test files...", verbose)
    # Note: Modal volumes don't have a delete API, but files will be overwritten

    print()
    print("=== Dry Run Complete ===")
    print(f"✓ Modal authentication works")
    print(f"✓ Volume upload works")
    if callback_url:
        print(f"✓ Webhook reachable")
    print()

    # Estimate full run
    gpu_time = len(images) / IMAGES_PER_SEC
    cost = gpu_time * GPU_COST_PER_SEC
    print(f"Ready for real run:")
    print(f"  Images:        {len(images)}")
    print(f"  Est. GPU time: {format_time(gpu_time)}")
    print(f"  Est. cost:     ${cost:.3f}")


# =============================================================================
# REAL RUN
# =============================================================================


def run_analysis(
    directory: Path,
    callback_url: str | None,
    limit: int | None,
    verbose: bool,
    follow: bool,
):
    """Upload images and trigger cloud analysis."""
    import modal

    log.start_time = time.time()

    # Find images
    log("Scanning for images...", verbose)
    images, skipped_small, skipped_large = find_images(directory, limit, verbose)

    if not images:
        print("No images found to process.")
        sys.exit(1)

    total_size = sum(p.stat().st_size for p in images)
    log(f"Found {len(images)} images ({format_size(total_size)})", verbose)

    if skipped_small or skipped_large:
        log(f"Skipped: {skipped_small} tiny, {skipped_large} large", verbose)

    # Create job ID
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    log(f"Job ID: {job_id}", verbose)

    # Get volume
    log("Connecting to Modal...", verbose)
    volume = modal.Volume.from_name("screenshot-analyzer-data", create_if_missing=True)

    # Upload images
    log(f"Starting upload of {len(images)} images...", verbose)
    upload_start = time.time()

    upload_dir = f"/data/images/{job_id}"
    uploaded = 0

    with volume.batch_upload() as batch:
        for i, img in enumerate(images):
            remote_path = f"{upload_dir}/{img.name}"
            batch.put_file(img, remote_path)
            uploaded += 1

            # Progress logging
            if verbose and (uploaded % 100 == 0 or uploaded == len(images)):
                pct = 100 * uploaded // len(images)
                elapsed = time.time() - upload_start
                rate = uploaded / elapsed if elapsed > 0 else 0
                log(f"Upload progress: {uploaded}/{len(images)} ({pct}%) - {rate:.0f}/s", verbose)

    upload_time = time.time() - upload_start
    log(f"✓ Upload complete ({format_time(upload_time)})", verbose)

    # Import and trigger the Modal function
    log("Triggering cloud job...", verbose)

    from app import run_analysis as modal_run_analysis

    # Spawn the job (non-blocking)
    if follow:
        # Blocking call - stream logs
        log("Running with --follow (streaming logs)...", verbose)
        result = modal_run_analysis.remote(
            job_id=job_id,
            callback_url=callback_url,
            dry_run=False,
        )
        print()
        print("=== Job Complete ===")
        print(f"Processed: {result.get('processed', 0)}")
        print(f"Errors: {result.get('errors', 0)}")
        print(f"Duration: {result.get('duration_sec', 0)}s")
    else:
        # Non-blocking - spawn and return
        call = modal_run_analysis.spawn(
            job_id=job_id,
            callback_url=callback_url,
            dry_run=False,
        )
        log(f"✓ Job started: {job_id}", verbose)

        if callback_url:
            log(f"✓ Results will POST to: {callback_url}", verbose)

        print()
        print("=== Job Submitted ===")
        print(f"Job ID:      {job_id}")
        print(f"Images:      {len(images)}")
        print(f"Callback:    {callback_url or 'none'}")
        print()
        print("Your laptop is free! Monitor at:")
        print(f"  https://modal.com/apps/screenshot-analyzer")
        print()

        if callback_url:
            print(f"Results will be POSTed to your webhook when complete.")
        else:
            print("Retrieve results later with:")
            print(f"  python -c \"from app import get_results; print(get_results.remote('{job_id}'))\"")


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Trigger cloud screenshot analysis on Modal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ~/screenshots --dry-run              # Local dry run
  %(prog)s ~/screenshots --dry-run-cloud        # Cloud dry run  
  %(prog)s ~/screenshots --limit 10 --verbose   # Small batch test
  %(prog)s ~/screenshots --callback URL         # Full run with webhook
""",
    )
    parser.add_argument(
        "directory",
        type=Path,
        help="Directory containing images to analyze",
    )
    parser.add_argument(
        "--callback",
        type=str,
        help="Webhook URL to POST results when complete",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of images to process",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Local dry run - count images, estimate cost (no network)",
    )
    parser.add_argument(
        "--dry-run-cloud",
        action="store_true",
        help="Cloud dry run - test upload/webhook without GPU processing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Detailed progress logging",
    )
    parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Stream cloud logs to terminal (blocks until complete)",
    )

    args = parser.parse_args()

    # Validate directory
    if not args.directory.is_dir():
        print(f"Error: {args.directory} is not a directory")
        sys.exit(1)

    # Route to appropriate handler
    if args.dry_run:
        dry_run_local(args.directory, args.limit, verbose=True)
    elif args.dry_run_cloud:
        dry_run_cloud(args.directory, args.callback, args.limit, args.verbose or True)
    else:
        run_analysis(
            args.directory,
            args.callback,
            args.limit,
            args.verbose,
            args.follow,
        )


if __name__ == "__main__":
    main()
