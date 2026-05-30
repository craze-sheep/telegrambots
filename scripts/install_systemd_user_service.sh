#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_NAME="telegram-ai-team-bot2bot.service"
SERVICE_FILE="${SERVICE_DIR}/${SERVICE_NAME}"
PYTHON_BIN="$(command -v python3)"
HERMES_BIN="$(command -v hermes || true)"

mkdir -p "${SERVICE_DIR}"

write_env_line() {
  local name="$1"
  local value="${!name-}"
  if [[ -n "${value}" ]]; then
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf 'Environment="%s=%s"\n' "${name}" "${value}"
  fi
}

{
cat <<EOF
[Unit]
Description=Telegram AI Team Bot-to-Bot Manager Service
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/run_team.sh
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=PYTHON_BIN=${PYTHON_BIN}
Environment=PATH=${PATH}
EOF
if [[ -n "${HERMES_BIN}" ]]; then
  printf 'Environment=HERMES_BIN=%s\n' "${HERMES_BIN}"
fi
for name in http_proxy https_proxy all_proxy no_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY; do
  write_env_line "${name}"
done
cat <<EOF

[Install]
WantedBy=default.target
EOF
} > "${SERVICE_FILE}"

systemctl --user daemon-reload
systemctl --user enable "${SERVICE_NAME}"
systemctl --user restart "${SERVICE_NAME}"

echo "Installed user service: ${SERVICE_NAME}"
echo "Status: systemctl --user status ${SERVICE_NAME}"
echo "Logs:   journalctl --user -u ${SERVICE_NAME} -f"
