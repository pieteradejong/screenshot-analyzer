#!/bin/bash
# Root wrapper - delegates to scripts/init.sh
exec "$(dirname "$0")/scripts/init.sh" "$@"
