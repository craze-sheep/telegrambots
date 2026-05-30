#!/usr/bin/env python3
"""Bot-to-bot Telegram AI team service."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx
from telegram import Bot, Update
from telegram.error import NetworkError, TelegramError, TimedOut

from .config import (
    BOT_TOKEN_RE,
    DEFAULT_AI_API_BASE_URL,
    DEFAULT_AI_API_MODE,
    DEFAULT_AI_MODEL,
    DEFAULT_AI_PROVIDER,
    DEFAULT_COMPLETED_TASK_MEMORY_LIMIT,
    DEFAULT_ENV_FILE,
    DEFAULT_POLL_INIT_MAX_RETRIES,
    MIN_REPORT_BODY_CHARS,
    PROJECT_DIR,
    TZ,
    WORKER_ROLES,
    env_int,
    load_dotenv,
    make_request,
    require_env,
    require_int_env,
)
from .files import (
    ARTIFACT_INSTRUCTIONS,
    acquire_process_lock,
    extract_file_blocks,
    sanitize_label,
)
from .llm import OpenAICompatibleClient, TmuxHermesClient
from .models import ManagerDecision, RoleConfig, TaskState
from .roles import ROLES, role_capability_text
from .text_utils import (
    clean_user_text,
    command_name,
    compact,
    elide_repeated_task_text,
    extract_report_role,
    extract_requested_work_dir,
    extract_task_id,
    is_from_role,
    is_supervisor_assignment,
    is_worker_report,
    make_task_id,
    normalize_manager_message,
    now_text,
    parse_manager_output,
    parse_worker_output,
    remove_worker_mentions,
    replace_role_mentions,
    task_reference,
    strip_fenced_code,
    task_has_deliverables,
    text_stats,
    worker_report_body,
)


class BotToBotTeam:
    def __init__(self, group_chat_id: int, timeout: float) -> None:
        self.group_chat_id = group_chat_id
        self.timeout = timeout
        self.client = OpenAICompatibleClient()
        self.project_dir = PROJECT_DIR
        self.bots: dict[str, Bot] = {}
        self.usernames: dict[str, str] = {}
        self.user_ids: dict[str, int] = {}
        self.tasks: dict[str, TaskState] = {}
        artifacts_dir = Path(os.environ.get("ARTIFACTS_DIR", "artifacts")).expanduser()
        self.artifacts_dir = artifacts_dir if artifacts_dir.is_absolute() else (PROJECT_DIR / artifacts_dir).resolve()
        self.artifact_sequence: dict[str, int] = {}
        self.poll_init_max_retries = env_int("TELEGRAM_POLL_INIT_MAX_RETRIES", DEFAULT_POLL_INIT_MAX_RETRIES, minimum=1)
        self.completed_task_memory_limit = env_int(
            "COMPLETED_TASK_MEMORY_LIMIT",
            DEFAULT_COMPLETED_TASK_MEMORY_LIMIT,
            minimum=1,
        )
        self.agent_backend = os.environ.get("AGENT_BACKEND", "tmux_hermes").strip().lower()
        self.tmux_client = TmuxHermesClient(self.project_dir, self.artifacts_dir)

    async def initialize_role_bot(self, role: str, config: RoleConfig) -> None:
        token = require_env(config.token_env, BOT_TOKEN_RE)
        attempt = 0
        while True:
            attempt += 1
            bot = Bot(token, request=make_request(self.timeout))
            try:
                await bot.initialize()
                me = await bot.get_me()
            except (TimedOut, NetworkError) as exc:
                print(
                    f"{role} initialize retry after {type(exc).__name__} "
                    f"(attempt {attempt}): {exc}",
                    flush=True,
                )
                try:
                    await bot.shutdown()
                except Exception:
                    pass
                await asyncio.sleep(min(30, 3 * attempt))
                continue
            except TelegramError:
                try:
                    await bot.shutdown()
                except Exception:
                    pass
                raise

            self.bots[role] = bot
            self.usernames[role] = me.username or ""
            self.user_ids[role] = me.id
            print(f"{role}: @{self.usernames[role]}", flush=True)
            return

    async def complete_role(self, role: str, system_prompt: str, user_prompt: str) -> str:
        if self.agent_backend == "tmux_hermes":
            try:
                return await self.tmux_client.complete(role, system_prompt, user_prompt)
            except Exception as exc:
                print(f"{role} tmux Hermes fallback to direct LLM after {type(exc).__name__}: {exc}", flush=True)
        return await self.client.complete(system_prompt, user_prompt)


    async def initialize(self) -> None:
        print(f"Direct LLM API: {self.client.describe()}", flush=True)
        print(
            "Xiaomi API defaults: "
            f"AI_PROVIDER={DEFAULT_AI_PROVIDER}, "
            f"AI_API_BASE_URL={DEFAULT_AI_API_BASE_URL}, "
            f"AI_API_MODE={DEFAULT_AI_API_MODE}, "
            f"AI_MODEL={DEFAULT_AI_MODEL}",
            flush=True,
        )
        for role, config in ROLES.items():
            await self.initialize_role_bot(role, config)

    async def shutdown(self) -> None:
        for bot in self.bots.values():
            await bot.shutdown()

    def is_mentioned(self, role: str, text: str) -> bool:
        username = self.usernames.get(role, "")
        return bool(username and re.search(rf"@{re.escape(username)}\b", text, flags=re.I))

    def task_artifact_dir(self, task_id: str) -> Path:
        return self.artifacts_dir / "tasks" / task_id

    def task_state_path(self, task_id: str) -> Path:
        return self.task_artifact_dir(task_id) / "state.json"

    def save_task_state(self, state: TaskState) -> None:
        task_dir = self.task_artifact_dir(state.task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        self.task_state_path(state.task_id).write_text(
            json.dumps(asdict(state), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def load_task_state(self, task_id: str) -> TaskState | None:
        path = self.task_state_path(task_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("state payload is not an object")
            contacted = data.get("contacted_roles") or []
            if not isinstance(contacted, list):
                contacted = []
            turns = data.get("turns")
            if not isinstance(turns, int):
                turns = 0
            completed = data.get("completed")
            if not isinstance(completed, bool):
                completed = False
            user_text = data.get("user_text")
            summary = data.get("summary")
            work_dir = data.get("work_dir")
            current_role = data.get("current_role")
            status = data.get("status")
            return TaskState(
                task_id=data.get("task_id") if isinstance(data.get("task_id"), str) else task_id,
                user_text=user_text if isinstance(user_text, str) and user_text else "未知任务",
                summary=summary if isinstance(summary, str) else "",
                work_dir=work_dir if isinstance(work_dir, str) else None,
                turns=turns,
                completed=completed,
                current_role=current_role if isinstance(current_role, str) and current_role else "Supervisor",
                status=status if isinstance(status, str) and status else "created",
                contacted_roles=[str(role) for role in contacted],
            )
        except Exception as exc:
            print(f"failed to load task state {path}: {type(exc).__name__}: {exc}", flush=True)
            return None

    def get_or_create_task_state(self, task_id: str, text: str, work_dir: str | None = None) -> TaskState:
        state = self.tasks.get(task_id)
        if state is None:
            state = self.load_task_state(task_id)
        if state is None:
            state = TaskState(
                task_id=task_id,
                user_text="未知任务",
                summary=compact(text, 500),
                work_dir=work_dir,
            )
        elif state.work_dir is None and work_dir:
            state.work_dir = work_dir
        self.tasks[task_id] = state
        return state

    def remember_task_state(self, state: TaskState) -> None:
        self.tasks[state.task_id] = state
        self.save_task_state(state)
        self.prune_completed_tasks()

    def prune_completed_tasks(self) -> None:
        completed = [state for state in self.tasks.values() if state.completed]
        if len(completed) <= self.completed_task_memory_limit:
            return
        completed.sort(key=lambda item: item.task_id)
        for state in completed[: len(completed) - self.completed_task_memory_limit]:
            self.tasks.pop(state.task_id, None)
            self.artifact_sequence.pop(state.task_id, None)

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
                    f"- Work dir: {state.work_dir or 'artifacts task directory'}",
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

    def write_code_files(self, task_id: str, role: str, message: str, state: TaskState | None) -> list[str]:
        extracted = extract_file_blocks(message)
        if not extracted:
            return []
        if state is not None and state.work_dir:
            files_root = Path(state.work_dir).expanduser().resolve()
            display_root = files_root
        else:
            files_root = (self.task_artifact_dir(task_id) / "files").resolve()
            display_root = Path("files")
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
            written.append(str(display_root / Path(*rel_path.parts)))
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
        message = elide_repeated_task_text(message, state)
        written_files = self.write_code_files(task_id, role, message, state)
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
                    "## Task Context",
                    "",
                    task_reference(state),
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
            f"摘要：{compact(state.summary, 120)}",
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
                    f"  摘要：{compact(state.summary, 90)}",
                ]
            )
        return "\n".join(lines)

    async def send_all_status(self) -> None:
        await self.send_as("Supervisor", self.build_all_status())

    def worker_outbound_violation(self, role: str, task_id: str, text: str) -> str | None:
        stripped = text.strip()
        body = worker_report_body(role, stripped)
        checked_text = strip_fenced_code(stripped)
        checked_body = strip_fenced_code(body)
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

        if re.search(r"\[(WORKING|STATUS|ASSIGN|DONE|ERROR)\]", checked_text, flags=re.I):
            if not is_worker_report(role, stripped):
                return "worker 不能发送 WORKING/STATUS/ASSIGN/DONE/ERROR 类型消息，只能发送 REPORT。"
        if re.search(r"(?im)^\s*(WORKING|STATUS|ASSIGN|DONE|ERROR|TARGET_ROLE)\s*[:：]", checked_text):
            return "worker REPORT 正文不能包含 WORKING/STATUS/ASSIGN/DONE/ERROR/TARGET_ROLE 标签。"

        checked_body = re.sub(rf"@{re.escape(self.usernames.get('Supervisor', ''))}\b", "", checked_body, flags=re.I).strip()
        if len(checked_body) < MIN_REPORT_BODY_CHARS:
            return f"worker REPORT 正文过短，至少需要 {MIN_REPORT_BODY_CHARS} 个字符的实质内容。"

        other_roles = [other_role for other_role in WORKER_ROLES if other_role != role]
        role_pattern = "|".join(re.escape(other_role) for other_role in other_roles)
        directive_patterns = (
            rf"(?:下一步|后续|之后|现在|请|需要|应该|必须|交给|调度|安排|转给|派给|让|由)\s*(?:{role_pattern})\s*(?:执行|处理|继续|负责|完成|开始|接手|实现|调研|测试|开发)",
            rf"(?:{role_pattern})\s*(?:请|需要|应该|必须|负责|执行|处理|继续|接手|完成|开始|实现|调研|测试|开发)",
            rf"负责人\s*[:：]\s*(?:{role_pattern})",
        )
        for pattern in directive_patterns:
            for match in re.finditer(pattern, checked_text, flags=re.I):
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
                "你是谁",
                "你是什么",
                "你是什么人",
                "自我介绍",
                "介绍一下你自己",
                "whoareyou",
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

    def is_invalid_job_prompt_complaint(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text.lower())
        return any(
            keyword in normalized
            for keyword in (
                "任务json不完整",
                "json不完整",
                "user_prompt缺失",
                "userprompt缺失",
                "role_contract后内容缺失",
            )
        )

    async def manager_start_task(self, user_text: str) -> None:
        task_id = make_task_id()
        work_dir = extract_requested_work_dir(user_text)
        work_dir_note = f"工作目录：{work_dir}。" if work_dir else ""
        state = TaskState(
            task_id=task_id,
            user_text=user_text,
            summary=f"用户需求：{compact(user_text, 500)} {work_dir_note}".strip(),
            work_dir=work_dir,
        )
        self.tasks[task_id] = state
        self.ensure_task_readme(state)
        self.remember_task_state(state)
        await self.send_task_status(state, "任务已创建。Supervisor 正在判断下一步。")
        if self.should_answer_team_intro_locally(user_text):
            state.completed = True
            state.status = "done"
            self.remember_task_state(state)
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
真实工作目录：{state.work_dir or '未指定；使用 artifacts/tasks/<task_id>/files 作为草稿区'}
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
            if self.is_invalid_job_prompt_complaint(f"{message}\n{summary}"):
                raise RuntimeError("Supervisor reported an incomplete internal job prompt")
            state.summary = summary
            if target_role == "DONE":
                state.completed = True
            self.remember_task_state(state)
            return ManagerDecision(target_role=target_role, message=message, handoff_summary=summary)
        except asyncio.CancelledError:
            raise
        except (RuntimeError, TimeoutError, httpx.HTTPError) as exc:
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
                    f"@{target_username} 请处理任务 {state.task_id} 的当前阶段。\n"
                    f"真实工作目录：{state.work_dir or 'artifacts/tasks/<task_id>/files 草稿区'}\n"
                    f"交接摘要：{state.summary}"
                ),
                handoff_summary=state.summary,
            )

    async def send_manager_decision(self, task_id: str, decision: ManagerDecision) -> None:
        role = decision.target_role
        state = self.tasks.get(task_id)
        message = elide_repeated_task_text(decision.message, state)
        if role in {"DONE", "ERROR"}:
            message = normalize_manager_message(task_id, role, message, self.usernames)
            if state is not None:
                state.current_role = "Supervisor"
                state.status = "done" if role == "DONE" else "error"
                state.completed = role == "DONE"
                self.remember_task_state(state)
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
            self.remember_task_state(state)
        username = self.usernames[role]
        if not message:
            message = f"@{username} 请根据任务 {task_id} 和当前交接摘要继续处理。"
        status_block = "\n".join(
            [
                "",
                "手机状态：",
                f"- 当前处理人：{role}",
                "- 状态：已派单，等待回报",
                f"- 真实工作目录：{state.work_dir if state and state.work_dir else 'artifacts/tasks/<task_id>/files 草稿区'}",
                f"- 交接摘要：{compact(decision.handoff_summary, 220)}",
            ]
        )
        if "手机状态：" not in message:
            message = f"{message}\n{status_block}"
        text = normalize_manager_message(task_id, role, message, self.usernames)
        if state is not None:
            await self.send_task_status(state, f"已派给 {role}，等待回报。", decision.handoff_summary)
        self.write_role_markdown(task_id, "Supervisor", f"assign-{role.lower()}", text, decision.handoff_summary, state)
        await self.send_as("Supervisor", text)

    async def worker_reply(self, role: str, text: str) -> None:
        task_id = extract_task_id(text)
        if not task_id:
            return
        inferred_work_dir = extract_requested_work_dir(text)
        state = self.get_or_create_task_state(task_id, text, inferred_work_dir)
        if state.work_dir is None:
            state.work_dir = inferred_work_dir or extract_requested_work_dir(state.user_text)
        state.current_role = role
        state.status = "working"
        self.remember_task_state(state)
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
真实工作目录：{state.work_dir or '未指定；使用 artifacts/tasks/<task_id>/files 作为草稿区'}
Supervisor 刚发给你的消息：{text}

请输出：
MESSAGE: 发到 Telegram 群里的正文，必须包含任务 ID，并 @{self.usernames['Supervisor']}
HANDOFF_SUMMARY: 300 字以内给 Supervisor 的交接摘要

{ARTIFACT_INSTRUCTIONS}
注意：如果真实工作目录已指定，实质产出应写入该工作目录；不要把 artifacts/tasks 当成最终交付目录。
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.status = "error"
            summary = f"{role} 模型调用或出站校验失败，未产生有效 REPORT；错误类型：{type(exc).__name__}"
            self.remember_task_state(state)
            task_dir = self.task_artifact_dir(task_id)
            if task_dir.exists() and not task_has_deliverables(task_dir, state.work_dir):
                print(
                    f"removing empty failed task artifact: {task_dir}; {text_stats(task_dir)}",
                    flush=True,
                )
                shutil.rmtree(task_dir)
                print(f"empty failed task artifact removed: {task_dir}", flush=True)
            visible = (
                f"[{task_id}][Supervisor][ERROR]\n"
                f"{role} 未产生有效输出，本次 worker 结果未按成功 REPORT 记录。\n"
                f"错误类型：{type(exc).__name__}\n"
                f"真实工作目录：{state.work_dir or '未指定'}"
            )
            try:
                await self.send_as("Supervisor", visible)
            except (TimedOut, NetworkError, TelegramError) as send_exc:
                print(
                    f"failed to send worker error notification for {task_id}: "
                    f"{type(send_exc).__name__}: {send_exc}",
                    flush=True,
                )
            return
        state.summary = summary
        state.status = "reported"
        if role not in state.contacted_roles:
            state.contacted_roles.append(role)
        self.remember_task_state(state)
        visible, _violation = self.prepare_worker_report(role, task_id, visible)
        self.write_role_markdown(task_id, role, "report", visible, summary, state)
        await self.send_as(role, visible)

    async def manager_receive_report(self, text: str) -> None:
        task_id = extract_task_id(text)
        if not task_id:
            return
        inferred_work_dir = extract_requested_work_dir(text)
        state = self.get_or_create_task_state(task_id, text, inferred_work_dir)
        if state.work_dir is None:
            state.work_dir = inferred_work_dir or extract_requested_work_dir(state.user_text)
        if state.completed:
            print(f"ignore report for completed task {task_id}", flush=True)
            return
        report_role = extract_report_role(text) or "Worker"
        state.current_role = "Supervisor"
        state.status = f"reviewing {report_role} report"
        await self.send_task_status(state, f"已收到 {report_role} 回报。Supervisor 正在判断下一步。")
        state.turns += 1
        self.remember_task_state(state)
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
        init_attempt = 0
        while offset is None:
            init_attempt += 1
            try:
                old_updates = await bot.get_updates(timeout=0, allowed_updates=Update.ALL_TYPES)
                offset = old_updates[-1].update_id + 1 if old_updates else 0
            except (TimedOut, NetworkError, TelegramError) as exc:
                if init_attempt >= self.poll_init_max_retries:
                    raise RuntimeError(
                        f"{role} polling initialization failed after {init_attempt} attempts: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
                print(f"{role} polling init retry after {type(exc).__name__}: {exc}", flush=True)
                await asyncio.sleep(5)
            except Exception as exc:
                if init_attempt >= self.poll_init_max_retries:
                    raise RuntimeError(
                        f"{role} polling initialization failed after {init_attempt} unexpected errors: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
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
        try:
            await self.send_as(
                "Supervisor",
                "[SYSTEM][Supervisor][ONLINE]\nBot-to-Bot 经理调度版已启动。发送 /new 你的任务 开始。",
            )
        except (TimedOut, NetworkError, TelegramError) as exc:
            print(f"Startup online message skipped after {type(exc).__name__}: {exc}", flush=True)
        tasks = [asyncio.create_task(self.poll_role(role)) for role in ROLES]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for task, role in zip(tasks, ROLES):
                if task in done:
                    if task.cancelled():
                        print(f"{role} polling task was cancelled.", flush=True)
                        continue
                    result = task.exception()
                    if result is not None:
                        print(f"{role} polling task exited unexpectedly: {type(result).__name__}: {result}", flush=True)
                        raise RuntimeError(f"{role} polling task failed") from result
                    print(f"{role} polling task exited unexpectedly without an exception.", flush=True)
        finally:
            for task in tasks:
                task.cancel()
            await self.shutdown()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run bot-to-bot Telegram AI team service.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env_path = Path(args.env_file).expanduser()
    if not env_path.is_absolute():
        env_path = PROJECT_DIR / env_path
    load_dotenv(env_path)
    lock_path = Path(os.environ.get("SERVICE_LOCK_FILE", "data/bot2bot.lock"))
    if not lock_path.is_absolute():
        lock_path = PROJECT_DIR / lock_path
    lock_file = acquire_process_lock(lock_path)
    group_chat_id = require_int_env("GROUP_CHAT_ID")
    team = BotToBotTeam(group_chat_id=group_chat_id, timeout=args.timeout)
    try:
        asyncio.run(team.run())
    except KeyboardInterrupt:
        print("Bot-to-Bot team stopped.")
    finally:
        lock_file.close()


if __name__ == "__main__":
    main()
