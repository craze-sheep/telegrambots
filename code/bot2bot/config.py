from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram.request import HTTPXRequest


TZ = ZoneInfo("Asia/Shanghai")
MANAGER_ROLE = "Supervisor"
WORKER_ROLES = ("Planner", "Researcher", "Developer", "Tester")
HANDOFF_SUMMARY_MAX_CHARS = 300
DEFAULT_AI_PROVIDER = "xiaomi"
DEFAULT_AI_API_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_AI_API_MODE = "chat_completions"
DEFAULT_AI_MODEL = "mimo-v2.5-pro"
DEFAULT_AI_TIMEOUT = "90"
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_DIR / ".env"
DEFAULT_POLL_INIT_MAX_RETRIES = 30
DEFAULT_COMPLETED_TASK_MEMORY_LIMIT = 100
MIN_REPORT_BODY_CHARS = 50
BOT_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]+$")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def require_env(name: str, pattern: re.Pattern[str] | None = None) -> str:
    value = os.environ.get(name, "").strip()
    if value and (pattern is None or pattern.match(value)):
        return value
    if value and pattern is not None:
        print(f"Invalid value format for environment variable: {name}", file=sys.stderr)
        raise SystemExit(2)
    print(f"Missing required environment variable: {name}", file=sys.stderr)
    raise SystemExit(2)


def make_request(timeout: float) -> HTTPXRequest:
    return HTTPXRequest(
        connect_timeout=timeout,
        read_timeout=timeout,
        write_timeout=timeout,
        pool_timeout=timeout,
    )


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc
    if minimum is not None and parsed < minimum:
        raise RuntimeError(f"{name} must be >= {minimum}, got {parsed}")
    return parsed


def require_int_env(name: str) -> int:
    value = require_env(name, re.compile(r"^-?\d+$"))
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer, got {value!r}") from exc

