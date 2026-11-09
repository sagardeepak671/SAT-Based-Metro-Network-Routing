#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ "${CLEAN:-0}" != 0 ]]; then
    make clean
fi
if [[ "${DEBUG:-0}" != 0 ]]; then
    make -B encoder decoder CXXFLAGS="-std=c++11 -O0 -g -Wall -Wextra -fno-omit-frame-pointer -fsanitize=address,undefined"
else
    make -B encoder decoder
fi
