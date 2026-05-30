from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .config import HANDOFF_SUMMARY_MAX_CHARS, TZ, WORKER_ROLES
from .models import TaskState


def now_text() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def make_task_id() -> str:
    return f"B2B-{datetime.now(TZ).strftime('%Y%m%d-%H%M%S')}"


def compact(text: str, max_chars: int = 900) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def task_reference(state: TaskState | None) -> str:
    if state is None:
        return "未知任务"
    parts = [f"Task: {state.task_id}", "完整需求见本 task 的 README.md"]
    if state.work_dir:
        parts.append(f"真实工作目录：{state.work_dir}")
    return "\n".join(parts)


def elide_repeated_task_text(text: str, state: TaskState | None) -> str:
    if state is None or not state.user_text or state.user_text == "未知任务":
        return text
    replacement = f"完整需求见 {state.task_id} README.md"
    text = text.replace(state.user_text, replacement)
    compacted_task = compact(state.user_text, 500)
    if compacted_task != state.user_text:
        text = text.replace(compacted_task, replacement)
    return text


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


def extract_requested_work_dir(text: str) -> str | None:
    patterns = (
        r"(?:工作目录|输出目录|保存目录)\s*(?:是|为|[:：])?\s*([/][^\s，。；;、]+)",
        r"(?:放入|保存到|下载到|clone到|拉取到)\s*([/][^\s，。；;、]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        raw = match.group(1).strip().rstrip("，。；;、)")
        path = Path(raw).expanduser()
        if path.is_absolute():
            return str(path)
    return None


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
    return target_role, (message or text).strip(), compact(summary or message or text, HANDOFF_SUMMARY_MAX_CHARS)


def parse_worker_output(text: str) -> tuple[str, str]:
    message = extract_section(text, ("MESSAGE", "消息"))
    summary = extract_section(text, ("HANDOFF_SUMMARY", "交接摘要"))
    visible = (message or text).strip()
    return visible, compact(summary or visible, HANDOFF_SUMMARY_MAX_CHARS)


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


def repair_split_usernames(text: str, usernames: dict[str, str]) -> str:
    """Repair model/tmux line wraps that split a Telegram @username."""
    for username in sorted((value for value in usernames.values() if value), key=len, reverse=True):
        if len(username) < 6:
            continue
        pattern = "@" + r"\s*".join(re.escape(char) for char in username)
        text = re.sub(pattern, f"@{username}", text, flags=re.I)
    return text


def strip_fenced_code(text: str) -> str:
    return re.sub(r"(?ms)^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^(?P=fence)\s*$", "", text)


def worker_report_body(role: str, text: str) -> str:
    return re.sub(
        rf"(?is)^\s*\[B2B-\d{{8}}-\d{{6}}\]\[{re.escape(role)}\]\[REPORT\]\s*",
        "",
        text,
        count=1,
    ).strip()


def text_stats(root: Path, max_entries: int = 6) -> str:
    if not root.exists():
        return "missing"
    entries = []
    total_files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        total_files += 1
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        total_bytes += size
        if len(entries) < max_entries:
            entries.append(f"{path.relative_to(root)} ({size} bytes)")
    preview = ", ".join(entries) if entries else "no files"
    return f"{total_files} files, {total_bytes} bytes; preview: {preview}"


def strip_supervisor_headers(text: str) -> str:
    return re.sub(
        r"(?im)^\s*\[B2B-\d{8}-\d{6}\]\[Supervisor\]\[(?:ASSIGN|DONE|ERROR|STATUS)\]\s*",
        "",
        text,
    ).strip()


def strip_leading_username(text: str, username: str) -> str:
    if not username:
        return text.strip()
    pattern = rf"(?im)^\s*@{re.escape(username)}\b\s*"
    previous = None
    while previous != text:
        previous = text
        text = re.sub(pattern, "", text).strip()
    return text.strip()


def normalize_manager_message(task_id: str, role: str, message: str, usernames: dict[str, str]) -> str:
    text = repair_split_usernames(replace_role_mentions(message, usernames), usernames)
    text = strip_supervisor_headers(text)
    if role in WORKER_ROLES:
        username = usernames[role]
        text = strip_leading_username(text, username)
        return f"[{task_id}][Supervisor][ASSIGN]\n@{username}" + (f"\n{text}" if text else "")
    if role in {"DONE", "ERROR"}:
        text = strip_leading_username(text, usernames.get("Supervisor", ""))
        return f"[{task_id}][Supervisor][{role}]" + (f"\n{text}" if text else "")
    return text


def task_has_deliverables(task_dir: Path, work_dir: str | None) -> bool:
    files_dir = task_dir / "files"
    if files_dir.exists() and any(path.is_file() for path in files_dir.rglob("*")):
        return True
    if work_dir:
        root = Path(work_dir).expanduser()
        if root.exists() and any(path.is_file() for path in root.rglob("*")):
            return True
    return False


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

