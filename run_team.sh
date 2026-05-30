#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p data logs artifacts
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ "${HERMES_TMUX_AUTOSTART:-1}" == "1" ]]; then
  "${PYTHON_BIN}" scripts/start_hermes_tmux_agents.py
fi
exec "${PYTHON_BIN}" ai_team_b2b_service.py
