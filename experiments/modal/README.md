# Modal Cloud Deployment (Experimental)

Run screenshot analysis on Modal's GPU cloud with fire-and-forget execution and webhook callbacks.

## Why Modal?

- **Faster**: NVIDIA T4 GPU runs OCR ~2x faster than Apple MPS
- **Parallel**: Spin up 10+ GPU containers simultaneously  
- **Fire-and-forget**: Your laptop is free in ~2 seconds
- **Cheap**: ~$0.02 for 5,000 images (free tier: $30/month)

## Setup

```bash
# Install Modal CLI
pip install -r requirements.txt

# Authenticate (opens browser)
modal setup

# Deploy the app to Modal
modal deploy app.py
```

## Usage

### 1. Local Dry Run (no cost)

Count images and estimate cost without any network calls:

```bash
python trigger.py ~/screenshots --dry-run
```

### 2. Cloud Dry Run (no GPU cost)

Test upload, webhook connectivity, and auth without GPU processing:

```bash
python trigger.py ~/screenshots --dry-run-cloud --callback https://webhook.site/xxx
```

### 3. Small Batch Test (~$0.001)

Process 10 images to validate the full pipeline:

```bash
python trigger.py ~/screenshots --limit 10 --callback https://webhook.site/xxx --verbose
```

### 4. Full Run

Process all images with fire-and-forget execution:

```bash
python trigger.py ~/screenshots --callback https://webhook.site/xxx --verbose
```

## CLI Options

| Flag | Description |
|------|-------------|
| `--dry-run` | Local dry run - count images, estimate cost |
| `--dry-run-cloud` | Cloud dry run - test upload/webhook, no GPU |
| `--limit N` | Process only first N images |
| `--callback URL` | Webhook URL to POST results when complete |
| `--verbose` | Detailed progress logging |
| `--follow` | Stream cloud worker logs to terminal |

## Webhook Payload

When the job completes, your callback URL receives:

```json
{
  "job_id": "job_abc123",
  "status": "complete",
  "processed": 5000,
  "errors": 3,
  "duration_sec": 58.2,
  "results_url": "https://modal.run/download/abc123/results.json",
  "log_url": "https://modal.com/logs/job_abc123"
}
```

## Cost Estimate

| Images | GPU Time | Cost |
|--------|----------|------|
| 100 | ~2 sec | < $0.01 |
| 1,000 | ~12 sec | < $0.01 |
| 5,000 | ~60 sec | ~$0.02 |
| 10,000 | ~120 sec | ~$0.04 |

Modal free tier includes $30/month - enough for ~75,000 images.

## Architecture

```
Your Laptop                    Modal Cloud
    │                              │
    ├── trigger.py ────────────────┤
    │   Upload images to Volume    │
    │   Trigger async job          │
    │   Return immediately         │
    │                              │
    │                    ┌─────────┴─────────┐
    │                    │      app.py       │
    │                    │  ┌─────┬─────┐    │
    │                    │  │GPU-0│GPU-1│... │
    │                    │  │OCR  │OCR  │    │
    │                    │  └─────┴─────┘    │
    │                    │                   │
    │                    │  Collect results  │
    │                    │  POST to webhook  │
    │                    └───────────────────┘
    │
Webhook ◄─────────────────── Results JSON
```
