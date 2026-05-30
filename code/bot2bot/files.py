from __future__ import annotations

import fcntl
import os
import re
import sys
from pathlib import Path, PurePosixPath


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


