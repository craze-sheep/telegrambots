from __future__ import annotations

from dataclasses import dataclass, field


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
    work_dir: str | None = None
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


