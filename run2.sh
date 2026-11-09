#!/usr/bin/env bash
# Decode <basename>.satoutput into <basename>.metromap (SPEC.md move format).
# Exit status is the decoder's: 0 ok, 3 routes written but requirements
# violated, 1 bad input/solver output or no valid route recoverable, 2 usage.
set -euo pipefail
if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <basename without .city>" >&2
    exit 2
fi
if [[ ! -f "$1.city" ]]; then
    echo "Input not found: $1.city" >&2
    exit 1
fi
if [[ ! -f "$1.satoutput" ]]; then
    echo "Solver output not found: $1.satoutput (run the SAT solver on $1.satinput first)" >&2
    exit 1
fi
script_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ ! -x "$script_dir/decoder" ]]; then
    echo "Build the decoder first with ./compile.sh" >&2
    exit 1
fi
exec "$script_dir/decoder" "$1"
