#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
mkdir -p data logs artifacts

tmux kill-server 2>/dev/null || true

LOCK_FILE="${SERVICE_LOCK_FILE:-data/bot2bot.lock}"
if [[ "${LOCK_FILE}" != /* ]]; then
  LOCK_FILE="${PWD}/${LOCK_FILE}"
fi
if [[ -f "${LOCK_FILE}" ]]; then
  LOCK_PID="$(tr -cd '0-9' < "${LOCK_FILE}" || true)"
  if [[ -z "${LOCK_PID}" ]] || ! kill -0 "${LOCK_PID}" 2>/dev/null; then
    rm -f "${LOCK_FILE}"
  fi
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [[ "${HERMES_TMUX_AUTOSTART:-1}" == "1" ]]; then
  "${PYTHON_BIN}" scripts/start_hermes_tmux_agents.py
fi
export PYTHONPATH="${PWD}/code${PYTHONPATH:+:${PYTHONPATH}}"
exec "${PYTHON_BIN}" -m bot2bot.service
