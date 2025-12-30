#!/bin/bash
# Root wrapper - delegates to scripts/test.sh
exec "$(dirname "$0")/scripts/test.sh" "$@"
