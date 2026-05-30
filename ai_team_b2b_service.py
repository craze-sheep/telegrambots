#!/usr/bin/env python3
"""Bot-to-bot Telegram AI team: manager schedules workers by @mention."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

import httpx
from telegram import Bot, Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.request import HTTPXRequest


TZ = ZoneInfo("Asia/Shanghai")
MANAGER_ROLE = "Supervisor"
WORKER_ROLES = ("Planner", "Researcher", "Developer", "Tester")
BOT_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
FILE_BLOCK_RE = re.compile(
    r"(?ims)^\s*(?:FILE|文件)\s*[:：]\s*`?([^\n`]+?)`?\s*\n```([A-Za-z0-9_.+-]*)\s*\n(.*?)\n```"
)

ARTIFACT_INSTRUCTIONS = """产物要求：
- 你的回复会自动保存成 Markdown 文档。
- 如果本阶段需要产出代码或配置文件，必须直接给出文件内容，不要只描述“应该创建”。
- 代码文件使用下面格式；路径只能是相对路径，不能包含 .. 或绝对路径：
FILE: relative/path.ext
```language
file content
```
"""


@dataclass(frozen=True)
class RoleConfig:
    role: str
    token_env: str
    description: str
    skills: tuple[str, ...]
    mcps: tuple[str, ...]
    toolsets: tuple[str, ...]


@dataclass
class TaskState:
    task_id: str
    user_text: str
    summary: str
    turns: int = 0
    completed: bool = False
    current_role: str = "Supervisor"
    status: str = "created"
    contacted_roles: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ManagerDecision:
    target_role: str
    message: str
    handoff_summary: str


ROLES = {
    "Supervisor": RoleConfig(
        "Supervisor",
        "SUPERVISOR_TOKEN",
        "经理。负责接收用户任务、@调度角色、汇总结论。",
        skills=("kanban-orchestrator", "dispatching-parallel-agents", "messaging-gateway-integrations"),
        mcps=(
            "holographic:fact_query",
            "holographic:fact_store",
            "holographic:fact_feedback",
            "sequential_thinking:sequentialthinking",
        ),
        toolsets=("skills", "todo", "messaging", "holographic", "sequential-thinking"),
    ),
    "Planner": RoleConfig(
        "Planner",
        "DECOMPOSER_TOKEN",
        "规划员。负责拆解任务、定义交付物和验收标准。",
        skills=("brainstorming", "plan", "writing-plans"),
        mcps=(
            "holographic:fact_query",
            "holographic:fact_store",
            "sequential_thinking:sequentialthinking",
        ),
        toolsets=("skills", "todo", "file", "holographic", "sequential-thinking"),
    ),
    "Researcher": RoleConfig(
        "Researcher",
        "RESEARCHER_TOKEN",
        "调研员。负责事实核查、资料路径、风险和不确定性。",
        skills=("web-access", "chinese-platform-research", "literature-survey"),
        mcps=(
            "fetch:fetch",
            "context7:resolve_library_id",
            "context7:query_docs",
            "holographic:fact_query",
            "holographic:fact_feedback",
        ),
        toolsets=("skills", "web", "browser", "file", "fetch", "context7", "holographic"),
    ),
    "Developer": RoleConfig(
        "Developer",
        "DEVELOPER_TOKEN",
        "开发者。负责实现方案、文件改动建议和执行步骤。",
        skills=("codex", "codebase-inspection", "systematic-debugging", "implementation-verification-workflows"),
        mcps=(
            "codegraph:codegraph_context",
            "codegraph:codegraph_explore",
            "codegraph:codegraph_files",
            "codegraph:codegraph_impact",
            "codegraph:codegraph_trace",
            "context7:query_docs",
            "holographic:fact_query",
        ),
        toolsets=("skills", "terminal", "file", "code_execution", "codegraph", "context7", "holographic"),
    ),
    "Tester": RoleConfig(
        "Tester",
        "TESTER_TOKEN",
        "测试员。负责验收清单、测试计划、风险复核。",
        skills=("test-driven-development", "verification-before-completion", "requesting-code-review", "playwright"),
        mcps=(
            "codegraph:codegraph_impact",
            "codegraph:codegraph_trace",
            "codegraph:codegraph_status",
            "holographic:fact_query",
            "sequential_thinking:sequentialthinking",
        ),
        toolsets=("skills", "terminal", "file", "browser", "codegraph", "holographic", "sequential-thinking"),
    ),
}


def now_text() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


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


def make_task_id() -> str:
    return f"B2B-{datetime.now(TZ).strftime('%Y%m%d-%H%M%S')}"


def compact(text: str, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def clean_user_text(text: str, manager_username: str) -> str:
    text = re.sub(rf"@{re.escape(manager_username)}\b", "", text, flags=re.I)
    text = re.sub(r"^/new(?:@\w+)?\b", "", text).strip()
    text = re.sub(r"^新任务[:：]?", "", text).strip()
    return text or "未命名任务"


def command_name(text: str) -> str:
    first = text.strip().split(maxsplit=1)[0] if text.strip() else ""
    return first.split("@", 1)[0]


def extract_task_id(text: str) -> str | None:
    match = re.search(r"\bB2B-\d{8}-\d{6}\b", text)
    return match.group(0) if match else None


def extract_report_role(text: str) -> str | None:
    match = re.search(
        r"^\s*\[B2B-\d{8}-\d{6}\]\[(Planner|Researcher|Developer|Tester)\]\[REPORT\]",
        text,
        flags=re.I,
    )
    if not match:
        return None
    wanted = match.group(1).lower()
    for role in WORKER_ROLES:
        if role.lower() == wanted:
            return role
    return None


def extract_section(text: str, names: tuple[str, ...]) -> str | None:
    pattern = "|".join(re.escape(name) for name in names)
    match = re.search(
        rf"(?ims)^\s*(?:#+\s*)?(?:{pattern})\s*[:：]\s*(.*?)(?=^\s*(?:#+\s*)?(?:TARGET_ROLE|MESSAGE|HANDOFF_SUMMARY|目标角色|消息|交接摘要)\s*[:：]|\Z)",
        text,
    )
    if not match:
        return None
    return match.group(1).strip()


def parse_manager_output(text: str, fallback_role: str) -> tuple[str, str, str]:
    target = extract_section(text, ("TARGET_ROLE", "目标角色"))
    message = extract_section(text, ("MESSAGE", "消息"))
    summary = extract_section(text, ("HANDOFF_SUMMARY", "交接摘要"))
    target_role = (target or fallback_role).strip()
    for role in WORKER_ROLES + ("DONE",):
        if re.search(rf"\b{re.escape(role)}\b", target_role, flags=re.I):
            target_role = role
            break
    if target_role not in set(WORKER_ROLES) | {"DONE"}:
        target_role = fallback_role
    return target_role, (message or text).strip(), compact(summary or message or text, 700)


def parse_worker_output(text: str) -> tuple[str, str]:
    message = extract_section(text, ("MESSAGE", "消息"))
    summary = extract_section(text, ("HANDOFF_SUMMARY", "交接摘要"))
    visible = (message or text).strip()
    return visible, compact(summary or visible, 700)


def replace_role_mentions(text: str, usernames: dict[str, str]) -> str:
    replacements = {
        "Supervisor": usernames.get("Supervisor", ""),
        "Planner": usernames.get("Planner", ""),
        "Researcher": usernames.get("Researcher", ""),
        "Developer": usernames.get("Developer", ""),
        "Tester": usernames.get("Tester", ""),
    }
    for role, username in replacements.items():
        if username:
            text = re.sub(rf"@{role}\b", f"@{username}", text, flags=re.I)
    return text


def remove_worker_mentions(text: str, usernames: dict[str, str]) -> str:
    for role in WORKER_ROLES:
        username = usernames.get(role, "")
        if username:
            text = re.sub(rf"@{re.escape(username)}\b", role, text, flags=re.I)
        text = re.sub(rf"@{role}\b", role, text, flags=re.I)
    return text


def supervisor_message_kind(text: str) -> str | None:
    match = re.match(
        r"^\s*\[B2B-\d{8}-\d{6}\]\[Supervisor\]\[(ASSIGN|DONE|ERROR)\]",
        text,
        flags=re.I,
    )
    return match.group(1).upper() if match else None


def is_supervisor_assignment(text: str) -> bool:
    return supervisor_message_kind(text) == "ASSIGN"


def is_worker_report(role: str, text: str) -> bool:
    return bool(
        re.match(
            rf"^\s*\[B2B-\d{{8}}-\d{{6}}\]\[{re.escape(role)}\]\[REPORT\]",
            text,
            flags=re.I,
        )
    )


def strip_supervisor_header(text: str) -> str:
    return re.sub(
        r"^\s*(?:\[[^\]\n]+\])?\[Supervisor\]\[(?:ASSIGN|DONE|ERROR)\]\s*",
        "",
        text,
        count=1,
        flags=re.I,
    ).strip()


def is_from_role(user_id: int | None, role: str, role_user_ids: dict[str, int]) -> bool:
    return user_id is not None and role_user_ids.get(role) == user_id


def role_capability_text(role: str) -> str:
    config = ROLES[role]
    return (
        f"{role}: {config.description}\n"
        f"  skills: {', '.join(config.skills)}\n"
        f"  mcp: {', '.join(config.mcps)}\n"
        f"  hermes toolsets: {', '.join(config.toolsets)}"
    )


def build_role_prompt(role: str) -> str:
    config = ROLES[role]
    lines = [
        f"# Telegram AI Team Role: {role}",
        "",
        role_capability_text(role),
        "",
        "## Identity",
        "",
        "- You are a persistent Hermes Agent behind one Telegram bot in a visible group chat.",
        "- The Telegram group is a workbench for the human user to watch progress.",
        "- The project source of truth is the local working directory plus artifacts saved under `artifacts/tasks/<task_id>/`.",
        "- Do not claim that a tool, MCP, file write, test, browser action, or shell command happened unless it actually happened in your available environment.",
        "- If a requested action needs a tool that is not available to your configured skills/toolsets, mark it as `待执行/待验证` and explain what is missing.",
        "",
        "## Team Topology",
        "",
        "- The only manager is Supervisor.",
        "- Supervisor may assign Planner, Researcher, Developer, Tester, or finish with DONE.",
        "- Planner, Researcher, Developer, and Tester are workers.",
        "- Workers never talk to each other, never schedule each other, and never address the human user as if they were the manager.",
        "- Workers report only to Supervisor.",
        "",
        "## Artifact Rules",
        "",
        "- Every substantive result must be suitable for Markdown archival.",
        "- Keep Telegram-facing text concise, but include enough handoff context for Supervisor.",
        "- If producing code/config/docs, output complete file contents using this literal pattern:",
        "",
        "    FILE: relative/path.ext",
        "    ```language",
        "    file content",
        "    ```",
        "",
        "- File paths must be relative paths. Never use absolute paths, `..`, or Windows drive prefixes.",
        "- Code/file artifacts are drafts under `artifacts/tasks/<task_id>/files/` unless the human explicitly asks to merge them into source.",
        "",
        "## Output Sections",
        "",
        "- Follow the exact output schema requested by the current job prompt.",
        "- Do not add unrelated chat, greetings, or meta commentary outside the requested schema.",
        "- Preserve the task ID exactly as given.",
        "",
    ]

    if role == MANAGER_ROLE:
        lines.extend(
            [
                "## Supervisor Rules",
                "",
                "- You are the only role allowed to dispatch work, summarize status, finish tasks, or report errors.",
                "- Telegram-facing Supervisor messages may use only these headers:",
                "  - `[B2B-YYYYMMDD-HHMMSS][Supervisor][ASSIGN]`",
                "  - `[B2B-YYYYMMDD-HHMMSS][Supervisor][STATUS]`",
                "  - `[B2B-YYYYMMDD-HHMMSS][Supervisor][DONE]`",
                "  - `[B2B-YYYYMMDD-HHMMSS][Supervisor][ERROR]`",
                "- For ASSIGN, mention exactly one target worker by real bot username.",
                "- Do not ask workers to read full group history. Give them a short handoff package.",
                "- Choose the next worker by capability, not by a fixed workflow.",
                "- Finish with DONE only when the user's requested outcome is satisfied or when a clear limitation has been explained.",
                "- If a worker suggests next steps, treat that as advice; only you decide the next assignment.",
                "",
                "## Supervisor Decision Output",
                "",
                "When asked to decide, output exactly these fields:",
                "",
                "```text",
                "TARGET_ROLE: Planner/Researcher/Developer/Tester/DONE",
                "MESSAGE: Telegram-visible message. ASSIGN messages must include task ID and the target worker username.",
                "HANDOFF_SUMMARY: <=300 Chinese characters, enough for the next role.",
                "```",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## Worker Rules",
                "",
                f"- You are {role}. Complete only the slice assigned to {role}.",
                "- You may act only when Supervisor assigns you work.",
                "- Never produce Telegram messages with WORKING, STATUS, ASSIGN, DONE, or ERROR headers.",
                "- Never @, directly instruct, schedule, or route work to Planner, Researcher, Developer, or Tester.",
                "- The only allowed Telegram @ mention is the real Supervisor username provided in the job prompt.",
                "- If you recommend next steps, describe the needed capability for Supervisor; do not name another worker as the next assignee.",
                "- Do not write as if you are the manager. Do not say that another worker should now do something as a command.",
                "- Do not write `负责人: Developer`, `下一步由 Researcher 执行`, `请 Tester 继续`, or similar assignment language.",
                "- Your Telegram-facing MESSAGE must be a REPORT to Supervisor.",
                "- The service enforces this in code: invalid worker output is rejected and you will be asked to rewrite once; repeated invalid output becomes a local fallback report.",
                "",
                "## Worker Telegram Message Contract",
                "",
                f"Your MESSAGE must start exactly like this, replacing only the task ID:",
                "",
                "```text",
                f"[B2B-YYYYMMDD-HHMMSS][{role}][REPORT]",
                "@<real Supervisor username>",
                "your report body",
                "```",
                "",
                "Forbidden worker MESSAGE examples:",
                "",
                "```text",
                f"[B2B-YYYYMMDD-HHMMSS][{role}][WORKING]",
                f"[B2B-YYYYMMDD-HHMMSS][{role}][STATUS]",
                "[B2B-YYYYMMDD-HHMMSS][Supervisor][ASSIGN]",
                "@other_worker_bot please continue",
                "下一步由 Developer 执行",
                "```",
                "",
                "Allowed wording for advice:",
                "",
                "```text",
                "供 Supervisor 决策参考：后续需要实现环节，并需要补充测试验证。",
                "```",
                "",
                "## Worker Output Schema",
                "",
                "When asked to reply, output exactly these fields:",
                "",
                "```text",
                "MESSAGE: must be a Telegram-visible REPORT following the Worker Telegram Message Contract.",
                "HANDOFF_SUMMARY: <=300 Chinese characters for Supervisor.",
                "```",
                "",
            ]
        )

    return "\n".join(lines).strip() + "\n"


def safe_relative_path(raw_path: str) -> PurePosixPath | None:
    cleaned = raw_path.strip().strip("`").strip().replace("\\", "/")
    if not cleaned or cleaned.startswith("/"):
        return None
    path = PurePosixPath(cleaned)
    if not path.name:
        return None
    for part in path.parts:
        if part in {"", ".", ".."} or ":" in part:
            return None
    return path


def extract_file_blocks(text: str) -> list[tuple[PurePosixPath, str, str]]:
    files: list[tuple[PurePosixPath, str, str]] = []
    for match in FILE_BLOCK_RE.finditer(text):
        rel_path = safe_relative_path(match.group(1))
        if rel_path is None:
            continue
        language = match.group(2).strip()
        content = match.group(3).rstrip() + "\n"
        files.append((rel_path, language, content))
    return files


def sanitize_label(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower() or "artifact"


def extract_marked_response(captured: str, start_marker: str, done_marker: str) -> str | None:
    start_matches = list(re.finditer(rf"(?m)^\s*{re.escape(start_marker)}\s*$", captured))
    if not start_matches:
        return None
    start_pos = start_matches[-1].end()
    done_match = re.search(rf"(?m)^\s*{re.escape(done_marker)}\s*$", captured[start_pos:])
    if not done_match:
        return None
    return captured[start_pos : start_pos + done_match.start()].strip()


def acquire_process_lock(path: Path) -> object:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(
            f"Another telegram bot service is already running for this project: {path}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    lock_file.seek(0)
    lock_file.truncate()
    lock_file.write(str(os.getpid()))
    lock_file.flush()
    return lock_file


class OpenAICompatibleClient:
    def __init__(self) -> None:
        self.provider = os.environ.get("AI_PROVIDER", "xiaomi")
        self.base_url = os.environ.get("AI_API_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1").rstrip("/")
        self.model = os.environ.get("AI_MODEL", "mimo-v2.5-pro")
        self.api_mode = os.environ.get("AI_API_MODE", "chat_completions")
        self.api_key = os.environ.get("AI_API_KEY", "").strip() or self.load_provider_key(self.provider)
        self.timeout = float(os.environ.get("AI_TIMEOUT", "90"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and self.api_mode == "chat_completions"

    def load_provider_key(self, provider: str) -> str:
        config_path = Path(os.environ.get("HERMES_CONFIG", "~/.hermes/config.yaml")).expanduser()
        if not config_path.exists():
            return ""

        in_provider = False
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("- name:"):
                in_provider = line.split(":", 1)[1].strip().strip("'\"") == provider
                continue
            if in_provider and line.startswith("api_key:"):
                return line.split(":", 1)[1].strip().strip("'\"")
        return ""

    async def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        if not self.enabled:
            raise RuntimeError("AI_API_KEY is not set or AI_API_MODE is unsupported")

        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"].strip()


class TmuxHermesClient:
    def __init__(self, project_dir: Path, artifacts_dir: Path) -> None:
        self.project_dir = project_dir
        self.artifacts_dir = artifacts_dir
        self.prefix = os.environ.get("HERMES_TMUX_PREFIX", "telegrambots")
        self.timeout = float(os.environ.get("HERMES_TMUX_TIMEOUT", "360"))
        self.poll_interval = float(os.environ.get("HERMES_TMUX_POLL_INTERVAL", "2"))
        self.locks = {role: asyncio.Lock() for role in ROLES}

    def session_name(self, role: str) -> str:
        return f"{self.prefix}-{role.lower()}"

    async def run_tmux(self, *args: str) -> str:
        process = await asyncio.create_subprocess_exec(
            "tmux",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.project_dir,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"tmux {' '.join(args)} failed: {detail}")
        return stdout.decode("utf-8", errors="replace")

    async def ensure_session(self, role: str) -> None:
        session = self.session_name(role)
        process = await asyncio.create_subprocess_exec(
            "tmux",
            "has-session",
            "-t",
            session,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await process.communicate()
        if process.returncode == 0:
            return
        script = self.project_dir / "scripts" / "start_hermes_tmux_agents.py"
        starter = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            "--role",
            role,
            cwd=self.project_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await starter.communicate()
        if starter.returncode != 0:
            detail = (stderr or stdout).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"failed to start Hermes tmux session for {role}: {detail}")
        await asyncio.sleep(float(os.environ.get("HERMES_TMUX_STARTUP_DELAY", "3")))

    def build_job_prompt(self, role: str, job_id: str, system_prompt: str, user_prompt: str) -> str:
        config = ROLES[role]
        start_marker = f"<<<B2B_RESPONSE:{job_id}>>>"
        done_marker = f"<<<B2B_DONE:{job_id}>>>"
        payload = {
            "job_id": job_id,
            "role": role,
            "role_description": config.description,
            "skills": config.skills,
            "mcp": config.mcps,
            "hard_rules": [
                "只处理本条任务，不读取或展开完整群聊历史。",
                "必须把实质产出写成 Markdown；如有代码，用 FILE: relative/path.ext 加代码块。",
                "Supervisor 只能调度 Planner/Researcher/Developer/Tester 或 DONE。",
                "Worker 只允许发送 [任务ID][角色][REPORT] 给 Supervisor，禁止 WORKING/STATUS/ASSIGN/DONE/ERROR。",
                "Worker 禁止 @、指挥、安排其他 worker；只能把建议写成供 Supervisor 决策参考。",
                "涉及未真实执行的 MCP/工具结果，必须标注待执行或待验证，不能编造。",
                "输出必须放在指定开始/结束标记之间。",
            ],
            "role_contract": build_role_prompt(role),
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }
        return (
            f"请处理这个 Telegram AI Team 任务。先单独输出 {start_marker}，"
            f"然后输出最终答案，最后单独输出 {done_marker}。"
            "不要在结束标记后输出任何内容。任务 JSON："
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    async def complete(self, role: str, system_prompt: str, user_prompt: str) -> str:
        async with self.locks[role]:
            await self.ensure_session(role)
            session = self.session_name(role)
            job_id = f"{role.lower()}-{datetime.now(TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:16]}"
            start_marker = f"<<<B2B_RESPONSE:{job_id}>>>"
            done_marker = f"<<<B2B_DONE:{job_id}>>>"
            prompt = self.build_job_prompt(role, job_id, system_prompt, user_prompt)
            jobs_dir = self.artifacts_dir / "tmux-jobs"
            jobs_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = jobs_dir / f"{job_id}.prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            buffer_name = f"b2b-{job_id}"
            await self.run_tmux("send-keys", "-t", session, "C-l")
            await self.run_tmux("clear-history", "-t", session)
            await self.run_tmux("load-buffer", "-b", buffer_name, str(prompt_path))
            await self.run_tmux("paste-buffer", "-b", buffer_name, "-t", session)
            await self.run_tmux("send-keys", "-t", session, "Enter")

            deadline = asyncio.get_running_loop().time() + self.timeout
            captured = ""
            while asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(self.poll_interval)
                captured = await self.run_tmux("capture-pane", "-p", "-S", "-5000", "-t", session)
                response = extract_marked_response(captured, start_marker, done_marker)
                if response is not None:
                    return response

            timeout_path = jobs_dir / f"{job_id}.timeout-capture.txt"
            timeout_path.write_text(captured, encoding="utf-8")
            raise TimeoutError(f"Hermes tmux job timed out for {role}; capture saved to {timeout_path}")


class BotToBotTeam:
    def __init__(self, group_chat_id: int, timeout: float) -> None:
        self.group_chat_id = group_chat_id
        self.timeout = timeout
        self.client = OpenAICompatibleClient()
        self.project_dir = Path(__file__).resolve().parent
        self.bots: dict[str, Bot] = {}
        self.usernames: dict[str, str] = {}
        self.user_ids: dict[str, int] = {}
        self.tasks: dict[str, TaskState] = {}
        self.artifacts_dir = Path(os.environ.get("ARTIFACTS_DIR", "artifacts")).expanduser()
        self.artifact_sequence: dict[str, int] = {}
        self.agent_backend = os.environ.get("AGENT_BACKEND", "tmux_hermes").strip().lower()
        self.tmux_client = TmuxHermesClient(self.project_dir, self.artifacts_dir)

    async def complete_role(self, role: str, system_prompt: str, user_prompt: str) -> str:
        if self.agent_backend == "tmux_hermes":
            try:
                return await self.tmux_client.complete(role, system_prompt, user_prompt)
            except Exception as exc:
                print(f"{role} tmux Hermes fallback to direct LLM after {type(exc).__name__}: {exc}", flush=True)
        return await self.client.complete(system_prompt, user_prompt)


    async def initialize(self) -> None:
        for role, config in ROLES.items():
            bot = Bot(require_env(config.token_env, BOT_TOKEN_RE), request=make_request(self.timeout))
            await bot.initialize()
            me = await bot.get_me()
            self.bots[role] = bot
            self.usernames[role] = me.username or ""
            self.user_ids[role] = me.id
            print(f"{role}: @{self.usernames[role]}", flush=True)

    async def shutdown(self) -> None:
        for bot in self.bots.values():
            await bot.shutdown()

    def is_mentioned(self, role: str, text: str) -> bool:
        username = self.usernames.get(role, "")
        return bool(username and re.search(rf"@{re.escape(username)}\b", text, flags=re.I))

    def task_artifact_dir(self, task_id: str) -> Path:
        return self.artifacts_dir / "tasks" / task_id

    def ensure_task_readme(self, state: TaskState) -> None:
        task_dir = self.task_artifact_dir(state.task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        readme = task_dir / "README.md"
        if readme.exists():
            return
        readme.write_text(
            "\n".join(
                [
                    f"# {state.task_id}",
                    "",
                    f"- Created: {now_text()}",
                    f"- Mode: centralized bot-to-bot manager",
                    f"- User task: {state.user_text}",
                    "",
                    "## Topology",
                    "",
                    "User <-> Supervisor <-> Planner / Researcher / Developer / Tester",
                    "",
                    "Workers only report to Supervisor. Worker-to-worker messages are ignored by service logic.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def next_artifact_name(self, task_id: str, kind: str) -> str:
        self.artifact_sequence[task_id] = self.artifact_sequence.get(task_id, 0) + 1
        stamp = datetime.now(TZ).strftime("%Y%m%d-%H%M%S-%f")
        return f"{self.artifact_sequence[task_id]:03d}-{stamp}-{sanitize_label(kind)}.md"

    def write_code_files(self, task_id: str, role: str, message: str) -> list[str]:
        extracted = extract_file_blocks(message)
        if not extracted:
            return []
        files_root = (self.task_artifact_dir(task_id) / "files").resolve()
        files_root.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for rel_path, _language, content in extracted:
            target = (files_root / Path(*rel_path.parts)).resolve()
            try:
                target.relative_to(files_root)
            except ValueError:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            written.append(str(Path("files") / Path(*rel_path.parts)))
        return written

    def write_role_markdown(
        self,
        task_id: str,
        role: str,
        kind: str,
        message: str,
        handoff_summary: str,
        state: TaskState | None,
    ) -> None:
        if state is not None:
            self.ensure_task_readme(state)
        task_dir = self.task_artifact_dir(task_id)
        role_dir = task_dir / role.lower()
        role_dir.mkdir(parents=True, exist_ok=True)
        written_files = self.write_code_files(task_id, role, message)
        config = ROLES[role]
        md_path = role_dir / self.next_artifact_name(task_id, kind)
        code_file_lines = "\n".join(f"- `{path}`" for path in written_files) or "- None"
        md_path.write_text(
            "\n".join(
                [
                    f"# {role} {kind}",
                    "",
                    f"- Time: {now_text()}",
                    f"- Task ID: {task_id}",
                    f"- Role: {role}",
                    f"- Kind: {kind}",
                    f"- Skills: {', '.join(config.skills)}",
                    f"- MCP: {', '.join(config.mcps)}",
                    "",
                    "## User Task",
                    "",
                    state.user_text if state is not None else "未知任务",
                    "",
                    "## Handoff Summary",
                    "",
                    handoff_summary or "None",
                    "",
                    "## Code Files Written",
                    "",
                    code_file_lines,
                    "",
                    "## Telegram Message",
                    "",
                    message,
                    "",
                ]
            ),
            encoding="utf-8",
        )
        print(f"artifact written: {md_path}", flush=True)

    def build_status_card(self, state: TaskState, title: str, detail: str = "") -> str:
        contacted = ", ".join(state.contacted_roles) or "None"
        display_detail = remove_worker_mentions(detail, self.usernames)
        lines = [
            f"[{state.task_id}][Supervisor][STATUS]",
            title,
            f"当前：{state.current_role} / {state.status}",
            f"轮次：{state.turns}",
            f"已联系：{contacted}",
            f"任务：{compact(state.user_text, 120)}",
        ]
        if display_detail:
            lines.extend(["", compact(display_detail, 350)])
        return "\n".join(lines)

    async def send_task_status(self, state: TaskState, title: str, detail: str = "") -> None:
        await self.send_as("Supervisor", self.build_status_card(state, title, detail))

    def build_all_status(self) -> str:
        active = [state for state in self.tasks.values() if not state.completed]
        if not active:
            return "[SYSTEM][Supervisor][STATUS]\n当前没有进行中的任务。"
        lines = ["[SYSTEM][Supervisor][STATUS]", f"进行中任务：{len(active)}"]
        for state in active:
            contacted = ", ".join(state.contacted_roles) or "None"
            lines.extend(
                [
                    "",
                    f"- {state.task_id}",
                    f"  当前：{state.current_role} / {state.status}",
                    f"  轮次：{state.turns}",
                    f"  已联系：{contacted}",
                    f"  任务：{compact(state.user_text, 90)}",
                ]
            )
        return "\n".join(lines)

    async def send_all_status(self) -> None:
        await self.send_as("Supervisor", self.build_all_status())

    def worker_outbound_violation(self, role: str, task_id: str, text: str) -> str | None:
        stripped = text.strip()
        header = re.match(
            r"^\s*\[(B2B-\d{8}-\d{6})\]\[([^\]\n]+)\]\[([^\]\n]+)\]",
            stripped,
            flags=re.I,
        )
        if header:
            found_task_id, found_role, found_kind = header.groups()
            if found_task_id != task_id or found_role.lower() != role.lower() or found_kind.upper() != "REPORT":
                return (
                    f"worker 群消息只能使用 [{task_id}][{role}][REPORT] 作为开头，"
                    f"不能使用 [{found_task_id}][{found_role}][{found_kind}]。"
                )

        for other_role in WORKER_ROLES:
            username = self.usernames.get(other_role, "")
            if other_role != role and username and re.search(rf"@{re.escape(username)}\b", stripped, flags=re.I):
                return f"worker 回报不能 @{username}，只能 @{self.usernames['Supervisor']}。"

        if re.search(r"\[(WORKING|STATUS|ASSIGN|DONE|ERROR)\]", stripped, flags=re.I):
            if not is_worker_report(role, stripped):
                return "worker 不能发送 WORKING/STATUS/ASSIGN/DONE/ERROR 类型消息，只能发送 REPORT。"
        if re.search(r"(?im)^\s*(WORKING|STATUS|ASSIGN|DONE|ERROR|TARGET_ROLE)\s*[:：]", stripped):
            return "worker REPORT 正文不能包含 WORKING/STATUS/ASSIGN/DONE/ERROR/TARGET_ROLE 标签。"

        other_roles = [other_role for other_role in WORKER_ROLES if other_role != role]
        role_pattern = "|".join(re.escape(other_role) for other_role in other_roles)
        directive_patterns = (
            rf"(?:下一步|后续|之后|现在|请|需要|应该|必须|交给|调度|安排|转给|派给|让|由)\s*(?:{role_pattern})\s*(?:执行|处理|继续|负责|完成|开始|接手|实现|调研|测试|开发)",
            rf"(?:{role_pattern})\s*(?:请|需要|应该|必须|负责|执行|处理|继续|接手|完成|开始|实现|调研|测试|开发)",
            rf"负责人\s*[:：]\s*(?:{role_pattern})",
        )
        for pattern in directive_patterns:
            for match in re.finditer(pattern, stripped, flags=re.I):
                return (
                    "worker REPORT 正文不能直接安排、指挥或指定其他 worker。"
                    "如需建议下一步，只能描述能力需求，不能点名安排 worker。"
                )
        return None

    def prepare_worker_report(self, role: str, task_id: str, text: str) -> tuple[str, str | None]:
        text = replace_role_mentions(text, self.usernames).strip()
        violation = self.worker_outbound_violation(role, task_id, text)
        if violation:
            return text, violation
        if not is_worker_report(role, text):
            text = f"[{task_id}][{role}][REPORT]\n{text}"
        return self.enforce_worker_outbound(role, text), None

    def enforce_worker_outbound(self, role: str, text: str) -> str:
        if role not in WORKER_ROLES:
            raise RuntimeError(f"Only worker roles can use worker outbound guard: {role}")
        if not is_worker_report(role, text):
            raise RuntimeError(f"{role} attempted to send a non-REPORT group message")

        text = remove_worker_mentions(text, self.usernames)
        supervisor_username = self.usernames["Supervisor"]
        allowed = supervisor_username.lower()

        def replace_mention(match: re.Match[str]) -> str:
            username = match.group(1)
            if username.lower() == allowed:
                return f"@{username}"
            return username

        text = re.sub(r"@([A-Za-z0-9_]{5,32})", replace_mention, text)
        if f"@{supervisor_username}" not in text:
            text = f"@{supervisor_username}\n{text}"
        return text

    async def send_as(self, role: str, text: str) -> None:
        if role != "Supervisor":
            text = self.enforce_worker_outbound(role, text)
        for attempt in range(1, 4):
            try:
                await self.bots[role].send_message(
                    chat_id=self.group_chat_id,
                    text=text,
                    disable_notification=True,
                )
                return
            except (TimedOut, NetworkError):
                if attempt == 3:
                    raise
                await asyncio.sleep(2 * attempt)

    def build_team_intro(self) -> str:
        lines = [
            "团队一共 5 个 bot：",
            "",
            f"- Supervisor：@{self.usernames['Supervisor']}，经理。接收你的任务，决定调度谁，最后汇总。",
        ]
        for role in WORKER_ROLES:
            lines.append(f"- {role}：@{self.usernames[role]}，{ROLES[role].description}")
        lines.extend(
            [
                "",
                "通信规则：你只需要把任务交给 Supervisor；Supervisor 负责 @ worker；worker 只向 Supervisor 回报，worker 之间不互相通信。",
            ]
        )
        return "\n".join(lines)

    def should_answer_team_intro_locally(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text.lower())
        return any(
            keyword in normalized
            for keyword in (
                "团队人数",
                "几个人",
                "多少人",
                "每个人的功能",
                "每个人功能",
                "功能和职责",
                "职责",
                "团队成员",
            )
        )

    async def manager_start_task(self, user_text: str) -> None:
        task_id = make_task_id()
        state = TaskState(task_id=task_id, user_text=user_text, summary=f"用户需求：{compact(user_text, 500)}")
        self.tasks[task_id] = state
        self.ensure_task_readme(state)
        await self.send_task_status(state, "任务已创建。Supervisor 正在判断下一步。")
        if self.should_answer_team_intro_locally(user_text):
            state.completed = True
            state.status = "done"
            message = f"[{task_id}][Supervisor][DONE]\n{self.build_team_intro()}"
            decision = ManagerDecision(target_role="DONE", message=message, handoff_summary="已直接回答团队人数与职责。")
            await self.send_manager_decision(task_id, decision)
            return
        decision = await self.manager_decide(
            state,
            incoming=f"用户发起新任务：{user_text}",
            fallback_role="Planner",
        )
        await self.send_manager_decision(task_id, decision)

    async def manager_decide(self, state: TaskState, incoming: str, fallback_role: str) -> ManagerDecision:
        role_directory = "\n".join(
            f"- {role}: @{self.usernames[role]}\n  {ROLES[role].description}\n"
            f"  skills: {', '.join(ROLES[role].skills)}\n"
            f"  mcp: {', '.join(ROLES[role].mcps)}\n"
            f"  hermes toolsets: {', '.join(ROLES[role].toolsets)}"
            for role in WORKER_ROLES
        )
        system_prompt = (
            "你是 Telegram AI Team 的 Supervisor 经理。你通过在群里 @某个角色来调度工作。"
            "你只能调度 Planner、Researcher、Developer、Tester，或者输出 DONE。"
            "不要套用固定流程；根据任务和最新回报自行决定下一步该 @ 谁，也可以重复调度同一个角色。"
            "不要让角色读取完整历史，只基于短交接摘要继续。"
            "简单确认、健康检查、问你是否在线这类请求，你可以直接 DONE 回答，不要派给 worker。"
            "收到 worker 回报后，只有当用户任务已经满足时才 DONE；否则继续调度最合适的 worker。"
            "所有 @ 必须使用真实 bot username，不能使用 @Planner、@Supervisor 这类角色名。"
            "调度时优先根据每个 worker 的 skills 和 MCP 能力选择人选。"
            "注意：当前 MCP 是能力边界和调度标签，不代表 worker 已经真实执行外部工具；不要编造工具执行结果。"
            "群聊消息只是可见工作台；所有实质产出也会落盘到工作目录。"
        )
        user_prompt = f"""任务 ID：{state.task_id}
用户需求：{state.user_text}
当前短摘要：{state.summary}
已联系过的角色：{', '.join(state.contacted_roles) or '无'}
可调度角色与真实用户名：
{role_directory}
新收到的信息：{incoming}

请输出：
TARGET_ROLE: Planner/Researcher/Developer/Tester/DONE
MESSAGE: 你要发到群里的调度消息。如果 TARGET_ROLE 不是 DONE，必须包含任务 ID，并 @目标角色的真实 username
HANDOFF_SUMMARY: 300 字以内交接摘要

{ARTIFACT_INSTRUCTIONS}
"""
        try:
            raw = await self.complete_role("Supervisor", system_prompt, user_prompt)
            target_role, message, summary = parse_manager_output(raw, fallback_role)
            message = replace_role_mentions(message, self.usernames)
            state.summary = summary
            if target_role == "DONE":
                state.completed = True
                message = f"[{state.task_id}][Supervisor][DONE]\n{message}"
            return ManagerDecision(target_role=target_role, message=message, handoff_summary=summary)
        except Exception as exc:
            if fallback_role == "DONE":
                return ManagerDecision(
                    target_role="ERROR",
                    message=(
                        f"[{state.task_id}][Supervisor][ERROR]\n"
                        f"调度异常，任务没有被标记为完成。\n\n"
                        f"当前交接摘要：{state.summary}\n"
                        f"错误类型：{type(exc).__name__}\n"
                        f"建议：稍后让 Supervisor 继续调度，或重新发送 /new。"
                    ),
                    handoff_summary=state.summary,
                )
            target_username = self.usernames[fallback_role]
            return ManagerDecision(
                target_role=fallback_role,
                message=(
                    f"[{state.task_id}][Supervisor][ASSIGN]\n"
                    f"@{target_username} 请处理这个阶段。\n\n"
                    f"任务：{state.user_text}\n"
                    f"交接摘要：{state.summary}"
                ),
                handoff_summary=state.summary,
            )

    async def send_manager_decision(self, task_id: str, decision: ManagerDecision) -> None:
        role = decision.target_role
        message = decision.message
        state = self.tasks.get(task_id)
        if role in {"DONE", "ERROR"}:
            if state is not None:
                state.current_role = "Supervisor"
                state.status = "done" if role == "DONE" else "error"
                await self.send_task_status(
                    state,
                    "任务已完成。" if role == "DONE" else "任务出现错误。",
                    decision.handoff_summary,
                )
            self.write_role_markdown(task_id, "Supervisor", role.lower(), message, decision.handoff_summary, state)
            await self.send_as("Supervisor", message)
            return
        if state is not None:
            state.current_role = role
            state.status = "assigned"
        username = self.usernames[role]
        message = replace_role_mentions(message, self.usernames).strip()
        if not message:
            message = f"@{username} 请根据任务 {task_id} 和当前交接摘要继续处理。"
        status_block = "\n".join(
            [
                "",
                "手机状态：",
                f"- 当前处理人：{role}",
                "- 状态：已派单，等待回报",
                f"- 交接摘要：{compact(decision.handoff_summary, 220)}",
            ]
        )
        if "手机状态：" not in message:
            message = f"{message}\n{status_block}"
        text = message if f"@{username}" in message else f"@{username}\n{message}"
        if not is_supervisor_assignment(text) or extract_task_id(text) != task_id:
            text = strip_supervisor_header(text)
            text = f"[{task_id}][Supervisor][ASSIGN]\n{text}"
        if state is not None:
            await self.send_task_status(state, f"已派给 {role}，等待回报。", decision.handoff_summary)
        self.write_role_markdown(task_id, "Supervisor", f"assign-{role.lower()}", text, decision.handoff_summary, state)
        await self.send_as("Supervisor", text)

    async def worker_reply(self, role: str, text: str) -> None:
        task_id = extract_task_id(text)
        if not task_id:
            return
        state = self.tasks.setdefault(
            task_id,
            TaskState(task_id=task_id, user_text="未知任务", summary=compact(text, 500)),
        )
        state.current_role = role
        state.status = "working"
        await self.send_task_status(state, f"{role} 已收到派单，正在处理。")
        system_prompt = (
            f"你是 Telegram AI Team 的 {role}。{ROLES[role].description}"
            f"你的专属能力配置：{role_capability_text(role)}"
            f"你被 Supervisor @ 到后，只完成自己这一段，并 @{self.usernames['Supervisor']} 回复。"
            "不要 @、指挥、安排 Planner、Researcher、Developer、Tester 中的任何其他 worker。"
            f"回复中唯一允许 @ 的对象是 @{self.usernames['Supervisor']}。"
            "不要安排其他角色，不要输出完整历史。"
            "如果需要提出下一步建议，只能写成“供 Supervisor 决策参考”，不能使用像你在调度团队的口吻。"
            "如果任务需要真实 MCP/工具调用，但当前对话没有提供工具结果，你必须标注为“待执行/待验证”，不能编造成已完成。"
            "群聊消息只是可见工作台；你的实质产出也会落盘到工作目录。"
        )
        user_prompt = f"""任务 ID：{task_id}
用户需求：{state.user_text}
当前短交接摘要：{state.summary}
Supervisor 刚发给你的消息：{text}

请输出：
MESSAGE: 发到 Telegram 群里的正文，必须包含任务 ID，并 @{self.usernames['Supervisor']}
HANDOFF_SUMMARY: 300 字以内给 Supervisor 的交接摘要

{ARTIFACT_INSTRUCTIONS}
"""
        try:
            repair_prompt = user_prompt
            last_violation = ""
            for attempt in range(2):
                raw = await self.complete_role(role, system_prompt, repair_prompt)
                visible, summary = parse_worker_output(raw)
                visible, violation = self.prepare_worker_report(role, task_id, visible)
                if violation is None:
                    break
                last_violation = violation
                repair_prompt = f"""你的上一版输出被 Telegram 出站规则拦截，不能发送到群里。

违规原因：{violation}

请重新输出，并严格遵守：
- MESSAGE 必须是给 Supervisor 的 REPORT，不得是 WORKING、STATUS、ASSIGN、DONE 或 ERROR；
- MESSAGE 开头必须是 [{task_id}][{role}][REPORT]；
- MESSAGE 只能 @{self.usernames['Supervisor']}，不能 @其他 worker；
- 你可以给 Supervisor 提建议，但不能像经理一样安排、调度其他 worker。

原始派单：
{text}

请重新输出：
MESSAGE: ...
HANDOFF_SUMMARY: ...
"""
            else:
                raise RuntimeError(f"{role} output failed outbound validation after retry: {last_violation}")
        except Exception as exc:
            summary = f"{role} 已完成本地 fallback 响应。收到的任务摘要：{compact(text, 350)}"
            visible = (
                f"[{task_id}][{role}][REPORT]\n"
                f"@{self.usernames['Supervisor']} {role} 收到调度。\n\n"
                f"本地 fallback 输出：{summary}\n"
                f"模型不可用：{type(exc).__name__}"
            )
        state.summary = summary
        state.status = "reported"
        if role not in state.contacted_roles:
            state.contacted_roles.append(role)
        visible, _violation = self.prepare_worker_report(role, task_id, visible)
        self.write_role_markdown(task_id, role, "report", visible, summary, state)
        await self.send_as(role, visible)

    async def manager_receive_report(self, text: str) -> None:
        task_id = extract_task_id(text)
        if not task_id:
            return
        state = self.tasks.setdefault(
            task_id,
            TaskState(task_id=task_id, user_text="未知任务", summary=compact(text, 500)),
        )
        if state.completed:
            print(f"ignore report for completed task {task_id}", flush=True)
            return
        report_role = extract_report_role(text) or "Worker"
        state.current_role = "Supervisor"
        state.status = f"reviewing {report_role} report"
        await self.send_task_status(state, f"已收到 {report_role} 回报。Supervisor 正在判断下一步。")
        state.turns += 1
        decision = await self.manager_decide(state, incoming=text, fallback_role="DONE")
        await self.send_manager_decision(task_id, decision)

    async def process_update(self, role: str, update: Update) -> None:
        message = update.effective_message
        chat = update.effective_chat
        user = update.effective_user
        if message is None or chat is None or chat.id != self.group_chat_id:
            return
        text = message.text or message.caption or ""
        if not text.strip():
            return

        if role == "Supervisor":
            if user is not None and user.is_bot:
                if self.is_mentioned("Supervisor", text) and not is_from_role(user.id, "Supervisor", self.user_ids):
                    await self.manager_receive_report(text)
                return

            name = command_name(text)
            if name in {"/help", "/start"}:
                role_help = "\n".join(
                    f"- {role}: @{self.usernames[role]}"
                    for role in WORKER_ROLES
                )
                await self.send_as(
                    "Supervisor",
                    "Bot-to-Bot 版本用法：\n"
                    "/new 你的任务\n"
                    "/status 查看当前谁在处理什么\n"
                    "你只需要把任务交给经理，经理会自行决定调度谁。\n\n"
                    f"可调度角色：\n{role_help}",
                )
                return
            if name == "/status":
                await self.send_all_status()
                return
            if name == "/new" or text.startswith("新任务") or self.is_mentioned("Supervisor", text):
                await self.manager_start_task(clean_user_text(text, self.usernames["Supervisor"]))
            return

        if (
            self.is_mentioned(role, text)
            and is_supervisor_assignment(text)
            and is_from_role(user.id if user else None, "Supervisor", self.user_ids)
        ):
            await self.worker_reply(role, text)

    async def poll_role(self, role: str) -> None:
        bot = self.bots[role]
        offset = None
        while offset is None:
            try:
                old_updates = await bot.get_updates(timeout=0, allowed_updates=Update.ALL_TYPES)
                offset = old_updates[-1].update_id + 1 if old_updates else 0
            except (TimedOut, NetworkError, TelegramError) as exc:
                print(f"{role} polling init retry after {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(5)
            except Exception as exc:
                print(f"{role} polling init unexpected error {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(10)
        print(f"{role} polling ready at {now_text()}", flush=True)

        while True:
            try:
                updates = await bot.get_updates(
                    offset=offset,
                    timeout=10,
                    allowed_updates=Update.ALL_TYPES,
                )
            except (TimedOut, NetworkError, TelegramError) as exc:
                print(f"{role} polling reconnect after {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(3)
                continue
            except Exception as exc:
                print(f"{role} polling unexpected error {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(10)
                continue
            for update in updates:
                offset = update.update_id + 1
                try:
                    await self.process_update(role, update)
                except Exception as exc:
                    print(f"{role} update handling failed after {type(exc).__name__}: {exc}", flush=True)

    async def run(self) -> None:
        await self.initialize()
        await self.send_as(
            "Supervisor",
            "[SYSTEM][Supervisor][ONLINE]\nBot-to-Bot 经理调度版已启动。发送 /new 你的任务 开始。",
        )
        tasks = [asyncio.create_task(self.poll_role(role)) for role in ROLES]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for role, result in zip(ROLES, results):
                if isinstance(result, Exception):
                    print(f"{role} polling task exited unexpectedly: {type(result).__name__}: {result}", flush=True)
        finally:
            for task in tasks:
                task.cancel()
            await self.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bot-to-bot Telegram AI team service.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(Path(args.env_file))
    lock_path = Path(os.environ.get("SERVICE_LOCK_FILE", "data/bot2bot.lock"))
    if not lock_path.is_absolute():
        lock_path = Path(__file__).resolve().parent / lock_path
    lock_file = acquire_process_lock(lock_path)
    group_chat_id = int(require_env("GROUP_CHAT_ID"))
    team = BotToBotTeam(group_chat_id=group_chat_id, timeout=args.timeout)
    try:
        asyncio.run(team.run())
    except KeyboardInterrupt:
        print("Bot-to-Bot team stopped.")
    finally:
        lock_file.close()


if __name__ == "__main__":
    main()
