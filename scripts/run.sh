#!/bin/bash
# =============================================================================
# Run Screenshot Analyzer
# =============================================================================
# Analyzes screenshots and generates an HTML report.
#
# Usage:
#   ./run.sh                    # Use default directory ($SCREENSHOT_DIR or ~/Pictures)
#   ./run.sh /path/to/images    # Analyze specific directory
#   ./run.sh --dry-run          # Count images without processing
#   ./run.sh --help             # Show analyzer help
# =============================================================================

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
cd "$PROJECT_ROOT"

# =============================================================================
# CONFIGURATION
# =============================================================================

# Default directory: SCREENSHOT_DIR env var, or ~/screenshots
DEFAULT_DIR="${SCREENSHOT_DIR:-$HOME/screenshots}"

# =============================================================================
# SETUP
# =============================================================================

# Setup venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo "Installing dependencies (this may take a few minutes for PyTorch)..."
    .venv/bin/pip install -r requirements.txt
fi

# =============================================================================
# ARGUMENT HANDLING
# =============================================================================

# Check if first arg is a directory or a flag
if [ $# -eq 0 ]; then
    # No arguments - use default directory
    DIR="$DEFAULT_DIR"
    EXTRA_ARGS=""
elif [ -d "$1" ]; then
    # First arg is a directory
    DIR="$1"
    shift
    EXTRA_ARGS="$@"
elif [[ "$1" == -* ]]; then
    # First arg is a flag - use default directory
    DIR="$DEFAULT_DIR"
    EXTRA_ARGS="$@"
else
    # First arg is not a directory and not a flag - pass through (will error)
    DIR="$1"
    shift
    EXTRA_ARGS="$@"
fi

echo "=== Screenshot Analyzer ==="
echo "Directory: $DIR"
echo ""

# =============================================================================
# RUN ANALYZER
# =============================================================================

.venv/bin/python src/analyzer.py "$DIR" $EXTRA_ARGS

# =============================================================================
# OPEN REPORT (if generated)
# =============================================================================

# Determine output directory
if [[ "$EXTRA_ARGS" == *"--output"* ]]; then
    # Custom output - don't auto-open (user knows what they're doing)
    :
else
    REPORT_PATH="$DIR/_analysis/report.html"
    if [ -f "$REPORT_PATH" ]; then
        echo ""
        echo "Opening report in browser..."
        # macOS
        if command -v open &> /dev/null; then
            open "$REPORT_PATH"
        # Linux
        elif command -v xdg-open &> /dev/null; then
            xdg-open "$REPORT_PATH"
        else
            echo "Report: file://$REPORT_PATH"
        fi
    fi
fi
