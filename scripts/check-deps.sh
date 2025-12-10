#!/bin/bash
# Check for Python dependency conflicts
#
# Usage: check-deps.sh <CONDA_ENV>
#
# Example: check-deps.sh sightline-build

set -e

CONDA_ENV="$1"

if [ -z "$CONDA_ENV" ]; then
    echo "Error: Missing required argument"
    echo "Usage: check-deps.sh <CONDA_ENV>"
    exit 1
fi

CONDA_RUN="conda run -n $CONDA_ENV"

echo "→ Checking for dependency conflicts..."
echo ""
echo "Step 1: Installing/upgrading pipdeptree..."
$CONDA_RUN pip install --quiet --upgrade pipdeptree || true
echo ""
echo "Step 2: Running pip check (finds broken dependencies)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if $CONDA_RUN pip check 2>&1 | grep -qE "(has requirement|but you have)"; then
    echo "⚠ CONFLICTS DETECTED:"
    $CONDA_RUN pip check
    echo ""
    echo "The above packages have dependency conflicts!"
else
    $CONDA_RUN pip check 2>&1 || true
    echo "✓ No broken dependencies found by pip check"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Step 3: Dependency tree (inspect for duplicate/conflicting versions)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$CONDA_RUN pipdeptree
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Step 4: Reverse dependency tree (what depends on each package)..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
$CONDA_RUN pipdeptree --reverse
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✓ Dependency check complete!"
echo ""
echo "Tips for identifying conflicts:"
echo "  • Look for packages listed multiple times with different versions"
echo "  • Check pip check output above for explicit conflict warnings"
echo "  • Review the reverse tree to see what depends on conflicting packages"
