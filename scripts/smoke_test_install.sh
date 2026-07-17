#!/usr/bin/env bash
# Installs a built agent-inspector wheel into a clean venv and smoke-tests
# that the CLI entry point actually resolves and its argument parsing
# works end-to-end post-install -- without needing a live LLM/Ollama
# backend or a real agent script to point it at.
#
# Usage: scripts/smoke_test_install.sh <path-to-wheel>

set -euo pipefail

wheel="${1:?Usage: $0 <path-to-wheel>}"

if [[ ! -f "$wheel" ]]; then
  echo "error: wheel not found at '$wheel'" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
venv_dir="$tmpdir/venv"

python3 -m venv "$venv_dir"
"$venv_dir/bin/pip" install --quiet "$wheel"

echo "--- agent-inspector --help ---"
"$venv_dir/bin/agent-inspector" --help

echo "--- agent-inspector launch --help ---"
"$venv_dir/bin/agent-inspector" launch --help

echo "OK: agent-inspector CLI installed from $wheel and resolves both --help invocations."
