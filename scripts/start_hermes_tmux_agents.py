#!/usr/bin/env python3
"""Start one persistent tmux Hermes session per Telegram AI Team role."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "code"))

from bot2bot.config import load_dotenv  # noqa: E402
from bot2bot.roles import ROLES, build_role_prompt  # noqa: E402


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_DIR,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def session_name(role: str) -> str:
    prefix = os.environ.get("HERMES_TMUX_PREFIX", "telegrambots")
    return f"{prefix}-{role.lower()}"


def has_session(session: str) -> bool:
    result = run(["tmux", "has-session", "-t", session], check=False)
    return result.returncode == 0


def write_role_prompt(role: str) -> Path:
    prompt_dir = PROJECT_DIR / os.environ.get("HERMES_ROLE_PROMPT_DIR", "artifacts/hermes-role-prompts")
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = prompt_dir / f"{role.lower()}.md"
    prompt_path.write_text(build_role_prompt(role), encoding="utf-8")
    return prompt_path


def inject_role_prompt(session: str, prompt_path: Path) -> None:
    if os.environ.get("HERMES_ROLE_PROMPT_INJECT", "1") != "1":
        return
    delay = float(os.environ.get("HERMES_ROLE_PROMPT_INJECT_DELAY", "3"))
    if delay > 0:
        import time

        time.sleep(delay)
    bootstrap_path = prompt_path.with_suffix(".bootstrap.md")
    bootstrap_path.write_text(
        "\n".join(
            [
                "请加载并遵守以下 Telegram AI Team 角色契约。",
                "这是一条长期系统约束：之后每个任务都必须服从它，尤其是通信边界和输出格式。",
                "只需简短确认“角色契约已加载”，不要执行任何任务。",
                "",
                prompt_path.read_text(encoding="utf-8"),
            ]
        ),
        encoding="utf-8",
    )
    buffer_name = f"{session}-role-prompt"
    try:
        run(["tmux", "load-buffer", "-b", buffer_name, str(bootstrap_path)])
        run(["tmux", "paste-buffer", "-b", buffer_name, "-t", session])
        run(["tmux", "send-keys", "-t", session, "Enter"])
    finally:
        bootstrap_path.unlink(missing_ok=True)


def build_hermes_command(role: str) -> str:
    config = ROLES[role]
    default_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = os.environ.get("HERMES_BIN") or (str(default_hermes) if default_hermes.exists() else "hermes")
    provider = os.environ.get("HERMES_PROVIDER") or os.environ.get("AI_PROVIDER", "xiaomi")
    model = os.environ.get("HERMES_MODEL") or os.environ.get("AI_MODEL", "mimo-v2.5-pro")
    args = [
        hermes_bin,
        "chat",
        "--provider",
        provider,
        "--model",
        model,
        "--skills",
        ",".join(config.skills),
        "--toolsets",
        ",".join(config.toolsets),
        "--accept-hooks",
        "--source",
        f"telegrambots-{role.lower()}",
    ]
    if os.environ.get("HERMES_IGNORE_USER_CONFIG", "1") == "1":
        args.append("--ignore-user-config")
    if os.environ.get("HERMES_TMUX_YOLO", "0") == "1":
        if os.environ.get("HERMES_TMUX_ALLOW_YOLO") != "I_UNDERSTAND":
            raise SystemExit(
                "Refusing HERMES_TMUX_YOLO=1 without "
                "HERMES_TMUX_ALLOW_YOLO=I_UNDERSTAND. This disables Hermes safety approvals."
            )
        print(f"WARNING: starting {role} with Hermes --yolo; safety approvals are disabled.", file=sys.stderr)
        args.append("--yolo")
    if os.environ.get("HERMES_RESUME_SESSIONS", "0") == "1":
        args.extend(["--continue", f"telegrambots-{role.lower()}"])
    path = os.environ.get("PATH", "")
    return (
        f"export PATH={shlex.quote(path)}; "
        f"cd {shlex.quote(str(PROJECT_DIR))} && exec "
        + " ".join(shlex.quote(arg) for arg in args)
    )


def start_role(role: str, restart: bool = False) -> None:
    session = session_name(role)
    prompt_path = write_role_prompt(role)
    if has_session(session):
        if not restart:
            print(f"{role}: tmux session already running: {session}")
            return
        run(["tmux", "kill-session", "-t", session])

    command = build_hermes_command(role)
    run(["tmux", "new-session", "-d", "-s", session, "bash", "-lc", command])
    inject_role_prompt(session, prompt_path)
    print(f"{role}: started {session}")
    print(f"  prompt: {prompt_path}")
    print(f"  attach: tmux attach -t {session}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start persistent Hermes tmux agents for Telegram AI Team.")
    parser.add_argument("--env-file", default=str(PROJECT_DIR / ".env"))
    parser.add_argument("--role", choices=tuple(ROLES), help="Start only one role.")
    parser.add_argument("--restart", action="store_true", help="Restart existing role sessions.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env_path = Path(args.env_file).expanduser()
    if not env_path.is_absolute():
        env_path = PROJECT_DIR / env_path
    load_dotenv(env_path)
    roles = [args.role] if args.role else list(ROLES)
    for role in roles:
        start_role(role, restart=args.restart)


if __name__ == "__main__":
    main()
