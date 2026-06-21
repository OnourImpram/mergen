#!/usr/bin/env bash
# Thin shim: delegates all logic to feature_ops.py.
# Accepted flags (unchanged): --json, --help / -h
SCRIPT_DIR="$(CDPATH="" cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/../feature_ops.py" setup-plan "$@"
