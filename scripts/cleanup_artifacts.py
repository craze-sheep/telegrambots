#!/usr/bin/env python3
"""Clean old Telegram AI Team artifacts."""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]


def remove_path(path: Path, dry_run: bool) -> None:
    if dry_run:
        print(f"would remove: {path}")
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    print(f"removed: {path}")


def cleanup_task_dirs(artifacts_dir: Path, cutoff: float, dry_run: bool) -> int:
    count = 0
    task_roots = [artifacts_dir / "tasks", artifacts_dir]
    seen: set[Path] = set()
    for task_root in task_roots:
        if not task_root.exists():
            continue
        for path in sorted(task_root.glob("B2B-*")):
            path = path.resolve()
            if path in seen or not path.is_dir():
                continue
            seen.add(path)
            if path.stat().st_mtime >= cutoff:
                continue
            remove_path(path, dry_run)
            count += 1
    return count


def cleanup_tmux_jobs(artifacts_dir: Path, cutoff: float, dry_run: bool) -> int:
    jobs_dir = artifacts_dir / "tmux-jobs"
    if not jobs_dir.exists():
        return 0
    count = 0
    for path in sorted(jobs_dir.iterdir()):
        if path.stat().st_mtime >= cutoff:
            continue
        remove_path(path, dry_run)
        count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean old artifacts without touching current source files.")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Artifacts directory, relative to project root by default.")
    parser.add_argument("--days", type=int, default=30, help="Remove artifacts older than this many days.")
    parser.add_argument("--include-tmux-jobs", action="store_true", help="Also clean old artifacts/tmux-jobs files.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be removed without deleting.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts_dir = Path(args.artifacts_dir)
    if not artifacts_dir.is_absolute():
        artifacts_dir = PROJECT_DIR / artifacts_dir
    artifacts_dir = artifacts_dir.resolve()

    if args.days < 1:
        raise SystemExit("--days must be >= 1")
    if not artifacts_dir.exists():
        print(f"nothing to clean: {artifacts_dir} does not exist")
        return

    cutoff = time.time() - args.days * 86400
    task_count = cleanup_task_dirs(artifacts_dir, cutoff, args.dry_run)
    job_count = cleanup_tmux_jobs(artifacts_dir, cutoff, args.dry_run) if args.include_tmux_jobs else 0
    action = "would remove" if args.dry_run else "removed"
    print(f"{action} {task_count} task artifact dir(s), {job_count} tmux job file(s)")


if __name__ == "__main__":
    main()
