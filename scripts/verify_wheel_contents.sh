#!/usr/bin/env bash
# Verifies a built agent-inspector wheel actually bundles the frontend.
#
# hatch_build.py's custom build hook fails *open*: if npm isn't on PATH
# it prints a warning and returns successfully rather than failing the
# build, which could silently produce (and even publish) a wheel with a
# working API and no UI. This script unzips a built wheel and asserts
# the bundled frontend assets are actually present, so both the PR
# packaging check and the real release job catch that failure mode
# loudly instead of it only being discovered after users try to run it.
#
# Usage: scripts/verify_wheel_contents.sh <path-to-wheel>

set -euo pipefail

wheel="${1:?Usage: $0 <path-to-wheel>}"

if [[ ! -f "$wheel" ]]; then
  echo "error: wheel not found at '$wheel'" >&2
  exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

unzip -q "$wheel" -d "$workdir"

index_html="$workdir/agent_inspector/web/index.html"
assets_dir="$workdir/agent_inspector/web/assets"

if [[ ! -f "$index_html" ]]; then
  echo "error: $wheel does not contain agent_inspector/web/index.html -- the frontend build did not get bundled into this wheel (see hatch_build.py)." >&2
  exit 1
fi

if [[ ! -d "$assets_dir" ]] || [[ -z "$(find "$assets_dir" -type f -print -quit)" ]]; then
  echo "error: $wheel's agent_inspector/web/assets/ directory is missing or empty -- the frontend build did not get bundled into this wheel (see hatch_build.py)." >&2
  exit 1
fi

asset_count="$(find "$assets_dir" -type f | wc -l | tr -d ' ')"
echo "OK: $wheel bundles a built frontend (agent_inspector/web/index.html + ${asset_count} asset file(s))."
