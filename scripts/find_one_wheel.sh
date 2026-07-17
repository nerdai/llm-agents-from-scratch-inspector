#!/usr/bin/env bash
# Prints the path to the single wheel under dist/, or fails loudly with
# a clear message if there isn't exactly one.
#
# `find dist -name '*.whl'` alone is ambiguous if dist/ ever ends up
# with zero wheels (a build failure that didn't error, or a stale/
# cleaned-up dist/) or more than one (a stale artifact left over from
# a previous local build, or a future build-config change that starts
# producing more than one wheel) -- either way the bare `find` becomes
# an empty or newline-delimited string, and whatever consumes it fails
# downstream in a confusing way instead of here, clearly.
#
# Usage: wheel="$(scripts/find_one_wheel.sh)"

set -euo pipefail

mapfile -t wheels < <(find dist -maxdepth 1 -name '*.whl')

if [[ ${#wheels[@]} -eq 0 ]]; then
  echo "error: no wheel found in dist/ (expected exactly one from 'uv build')." >&2
  exit 1
fi

if [[ ${#wheels[@]} -gt 1 ]]; then
  echo "error: expected exactly one wheel in dist/, found ${#wheels[@]}: ${wheels[*]}" >&2
  exit 1
fi

echo "${wheels[0]}"
