#!/usr/bin/env python3
"""Stop Telegram AI Team Hermes tmux role sessions."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from ai_team_b2b_service import ROLES, load_dotenv  # noqa: E402


def session_name(role: str) -> str:
    prefix = os.environ.get("HERMES_TMUX_PREFIX", "telegrambots")
    return f"{prefix}-{role.lower()}"


def stop_role(role: str) -> None:
    session = session_name(role)
    result = subprocess.run(["tmux", "kill-session", "-t", session], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode == 0:
        print(f"{role}: stopped {session}")
    else:
        print(f"{role}: not running ({session})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stop persistent Hermes tmux agents.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--role", choices=tuple(ROLES), help="Stop only one role.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(PROJECT_DIR / args.env_file)
    roles = [args.role] if args.role else list(ROLES)
    for role in roles:
        stop_role(role)


if __name__ == "__main__":
    main()
