#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <basename without .city>" >&2
    exit 2
fi
if [[ ! -f "$1.city" ]]; then
    echo "Input not found: $1.city" >&2
    exit 1
fi
script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ ! -x "$script_dir/encoder" ]]; then
    echo "Build the encoder first with ./compile.sh" >&2
    exit 1
fi
exec "$script_dir/encoder" "$1"
