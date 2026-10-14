#!/usr/bin/env bash
# ./run.sh [DIR]            analyse screenshots in DIR ($SCREENSHOT_DIR or ~/screenshots) -> HTML report
# ./run.sh DIR --dry-run    count images without processing
# ./run.sh test [...]       every check (./test.sh)
# Thin root wrapper; the implementation is scripts/run.sh. Run ./init.sh once first.
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in
  -h|--help|help) sed -n '2,5p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  test)           shift; exec ./test.sh "$@" ;;
esac
exec ./scripts/run.sh "$@"
