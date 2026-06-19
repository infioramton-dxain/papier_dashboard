#!/usr/bin/env bash
# Signal Terminal launcher — activates .venv and runs Streamlit on port 8520.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -d .venv ]]; then
  echo "✗ .venv not found. Run \`uv sync\` first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

exec streamlit run app.py \
  --server.port 8520 \
  --server.address 0.0.0.0 \
  --browser.gatherUsageStats false
