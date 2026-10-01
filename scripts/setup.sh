#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
if ! .venv/bin/python -c 'import gmsh' >/dev/null 2>&1; then
    printf '\nInstalling Linux libraries required by the geometry builder. Ubuntu may ask for your sudo password.\n'
    sudo apt-get update
    sudo apt-get install -y libglu1-mesa libxft2 libxrender1
    .venv/bin/python -c 'import gmsh'
fi
npm --prefix frontend ci --no-audit --no-fund
printf '\nSetup complete. Start with: bash scripts/start.sh\n'
