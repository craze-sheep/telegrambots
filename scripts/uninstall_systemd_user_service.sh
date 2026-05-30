#!/usr/bin/env bash
set -euo pipefail

SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="telegram-ai-team-bot2bot.service"
SERVICE_FILE="${SERVICE_DIR}/${SERVICE_NAME}"

systemctl --user stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl --user disable "${SERVICE_NAME}" 2>/dev/null || true

if [[ -f "${SERVICE_FILE}" ]]; then
  rm -f "${SERVICE_FILE}"
fi

systemctl --user daemon-reload

echo "Uninstalled user service: ${SERVICE_NAME}"
echo "Hermes tmux sessions are not stopped automatically."
echo "Stop them with: python3 scripts/stop_hermes_tmux_agents.py"
