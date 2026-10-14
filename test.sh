#!/usr/bin/env bash
# Every check for this repo: pytest, ruff lint, format check, type check. Exit 0 = green.
# Thin root wrapper; the implementation is scripts/test.sh (modes: all | backend | lint | format | type-check; --quick).
set -euo pipefail
cd "$(dirname "$0")"
case "${1:-}" in -h|--help) sed -n '2,3p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;; esac
exec ./scripts/test.sh "$@"
