#!/usr/bin/env bash
# Everything needed to work on screenshot-analyzer: .venv with OCR/VLM deps, config. Idempotent.
# Thin root wrapper; the implementation is scripts/init.sh (see `scripts/init.sh --help`: --clean, --no-clean).
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in -h|--help) sed -n '2,3p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
exec ./scripts/init.sh "$@"
