#!/usr/bin/env bash
# =============================================================
# validate_headers.sh — Validate CSV headers before bronze load
# =============================================================
# Purpose: fail early with a clear message if a source CSV's
#          header row does not match the expected column list
#          recorded in expected_headers.txt. Catches schema
#          drift (added/removed/renamed columns) *before* the
#          COPY in bronze.load_bronze() attempts a load.
#
# Usage:
#     ./scripts/bronze/validate_headers.sh [DATASETS_DIR]
#
#     If DATASETS_DIR is omitted, it defaults to
#     <repo_root>/datasets (resolved relative to this script).
# =============================================================
set -euo pipefail

# Resolve the repository root (two levels up from this script).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default datasets directory.
DATASETS_DIR="${1:-$REPO_ROOT/datasets}"
MANIFEST="$SCRIPT_DIR/expected_headers.txt"

# ---- helpers -------------------------------------------------
die() {
    echo "ERROR: $*" >&2
    exit 1
}

# ---- sanity checks -------------------------------------------
if [[ ! -f "$MANIFEST" ]]; then
    die "Manifest file not found: $MANIFEST"
fi
if [[ ! -d "$DATASETS_DIR" ]]; then
    die "Datasets directory not found: $DATASETS_DIR"
fi

# ---- parse manifest & validate -------------------------------
# Reads expected_headers.txt, which is INI-like with a
# "[section]" header per source folder followed by lines of the
# form: filename.csv|col1,col2,col3
current_section=""
errors=0

while IFS= read -r line || [[ -n "$line" ]]; do
    # strip leading/trailing whitespace
    line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

    # skip blank lines and comments
    [[ -z "$line" ]] && continue
    [[ "$line" == \#* ]] && continue

    # detect [section]
    if [[ "$line" =~ ^\[(.+)\]$ ]]; then
        current_section="${BASH_REMATCH[1]}"
        continue
    fi

    # parse filename|columns
    if [[ "$line" == *"|"* ]]; then
        filename="${line%%|*}"
        expected="${line#*|}"
    else
        echo "WARN: malformed manifest line (no '|'): $line" >&2
        continue
    fi

    file_path="$DATASETS_DIR/$current_section/$filename"

    if [[ ! -f "$file_path" ]]; then
        echo "ERROR: source file not found: $file_path" >&2
        errors=$((errors + 1))
        continue
    fi

    # grab the actual header (first line) and strip the trailing newline
    actual="$(head -n 1 "$file_path" | tr -d '\r\n')"
    # normalize expected (strip any surrounding whitespace)
    expected="$(echo "$expected" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"

    if [[ "$actual" != "$expected" ]]; then
        echo "ERROR: header mismatch in $file_path" >&2
        echo "       expected: $expected" >&2
        echo "       actual:   $actual" >&2
        errors=$((errors + 1))
    else
        echo "OK:      $file_path"
    fi
done < "$MANIFEST"

# ---- summary --------------------------------------------------
if [[ $errors -gt 0 ]]; then
    echo ""
    echo "FAILED: $errors header validation error(s). Fix source files or manifest."
    exit 1
fi

echo ""
echo "SUCCESS: all CSV headers validated."
