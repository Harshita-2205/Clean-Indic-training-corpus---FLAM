#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then echo "Usage: ./run.sh <raw_dir> <out_dir>" >&2; exit 2; fi
ROOT="$(cd "$(dirname "$0")" && pwd)"
python3 "$ROOT/src/pipeline.py" "$1" "$2"
