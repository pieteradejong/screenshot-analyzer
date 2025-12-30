#!/bin/bash
# Root wrapper - delegates to scripts/run.sh
exec "$(dirname "$0")/scripts/run.sh" "$@"
