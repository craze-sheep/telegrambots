from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx

from .config import (
    DEFAULT_AI_API_BASE_URL,
    DEFAULT_AI_API_MODE,
    DEFAULT_AI_MODEL,
    DEFAULT_AI_PROVIDER,
    DEFAULT_AI_TIMEOUT,
    DEFAULT_ENV_FILE,
    TZ,
)
from .files import extract_marked_response
from .roles import ROLES


class OpenAICompatibleClient:
    def __init__(self) -> None:
        self.provider = os.environ.get("AI_PROVIDER", DEFAULT_AI_PROVIDER).strip() or DEFAULT_AI_PROVIDER
        self.base_url = (os.environ.get("AI_API_BASE_URL", DEFAULT_AI_API_BASE_URL).strip() or DEFAULT_AI_API_BASE_URL).rstrip("/")
        self.model = os.environ.get("AI_MODEL", DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL
        self.api_mode = os.environ.get("AI_API_MODE", DEFAULT_AI_API_MODE).strip() or DEFAULT_AI_API_MODE
        self.api_key_source = str(DEFAULT_ENV_FILE)
        self.api_key = os.environ.get("AI_API_KEY", "").strip()
        self.timeout = float(os.environ.get("AI_TIMEOUT", DEFAULT_AI_TIMEOUT))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key) and self.api_mode == "chat_completions"

    def describe(self) -> str:
        key_state = f"loaded from {self.api_key_source}" if self.api_key else f"missing from {self.api_key_source}"
        return (
            f"provider={self.provider}, model={self.model}, mode={self.api_mode}, "
            f"base_url={self.base_url}, timeout={self.timeout:g}s, api_key={key_state}"
        )

    async def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        if not self.enabled:
            raise RuntimeError(
                "OpenAI-compatible API is not available: "
                f"{self.describe()}. Expected Xiaomi defaults: "
                f"AI_PROVIDER={DEFAULT_AI_PROVIDER}, "
                f"AI_API_BASE_URL={DEFAULT_AI_API_BASE_URL}, "
                f"AI_API_MODE={DEFAULT_AI_API_MODE}, "
                f"AI_MODEL={DEFAULT_AI_MODEL}."
            )

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

    def build_job_payload(self, role: str, job_id: str, system_prompt: str, user_prompt: str) -> dict[str, object]:
        config = ROLES[role]
        return {
            "job_id": job_id,
            "role": role,
            "role_description": config.description,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
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
        }

    def build_job_prompt(self, role: str, job_id: str, job_path: Path) -> str:
        start_marker = f"<<<B2B_RESPONSE:{job_id}>>>"
        done_marker = f"<<<B2B_DONE:{job_id}>>>"
        role_prompt_path = self.project_dir / "artifacts" / "hermes-role-prompts" / f"{role.lower()}.md"
        return (
            "请处理这个 Telegram AI Team 任务。\n"
            f"任务文件(JSON)：{job_path}\n"
            f"角色契约文件(已在会话启动时注入，仅作参考)：{role_prompt_path}\n"
            f"项目目录：{self.project_dir}\n\n"
            "不要把这条路径提示当成用户任务；请读取任务文件中的 system_prompt 和 user_prompt 后再执行。\n"
            f"先单独输出 {start_marker}，然后输出最终答案，最后单独输出 {done_marker}。\n"
            "不要在结束标记后输出任何内容。"
        )

    async def complete(self, role: str, system_prompt: str, user_prompt: str) -> str:
        async with self.locks[role]:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + self.timeout
            await asyncio.wait_for(self.ensure_session(role), timeout=self.timeout)
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"Hermes tmux job timed out while starting session for {role}")
            session = self.session_name(role)
            job_id = f"{role.lower()}-{datetime.now(TZ).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:16]}"
            start_marker = f"<<<B2B_RESPONSE:{job_id}>>>"
            done_marker = f"<<<B2B_DONE:{job_id}>>>"
            jobs_dir = self.artifacts_dir / "tmux-jobs"
            jobs_dir.mkdir(parents=True, exist_ok=True)
            payload = self.build_job_payload(role, job_id, system_prompt, user_prompt)
            job_path = jobs_dir / f"{job_id}.job.json"
            job_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            prompt = self.build_job_prompt(role, job_id, job_path)
            prompt_path = jobs_dir / f"{job_id}.prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")

            buffer_name = f"b2b-{job_id}"
            await self.run_tmux("send-keys", "-t", session, "C-l")
            await self.run_tmux("clear-history", "-t", session)
            await self.run_tmux("load-buffer", "-b", buffer_name, str(prompt_path))
            await self.run_tmux("paste-buffer", "-b", buffer_name, "-t", session)
            await self.run_tmux("send-keys", "-t", session, "Enter")

            captured = ""
            while loop.time() < deadline:
                await asyncio.sleep(self.poll_interval)
                captured = await self.run_tmux("capture-pane", "-p", "-S", "-5000", "-t", session)
                response = extract_marked_response(captured, start_marker, done_marker)
                if response is not None:
                    return response

            timeout_path = jobs_dir / f"{job_id}.timeout-capture.txt"
            timeout_path.write_text(captured, encoding="utf-8")
            raise TimeoutError(f"Hermes tmux job timed out for {role}; capture saved to {timeout_path}")
