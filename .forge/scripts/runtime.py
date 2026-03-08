#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


STATUS_START = "<!-- forge:status:start -->"
STATUS_END = "<!-- forge:status:end -->"
DOC_HASH_PATH = Path(".forge/state/current/doc_hashes.json")
QUEUE_PATH = Path(".forge/state/current/queue.json")
VALIDATION_PATH = Path(".forge/state/current/validation.json")
VALIDATION_REPORT_PATH = Path(".forge/state/current/last_validation.json")
RUNS_DIR = Path(".forge/runs")
SESSIONS_DIR = Path(".forge/sessions")
WORKTREES_DIR = Path(".forge/worktrees")
RUN_CONTEXT_PATH = Path(".forge/run-context.json")
TRACKED_DOCS = [
    Path("docs/prompt.md"),
    Path("docs/plans.md"),
    Path("docs/implement.md"),
    Path("docs/user_scenarios.md"),
]
ARCHIVE_SNAPSHOT = [
    Path("docs/prompt.md"),
    Path("docs/plans.md"),
    Path("docs/implement.md"),
    Path("docs/documentation.md"),
    Path("docs/user_scenarios.md"),
    Path("docs/prd.md"),
    Path("docs/architecture.md"),
    Path("docs/conventions.md"),
    Path("docs/tech_stack.md"),
    Path("docs/backlog.md"),
    QUEUE_PATH,
    VALIDATION_PATH,
    VALIDATION_REPORT_PATH,
]
MILESTONE_STATUSES = {"planned", "active", "done", "blocked"}
TASK_STATUSES = {"pending", "done", "blocked"}
PHASES = {"init", "open", "close"}
SESSION_STATUSES = {
    "clarifying",
    "drafting",
    "awaiting_review",
    "applying_feedback",
    "awaiting_final_approval",
    "finalizing",
    "completed",
    "deferred",
    "abandoned",
}
ACTIVE_SESSION_STATUSES = SESSION_STATUSES - {"completed", "abandoned"}
RUN_RESUMABLE_STATUSES = {"prepared", "interrupted", "needs_human", "failed", "max_sessions"}


class ForgeError(RuntimeError):
    pass


class DocParseError(ForgeError):
    def __init__(self, path: Path, message: str, line: int | None = None, column: int | None = None):
        self.path = path
        self.line = line
        self.column = column
        location = str(path)
        if line is not None:
            location += f":{line}"
            if column is not None:
                location += f":{column}"
        super().__init__(f"{location}: {message}")


@dataclass
class TomlBlock:
    path: Path
    text: str
    start_line: int
    data: dict[str, Any]


def run(
    command: list[str] | str,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        check=False,
        text=True,
        capture_output=capture_output,
        shell=isinstance(command, str),
        executable="/bin/bash" if isinstance(command, str) else None,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else ""
        stdout = result.stdout.strip() if result.stdout else ""
        detail = stderr or stdout or f"command failed with exit code {result.returncode}"
        raise ForgeError(detail)
    return result


def git_root(cwd: Path) -> Path:
    result = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, capture_output=True)
    return Path(result.stdout.strip())


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=True)
        handle.write("\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def repo_context(start: Path) -> tuple[Path, Path]:
    root = git_root(start)
    run_context = load_json(root / RUN_CONTEXT_PATH, default=None)
    if run_context and run_context.get("main_root"):
        return root, Path(run_context["main_root"])
    env_main_root = os.environ.get("FORGE_MAIN_ROOT")
    if env_main_root:
        return root, Path(env_main_root)
    return root, root


def now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def session_resume_hint(phase: str) -> str:
    return f"/forge-{phase}"


def pid_is_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ensure_relative_paths(paths: list[str], *, root: Path) -> list[str]:
    normalized: list[str] = []
    for item in paths:
        candidate = Path(item)
        normalized.append(str(candidate if candidate.is_absolute() else candidate))
    return normalized


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        raise ForgeError(f"{path} does not exist.")
    return path.read_text(encoding="utf-8").splitlines()


def parse_toml_blocks(path: Path) -> list[TomlBlock]:
    if not path.exists():
        raise ForgeError(f"{path} does not exist.")
    lines = path.read_text(encoding="utf-8").splitlines()
    blocks: list[TomlBlock] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if not line.startswith("```"):
            idx += 1
            continue
        info = line[3:].strip().split()
        if not info or info[0] != "toml":
            idx += 1
            continue
        block_start = idx + 2
        idx += 1
        collected: list[str] = []
        while idx < len(lines) and lines[idx].strip() != "```":
            collected.append(lines[idx])
            idx += 1
        if idx >= len(lines):
            raise DocParseError(path, "Unterminated TOML code fence.", line=block_start)
        text = "\n".join(collected)
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            absolute_line = block_start + exc.lineno - 1
            raise DocParseError(path, exc.msg, line=absolute_line, column=exc.colno) from exc
        blocks.append(TomlBlock(path=path, text=text, start_line=block_start, data=data))
        idx += 1
    return blocks


def ensure_list_of_strings(value: Any, *, path: Path, line: int, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DocParseError(path, f"{label} must be an array of strings.", line=line)
    return value


def parse_prompt(root: Path) -> dict[str, Any]:
    path = root / "docs/prompt.md"
    blocks = parse_toml_blocks(path)
    if not blocks:
        raise DocParseError(path, "Add a TOML block with project, user_surface, and commands.")
    data = blocks[0].data
    project = data.get("project")
    user_surface = data.get("user_surface")
    commands = data.get("commands")
    if not isinstance(project, dict):
        raise DocParseError(path, "Missing [project] table.", line=blocks[0].start_line)
    if not isinstance(user_surface, dict):
        raise DocParseError(path, "Missing [user_surface] table.", line=blocks[0].start_line)
    if not isinstance(commands, dict):
        raise DocParseError(path, "Missing [commands] table.", line=blocks[0].start_line)
    if not isinstance(project.get("name"), str) or not project["name"].strip():
        raise DocParseError(path, "project.name must be a non-empty string.", line=blocks[0].start_line)
    if not isinstance(project.get("one_liner"), str) or not project["one_liner"].strip():
        raise DocParseError(path, "project.one_liner must be a non-empty string.", line=blocks[0].start_line)
    if not isinstance(user_surface.get("kind"), str) or not user_surface["kind"].strip():
        raise DocParseError(path, "user_surface.kind must be a non-empty string.", line=blocks[0].start_line)
    return {
        "path": str(path.relative_to(root)),
        "hash": sha256(path),
        "project": project,
        "user_surface": user_surface,
        "commands": {
            "runtime_prepare": ensure_list_of_strings(commands.get("runtime_prepare"), path=path, line=blocks[0].start_line, label="commands.runtime_prepare"),
            "runtime_doctor": ensure_list_of_strings(commands.get("runtime_doctor"), path=path, line=blocks[0].start_line, label="commands.runtime_doctor"),
            "validate_static": ensure_list_of_strings(commands.get("validate_static"), path=path, line=blocks[0].start_line, label="commands.validate_static"),
            "validate_surface": ensure_list_of_strings(commands.get("validate_surface"), path=path, line=blocks[0].start_line, label="commands.validate_surface"),
        },
    }


def parse_plans(root: Path) -> dict[str, Any]:
    path = root / "docs/plans.md"
    if not path.exists():
        return {"path": str(path.relative_to(root)), "hash": None, "milestones": []}
    blocks = parse_toml_blocks(path)
    milestones: list[dict[str, Any]] = []
    for block in blocks:
        if block.data.get("type") != "milestone":
            continue
        milestone = block.data.get("milestone")
        if not isinstance(milestone, dict):
            raise DocParseError(path, "Milestone block must include [milestone].", line=block.start_line)
        milestone_id = milestone.get("id")
        title = milestone.get("title")
        goal = milestone.get("goal")
        status = milestone.get("status", "planned")
        if not isinstance(milestone_id, str) or not milestone_id.strip():
            raise DocParseError(path, "milestone.id must be a non-empty string.", line=block.start_line)
        if not isinstance(title, str) or not title.strip():
            raise DocParseError(path, "milestone.title must be a non-empty string.", line=block.start_line)
        if not isinstance(goal, str) or not goal.strip():
            raise DocParseError(path, "milestone.goal must be a non-empty string.", line=block.start_line)
        if status not in MILESTONE_STATUSES:
            raise DocParseError(path, f"milestone.status must be one of {sorted(MILESTONE_STATUSES)}.", line=block.start_line)
        tasks = block.data.get("task", [])
        if not isinstance(tasks, list):
            raise DocParseError(path, "[[task]] entries are required for milestones.", line=block.start_line)
        normalized_tasks: list[dict[str, Any]] = []
        task_ids: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise DocParseError(path, "Each [[task]] entry must be an object.", line=block.start_line)
            task_id = task.get("id")
            if not isinstance(task_id, str) or not task_id.strip():
                raise DocParseError(path, "task.id must be a non-empty string.", line=block.start_line)
            if task_id in task_ids:
                raise DocParseError(path, f"Duplicate task id '{task_id}' in active milestone.", line=block.start_line)
            task_ids.add(task_id)
            title_value = task.get("title")
            description = task.get("description")
            if not isinstance(title_value, str) or not title_value.strip():
                raise DocParseError(path, f"Task '{task_id}' is missing title.", line=block.start_line)
            if not isinstance(description, str) or not description.strip():
                raise DocParseError(path, f"Task '{task_id}' is missing description.", line=block.start_line)
            depends_on = ensure_list_of_strings(task.get("depends_on"), path=path, line=block.start_line, label=f"task.{task_id}.depends_on")
            normalized_tasks.append(
                {
                    "id": task_id,
                    "title": title_value,
                    "description": description,
                    "depends_on": depends_on,
                }
            )
        validation = block.data.get("validation", {})
        if validation is None:
            validation = {}
        if not isinstance(validation, dict):
            raise DocParseError(path, "validation must be a table.", line=block.start_line)
        validation_commands = ensure_list_of_strings(validation.get("commands"), path=path, line=block.start_line, label="validation.commands")
        smoke_scenarios = ensure_list_of_strings(validation.get("smoke_scenarios"), path=path, line=block.start_line, label="validation.smoke_scenarios")
        milestone_scope = ensure_list_of_strings(milestone.get("scope"), path=path, line=block.start_line, label="milestone.scope")
        milestone_acceptance = ensure_list_of_strings(milestone.get("acceptance"), path=path, line=block.start_line, label="milestone.acceptance")
        milestones.append(
            {
                "id": milestone_id,
                "title": title,
                "goal": goal,
                "status": status,
                "scope": milestone_scope,
                "acceptance": milestone_acceptance,
                "validation": {
                    "commands": validation_commands,
                    "smoke_scenarios": smoke_scenarios,
                    "stop_and_fix": bool(validation.get("stop_and_fix", True)),
                },
                "tasks": normalized_tasks,
                "line": block.start_line,
            }
        )
    active = [milestone for milestone in milestones if milestone["status"] == "active"]
    if len(active) > 1:
        raise DocParseError(path, "Only one milestone can have status='active'.", line=active[1]["line"])
    return {"path": str(path.relative_to(root)), "hash": sha256(path), "milestones": milestones}


def current_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in TRACKED_DOCS:
        full_path = root / relative
        if full_path.exists():
            hashes[str(relative)] = sha256(full_path)
    return hashes


def sync_state(root: Path) -> dict[str, Any]:
    prompt = parse_prompt(root)
    plans = parse_plans(root)
    hashes = current_hashes(root)
    queue_path = root / QUEUE_PATH
    validation_path = root / VALIDATION_PATH
    existing_queue = load_json(queue_path, default={}) or {}
    existing_tasks = {
        task["id"]: task
        for task in existing_queue.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    milestones = plans["milestones"]
    active = next((milestone for milestone in milestones if milestone["status"] == "active"), None)
    if active is None:
        queue_payload = {
            "project": prompt["project"]["name"],
            "source_hashes": hashes,
            "active_milestone": None,
            "tasks": [],
            "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        validation_payload = {
            "project": prompt["project"]["name"],
            "source_hashes": hashes,
            "active_milestone": None,
            "commands": [],
            "smoke_scenarios": [],
            "synced_at": queue_payload["synced_at"],
        }
        write_json(queue_path, queue_payload)
        write_json(validation_path, validation_payload)
        write_json(root / DOC_HASH_PATH, {"hashes": hashes, "synced_at": queue_payload["synced_at"]})
        return {"queue": queue_payload, "validation": validation_payload, "active": None}
    task_lookup = {task["id"]: task for task in active["tasks"]}
    for task in active["tasks"]:
        missing = [dependency for dependency in task["depends_on"] if dependency not in task_lookup]
        if missing:
            raise DocParseError(root / "docs/plans.md", f"Task '{task['id']}' depends on unknown task(s): {', '.join(missing)}.", line=active["line"])
        if task["id"] in task["depends_on"]:
            raise DocParseError(root / "docs/plans.md", f"Task '{task['id']}' cannot depend on itself.", line=active["line"])
    merged_tasks: list[dict[str, Any]] = []
    for index, task in enumerate(active["tasks"], start=1):
        previous = existing_tasks.get(task["id"], {})
        status = previous.get("status", "pending")
        if status not in TASK_STATUSES:
            status = "pending"
        merged_tasks.append(
            {
                "id": task["id"],
                "title": task["title"],
                "description": task["description"],
                "depends_on": task["depends_on"],
                "status": status,
                "notes": previous.get("notes", ""),
                "priority": index,
            }
        )
    validation_commands = active["validation"]["commands"] or [
        "./.forge/scripts/validate_static.sh",
        "./.forge/scripts/validate_surface.sh",
    ]
    queue_payload = {
        "project": prompt["project"]["name"],
        "source_hashes": hashes,
        "active_milestone": {
            "id": active["id"],
            "title": active["title"],
            "goal": active["goal"],
            "scope": active["scope"],
            "acceptance": active["acceptance"],
        },
        "tasks": merged_tasks,
        "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    validation_payload = {
        "project": prompt["project"]["name"],
        "source_hashes": hashes,
        "active_milestone": {
            "id": active["id"],
            "title": active["title"],
        },
        "commands": validation_commands,
        "smoke_scenarios": active["validation"]["smoke_scenarios"],
        "stop_and_fix": active["validation"]["stop_and_fix"],
        "user_surface": prompt["user_surface"],
        "synced_at": queue_payload["synced_at"],
    }
    write_json(queue_path, queue_payload)
    write_json(validation_path, validation_payload)
    write_json(root / DOC_HASH_PATH, {"hashes": hashes, "synced_at": queue_payload["synced_at"]})
    return {"queue": queue_payload, "validation": validation_payload, "active": active}


def state_is_stale(root: Path) -> bool:
    hashes = current_hashes(root)
    stored = load_json(root / DOC_HASH_PATH, default={}) or {}
    return stored.get("hashes") != hashes


def ensure_synced(root: Path) -> dict[str, Any]:
    if state_is_stale(root) or not (root / QUEUE_PATH).exists() or not (root / VALIDATION_PATH).exists():
        return sync_state(root)
    return {
        "queue": load_json(root / QUEUE_PATH, default={}) or {},
        "validation": load_json(root / VALIDATION_PATH, default={}) or {},
        "active": None,
    }


def queue_stats(root: Path) -> dict[str, Any]:
    queue = load_json(root / QUEUE_PATH, default={}) or {}
    tasks = queue.get("tasks", [])
    done = sum(1 for task in tasks if task.get("status") == "done")
    blocked = sum(1 for task in tasks if task.get("status") == "blocked")
    pending = sum(1 for task in tasks if task.get("status") == "pending")
    task_map = {task["id"]: task for task in tasks if isinstance(task, dict) and isinstance(task.get("id"), str)}
    available = 0
    for task in tasks:
        if task.get("status") != "pending":
            continue
        deps = task.get("depends_on", [])
        if all(task_map.get(dep, {}).get("status") == "done" for dep in deps):
            available += 1
    return {
        "total": len(tasks),
        "done": done,
        "blocked": blocked,
        "pending": pending,
        "available": available,
        "active_milestone": queue.get("active_milestone"),
    }


def current_run(main_root: Path) -> dict[str, Any] | None:
    path = main_root / RUNS_DIR / "current.json"
    payload = load_json(path, default=None)
    if not payload:
        return None
    worktree_path = payload.get("worktree_path")
    if worktree_path and not Path(worktree_path).exists():
        path.unlink(missing_ok=True)
        return None
    if payload.get("status") == "running" and not pid_is_alive(payload.get("pid")):
        payload["status"] = "interrupted"
        payload["pid"] = None
        payload["updated_at"] = now()
        write_json(path, payload)
        state_path = main_root / RUNS_DIR / payload["run_id"] / "state.json"
        state = load_json(state_path, default={}) or {}
        if state:
            state["status"] = "interrupted"
            state["pid"] = None
            state["updated_at"] = payload["updated_at"]
            write_json(state_path, state)
    return payload


def write_current_run(main_root: Path, payload: dict[str, Any] | None) -> None:
    path = main_root / RUNS_DIR / "current.json"
    if payload is None:
        if path.exists():
            path.unlink()
        return
    write_json(path, payload)


def update_run_state(main_root: Path, run_id: str, **updates: Any) -> dict[str, Any]:
    path = main_root / RUNS_DIR / run_id / "state.json"
    state = load_json(path, default={}) or {}
    state.update(updates)
    write_json(path, state)
    current = current_run(main_root)
    if current and current.get("run_id") == run_id:
        current.update(
            {key: value for key, value in updates.items() if key in {"status", "updated_at", "worktree_path", "branch", "pid"}}
        )
        write_current_run(main_root, current)
    return state


def session_dir(main_root: Path, session_id: str) -> Path:
    return main_root / SESSIONS_DIR / session_id


def current_session(main_root: Path) -> dict[str, Any] | None:
    return load_json(main_root / SESSIONS_DIR / "current.json", default=None)


def write_current_session(main_root: Path, payload: dict[str, Any] | None) -> None:
    path = main_root / SESSIONS_DIR / "current.json"
    if payload is None:
        if path.exists():
            path.unlink()
        return
    write_json(path, payload)


def write_session_summary(main_root: Path, session: dict[str, Any]) -> None:
    target = session_dir(main_root, session["session_id"]) / "summary.md"
    lines = [
        f"# Session {session['session_id']}",
        "",
        f"- Phase: {session['phase']}",
        f"- Status: {session['status']}",
        f"- Started: {session.get('started_at', '-')}",
        f"- Updated: {session.get('updated_at', '-')}",
        f"- Next action: {session.get('next_action', '-')}",
        f"- Resume hint: {session.get('resume_hint', '-')}",
    ]
    if session.get("draft_files"):
        lines.extend(["", "## Draft Files", *[f"- {item}" for item in session["draft_files"]]])
    if session.get("pending_questions"):
        lines.extend(["", "## Pending Questions", *[f"- {item}" for item in session["pending_questions"]]])
    if session.get("decisions_made"):
        lines.extend(["", "## Decisions", *[f"- {item}" for item in session["decisions_made"]]])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def create_or_resume_session(main_root: Path, phase: str) -> dict[str, Any]:
    if phase not in PHASES:
        raise ForgeError(f"Unsupported phase: {phase}")
    current = current_session(main_root)
    if current and current.get("status") in ACTIVE_SESSION_STATUSES:
        if current.get("phase") != phase:
            raise ForgeError(
                f"Active phase session {current['session_id']} ({current['phase']}) exists. "
                f"Resume {current.get('resume_hint', session_resume_hint(current['phase']))} or abandon it first."
            )
        current["mode"] = "resume"
        return current
    session_id = f"{phase}-{time.strftime('%Y%m%d-%H%M%S')}"
    payload = {
        "session_id": session_id,
        "phase": phase,
        "status": "clarifying",
        "started_at": now(),
        "updated_at": now(),
        "root": str(main_root),
        "draft_files": [],
        "pending_questions": [],
        "decisions_made": [],
        "next_action": "Continue the interactive session.",
        "related_run_id": None,
        "related_worktree": None,
        "resume_hint": session_resume_hint(phase),
    }
    session_root = session_dir(main_root, session_id)
    session_root.mkdir(parents=True, exist_ok=False)
    write_json(session_root / "state.json", payload)
    write_session_summary(main_root, payload)
    write_current_session(main_root, payload)
    payload["mode"] = "created"
    return payload


def update_session_state(main_root: Path, session_id: str, **updates: Any) -> dict[str, Any]:
    path = session_dir(main_root, session_id) / "state.json"
    state = load_json(path, default={}) or {}
    if not state:
        raise ForgeError(f"Unknown session: {session_id}")
    if "status" in updates and updates["status"] not in SESSION_STATUSES:
        raise ForgeError(f"Unsupported session status: {updates['status']}")
    for key in ("draft_files", "pending_questions", "decisions_made"):
        if key in updates and updates[key] is not None:
            existing = list(state.get(key, []))
            for item in updates[key]:
                if item not in existing:
                    existing.append(item)
            updates[key] = existing
    updates["updated_at"] = now()
    state.update({key: value for key, value in updates.items() if value is not None})
    write_json(path, state)
    write_session_summary(main_root, state)
    current = current_session(main_root)
    if current and current.get("session_id") == session_id:
        merged = current | {key: state[key] for key in state.keys()}
        write_current_session(main_root, merged)
    return state


def complete_session(main_root: Path, session_id: str, *, status: str = "completed") -> dict[str, Any]:
    state = update_session_state(main_root, session_id, status=status)
    current = current_session(main_root)
    if current and current.get("session_id") == session_id and status in {"completed", "abandoned"}:
        write_current_session(main_root, None)
    return state


def resumable_run(main_root: Path) -> dict[str, Any] | None:
    current = current_run(main_root)
    if not current:
        return None
    worktree_path = current.get("worktree_path")
    if not worktree_path or not Path(worktree_path).exists():
        return None
    if current.get("status") in RUN_RESUMABLE_STATUSES:
        return current
    return None


def ensure_clean_worktree(root: Path) -> None:
    unstaged = run(["git", "diff", "--name-only"], cwd=root, capture_output=True).stdout.strip()
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, capture_output=True).stdout.strip()
    if unstaged or staged:
        raise ForgeError("Working tree has tracked changes. Commit or stash before starting ./forge run.")


def ensure_documentation_markers(root: Path) -> Path:
    path = root / "docs/documentation.md"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "# Documentation\n\n"
            f"{STATUS_START}\n"
            "_No machine status yet._\n"
            f"{STATUS_END}\n\n"
            "## Session Notes\n"
            "- Add short session summaries here.\n\n"
            "## Decisions\n"
            "- Record durable decisions and why they were made.\n\n"
            "## Known Issues\n"
            "- Capture follow-ups that should survive agent sessions.\n",
            encoding="utf-8",
        )
    else:
        content = path.read_text(encoding="utf-8")
        if STATUS_START not in content or STATUS_END not in content:
            path.write_text(
                f"{STATUS_START}\n"
                "_No machine status yet._\n"
                f"{STATUS_END}\n\n"
                f"{content}",
                encoding="utf-8",
            )
    return path


def render_status_block(root: Path, qa_result: dict[str, Any] | None = None) -> str:
    queue = load_json(root / QUEUE_PATH, default={}) or {}
    stats = queue_stats(root)
    current = load_json(root / DOC_HASH_PATH, default={}) or {}
    validation_report = qa_result or load_json(root / VALIDATION_REPORT_PATH, default=None)
    _, main_root = repo_context(root)
    current_run_info = current_run(main_root)
    current_session_info = current_session(main_root)
    run_summary = "none"
    if current_run_info:
        run_summary = f"{current_run_info.get('run_id')} ({current_run_info.get('status', 'unknown')})"
    session_summary = "none"
    if current_session_info:
        session_summary = f"{current_session_info.get('session_id')} ({current_session_info.get('status', 'unknown')})"
    milestone = stats["active_milestone"]
    milestone_label = "none"
    if milestone:
        milestone_label = f"{milestone['id']} - {milestone['title']}"
    validation_status = "not run"
    validation_time = "-"
    if validation_report:
        validation_status = validation_report.get("status", "unknown")
        validation_time = validation_report.get("finished_at", "-")
    lines = [
        "## Machine Status",
        f"- Synced at: {current.get('synced_at', 'unknown')}",
        f"- Active milestone: {milestone_label}",
        f"- Tasks: {stats['done']}/{stats['total']} done, {stats['pending']} pending, {stats['blocked']} blocked, {stats['available']} available",
        f"- Last QA: {validation_status} at {validation_time}",
        f"- Active phase session: {session_summary}",
        f"- Active run: {run_summary}",
    ]
    return "\n".join(lines)


def update_documentation_status(root: Path, qa_result: dict[str, Any] | None = None) -> None:
    path = ensure_documentation_markers(root)
    content = path.read_text(encoding="utf-8")
    start_idx = content.index(STATUS_START) + len(STATUS_START)
    end_idx = content.index(STATUS_END)
    replacement = "\n" + render_status_block(root, qa_result=qa_result) + "\n"
    updated = content[:start_idx] + replacement + content[end_idx:]
    path.write_text(updated, encoding="utf-8")


def render_hook_script(prompt: dict[str, Any], *, kind: str) -> str:
    commands = prompt["commands"]
    if kind == "validate_static":
        lines = commands["validate_static"]
        script_name = "validate_static.sh"
        configured = bool(lines)
        body = "\n".join(lines) if lines else 'echo "validate_static.sh is not configured. Fill docs/prompt.md [commands].validate_static."; exit 1'
    elif kind == "validate_surface":
        lines = commands["validate_surface"]
        script_name = "validate_surface.sh"
        configured = bool(lines)
        body = "\n".join(lines) if lines else 'echo "validate_surface.sh is not configured. Fill docs/prompt.md [commands].validate_surface."; exit 1'
    elif kind == "prepare_runtime":
        lines = commands["runtime_prepare"]
        doctor_lines = commands["runtime_doctor"]
        script_name = "prepare_runtime.sh"
        configured = bool(lines or doctor_lines)
        body = "\n".join(lines) if lines else "exit 0"
    else:
        raise ForgeError(f"Unknown hook kind: {kind}")
    if kind == "prepare_runtime" and doctor_lines:
        doctor_block = "".join(f"  {line}\n" for line in doctor_lines) + "  echo \"prepare_runtime.sh: configured\"\n  exit 0\n"
    elif configured:
        doctor_block = f'  echo "{script_name}: configured"\n  exit 0\n'
    elif kind == "prepare_runtime":
        doctor_block = f'  echo "{script_name}: not required"\n  exit 0\n'
    else:
        doctor_block = f'  echo "{script_name}: not configured"\n  exit 1\n'
    return (
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        'if [ "${1:-}" = "--doctor" ]; then\n'
        + doctor_block
        + "fi\n"
        + 'FORGE_SCENARIO="${1:-default}"\n'
        + f"{body}\n"
    )


def run_commands(commands: list[str], *, cwd: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in commands:
        started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        result = run(command, cwd=cwd, capture_output=True, check=False)
        results.append(
            {
                "command": command,
                "started_at": started_at,
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != 0:
            break
    return results


def run_qa(root: Path) -> dict[str, Any]:
    ensure_synced(root)
    validation = load_json(root / VALIDATION_PATH, default={}) or {}
    commands = validation.get("commands") or ["./.forge/scripts/validate_static.sh", "./.forge/scripts/validate_surface.sh"]
    results = run_commands(commands, cwd=root)
    status = "pass" if results and all(item["exit_code"] == 0 for item in results) else "fail"
    report = {
        "status": status,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "commands": results,
    }
    write_json(root / VALIDATION_REPORT_PATH, report)
    update_documentation_status(root, qa_result=report)
    return report


def tracked_changes(root: Path) -> list[str]:
    unstaged = run(["git", "diff", "--name-only"], cwd=root, capture_output=True).stdout.splitlines()
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, capture_output=True).stdout.splitlines()
    return sorted({item.strip() for item in [*unstaged, *staged] if item.strip()})


def snapshot_open(root: Path, *, message: str | None = None) -> dict[str, Any]:
    allowed = {
        "docs/prd.md",
        "docs/backlog.md",
        "docs/plans.md",
        "docs/documentation.md",
    }
    changes = tracked_changes(root)
    outside_scope = [item for item in changes if item not in allowed]
    if outside_scope:
        raise ForgeError(
            "Open snapshot found unrelated tracked changes: " + ", ".join(outside_scope)
        )
    if not changes:
        return {"status": "noop", "message": "No planning changes to snapshot."}
    for relative in sorted(allowed):
        if (root / relative).exists():
            run(["git", "add", relative], cwd=root)
    milestone = queue_stats(root).get("active_milestone") or {}
    commit_message = message or f"Open milestone {milestone.get('id', 'unknown')}"
    run(["git", "commit", "-m", commit_message], cwd=root)
    return {"status": "committed", "message": commit_message}


def reset_project_state(root: Path, *, leave_status_note: bool = True) -> None:
    plans_path = root / "docs/plans.md"
    plans_path.write_text(
        "# Plans\n\n"
        "No active milestone. Run `/forge-open` or `$forge-open` to open the next phase.\n",
        encoding="utf-8",
    )
    documentation_path = root / "docs/documentation.md"
    documentation_path.write_text(
        "# Documentation\n\n"
        f"{STATUS_START}\n"
        "_No machine status yet._\n"
        f"{STATUS_END}\n\n"
        "## Session Notes\n"
        "- New milestone pending.\n\n"
        "## Decisions\n"
        "- Carry durable lessons into the next planning cycle.\n\n"
        "## Known Issues\n"
        "- None yet.\n",
        encoding="utf-8",
    )
    state_root = root / ".forge/state/current"
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    if leave_status_note:
        update_documentation_status(root)


def archive_project(target_root: Path, main_root: Path, name: str) -> Path:
    current = current_run(main_root)
    if current and current.get("status") in {"prepared", "running"}:
        raise ForgeError(f"Run {current['run_id']} is still active. Finish it before archiving.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ForgeError("Archive name must only contain letters, numbers, hyphens, and underscores.")
    archive_root = target_root / "docs/projects" / name
    if archive_root.exists():
        raise ForgeError(f"{archive_root} already exists.")
    archive_root.mkdir(parents=True, exist_ok=False)
    for relative in ARCHIVE_SNAPSHOT:
        source = target_root / relative
        if not source.exists():
            continue
        destination = archive_root / relative.name
        if relative.parts[:3] == (".forge", "state", "current"):
            destination = archive_root / "state" / relative.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    reset_project_state(target_root, leave_status_note=False)
    write_current_run(main_root, None)
    return archive_root


def archive_current_target(root: Path, main_root: Path) -> Path:
    current = current_run(main_root)
    if current and current.get("worktree_path"):
        worktree = Path(current["worktree_path"])
        if worktree.exists():
            return worktree
    return root


def command_sync(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    result = sync_state(root)
    update_documentation_status(root)
    active = result["queue"].get("active_milestone")
    if active:
        print(f"Synced active milestone {active['id']} ({len(result['queue']['tasks'])} tasks).")
    else:
        print("Synced documentation with no active milestone.")
    return 0


def command_status(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    ensure_synced(root)
    update_documentation_status(root)
    stats = queue_stats(root)
    report = load_json(root / VALIDATION_REPORT_PATH, default=None)
    doc_hash_info = load_json(root / DOC_HASH_PATH, default={}) or {}
    current = current_run(main_root)
    session = current_session(main_root)
    if args.brief:
        milestone = stats["active_milestone"]
        milestone_label = milestone["id"] if milestone else "none"
        qa = report["status"] if report else "not-run"
        print(
            json.dumps(
                {
                    "milestone": milestone_label,
                    "done": stats["done"],
                    "total": stats["total"],
                    "pending": stats["pending"],
                    "blocked": stats["blocked"],
                    "available": stats["available"],
                    "last_qa": qa,
                    "synced_at": doc_hash_info.get("synced_at"),
                    "active_session": session,
                    "active_run": current,
                }
            )
        )
        return 0
    milestone = stats["active_milestone"]
    print("=== Forge Status ===")
    print(f"Repo: {root}")
    print(f"Docs synced: {doc_hash_info.get('synced_at', 'never')}")
    if milestone:
        print(f"Milestone: {milestone['id']} - {milestone['title']}")
        print(f"Goal: {milestone['goal']}")
    else:
        print("Milestone: none")
    print(
        f"Tasks: {stats['done']}/{stats['total']} done | "
        f"{stats['pending']} pending | {stats['blocked']} blocked | {stats['available']} available"
    )
    if report:
        print(f"Last QA: {report['status']} at {report['finished_at']}")
    else:
        print("Last QA: not run")
    if session:
        print(
            f"Active phase session: {session.get('session_id')} [{session.get('status', 'unknown')}]"
        )
        print(f"Resume session: {session.get('resume_hint', session_resume_hint(session['phase']))}")
        if session.get("next_action"):
            print(f"Session next: {session['next_action']}")
    else:
        print("Active phase session: none")
    if current:
        print(f"Active run: {current.get('run_id')} [{current.get('status', 'unknown')}] at {current.get('worktree_path')}")
        if resumable_run(main_root):
            print("Resume run: ./forge run --resume")
    else:
        print("Active run: none")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    failures: list[str] = []
    checks: list[str] = []
    checks.append(f"git: {'ok' if shutil.which('git') else 'missing'}")
    checks.append(f"python3: {'ok' if shutil.which('python3') else 'missing'}")
    checks.append(f"claude CLI: {'ok' if shutil.which('claude') else 'missing'}")
    checks.append(f"codex CLI: {'ok' if shutil.which('codex') else 'missing'}")
    try:
        ensure_synced(root)
        checks.append("docs sync: ok")
    except ForgeError as exc:
        failures.append(str(exc))
    for script_name in ("validate_static.sh", "validate_surface.sh", "prepare_runtime.sh"):
        script_path = root / ".forge/scripts" / script_name
        if not script_path.exists():
            failures.append(f"{script_path} is missing.")
            continue
        if not os.access(script_path, os.X_OK):
            failures.append(f"{script_path} is not executable.")
            continue
        result = run([str(script_path), "--doctor"], cwd=root, capture_output=True, check=False)
        if result.returncode != 0:
            failures.append((result.stderr or result.stdout or f"{script_name} doctor failed").strip())
        else:
            checks.append(f"{script_name}: {(result.stdout or 'ok').strip()}")
    print("=== Forge Doctor ===")
    for item in checks:
        print(f"- {item}")
    if failures:
        print("")
        print("Failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("")
    print("All checks passed.")
    return 0


def command_qa(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    report = run_qa(root)
    print(f"QA {report['status']} ({len(report['commands'])} command(s))")
    for item in report["commands"]:
        status = "PASS" if item["exit_code"] == 0 else f"FAIL({item['exit_code']})"
        print(f"- {status} {item['command']}")
    return 0 if report["status"] == "pass" else 1


def command_queue_stats(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    ensure_synced(root)
    print(json.dumps(queue_stats(root)))
    return 0


def command_session_start(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    payload = create_or_resume_session(main_root, args.phase)
    print(json.dumps(payload))
    return 0


def command_session_update(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    payload = update_session_state(
        main_root,
        args.session_id,
        status=args.status,
        next_action=args.next_action,
        related_run_id=args.related_run_id,
        related_worktree=args.related_worktree,
        resume_hint=args.resume_hint,
        draft_files=args.draft_file,
        pending_questions=args.pending_question,
        decisions_made=args.decision,
    )
    print(json.dumps(payload))
    return 0


def command_session_complete(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    payload = complete_session(main_root, args.session_id, status=args.status)
    print(json.dumps(payload))
    return 0


def command_session_abandon(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    payload = complete_session(main_root, args.session_id, status="abandoned")
    print(json.dumps(payload))
    return 0


def command_session_status(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    payload = current_session(main_root)
    if payload is None:
        raise ForgeError("No active phase session.")
    print(json.dumps(payload))
    return 0


def command_set_run_status(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    updates: dict[str, Any] = {"status": args.status, "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if args.pid is not None:
        updates["pid"] = args.pid
    elif args.status != "running":
        updates["pid"] = None
    update_run_state(main_root, args.run_id, **updates)
    return 0


def prepare_run(root: Path, main_root: Path, agent: str, run_id: str | None = None) -> dict[str, Any]:
    sync_state(root)
    if root == main_root:
        ensure_clean_worktree(root)
    current = current_run(main_root)
    if current and current.get("status") in {"prepared", "running"}:
        raise ForgeError(f"Run {current['run_id']} is already active at {current['worktree_path']}.")
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S")
    worktree_path = main_root / WORKTREES_DIR / run_id
    branch_name = f"codex/run-{run_id}"
    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    if worktree_path.exists():
        raise ForgeError(f"Worktree path already exists: {worktree_path}")
    run(["git", "worktree", "add", "--quiet", "-b", branch_name, str(worktree_path), "HEAD"], cwd=main_root)
    run_dir = main_root / RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        run_dir / "state.json",
        {
            "run_id": run_id,
            "status": "prepared",
            "agent": agent,
            "branch": branch_name,
            "worktree_path": str(worktree_path),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pid": None,
        },
    )
    write_current_run(
        main_root,
        {
            "run_id": run_id,
            "status": "prepared",
            "agent": agent,
            "branch": branch_name,
            "worktree_path": str(worktree_path),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pid": None,
        },
    )
    context_path = worktree_path / RUN_CONTEXT_PATH
    context_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(context_path, {"run_id": run_id, "main_root": str(main_root)})
    run([sys.executable, str(worktree_path / ".forge/scripts/runtime.py"), "sync"], cwd=worktree_path, capture_output=True)
    prepare_runtime = worktree_path / ".forge/scripts/prepare_runtime.sh"
    if prepare_runtime.exists():
        result = run([str(prepare_runtime)], cwd=worktree_path, capture_output=True, check=False)
        if result.returncode != 0:
            update_run_state(main_root, run_id, status="failed", updated_at=time.strftime("%Y-%m-%d %H:%M:%S"))
            raise ForgeError((result.stderr or result.stdout or "prepare_runtime.sh failed").strip())
    return {
        "run_id": run_id,
        "branch": branch_name,
        "worktree_path": str(worktree_path),
    }


def command_prepare_run(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    info = prepare_run(root, main_root, args.agent, run_id=args.run_id)
    print(json.dumps(info))
    return 0


def command_run_resume_info(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    payload = resumable_run(main_root)
    if payload is None:
        raise ForgeError("No resumable run.")
    print(json.dumps(payload))
    return 0


def command_snapshot_open(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    if root != main_root:
        raise ForgeError("Open snapshot must be created from the main workspace root.")
    ensure_synced(root)
    payload = snapshot_open(root, message=args.message)
    print(json.dumps(payload))
    return 0


def command_archive(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    current = current_run(main_root)
    if root == main_root and current and current.get("worktree_path"):
        raise ForgeError(f"Archive from {current['worktree_path']} or merge that worktree first.")
    archive_root = archive_project(root, main_root, args.name)
    if root != main_root:
        reset_project_state(main_root)
    print(f"Archived current project snapshot to {archive_root}")
    return 0


def command_archive_current(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    target_root = archive_current_target(root, main_root)
    archive_root = archive_project(target_root, main_root, args.name)
    if root == main_root and target_root != root:
        reset_project_state(root)
    print(f"Archived current project snapshot to {archive_root}")
    return 0


def command_reset_current(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    target_root = archive_current_target(root, main_root)
    reset_project_state(target_root)
    if root == main_root and target_root != root:
        reset_project_state(root)
    if args.clear_run:
        write_current_run(main_root, None)
    print(f"Reset current project state at {target_root}")
    return 0


def command_render_hook(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    prompt = parse_prompt(root)
    sys.stdout.write(render_hook_script(prompt, kind=args.kind))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forge v2 runtime helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--brief", action="store_true")

    subparsers.add_parser("doctor")
    subparsers.add_parser("qa")
    subparsers.add_parser("queue-stats")

    session_start = subparsers.add_parser("session-start")
    session_start.add_argument("--phase", required=True, choices=sorted(PHASES))

    session_update = subparsers.add_parser("session-update")
    session_update.add_argument("--session-id", required=True)
    session_update.add_argument("--status", choices=sorted(SESSION_STATUSES))
    session_update.add_argument("--next-action")
    session_update.add_argument("--related-run-id")
    session_update.add_argument("--related-worktree")
    session_update.add_argument("--resume-hint")
    session_update.add_argument("--draft-file", action="append")
    session_update.add_argument("--pending-question", action="append")
    session_update.add_argument("--decision", action="append")

    session_complete = subparsers.add_parser("session-complete")
    session_complete.add_argument("--session-id", required=True)
    session_complete.add_argument("--status", choices=["completed", "deferred"], default="completed")

    session_abandon = subparsers.add_parser("session-abandon")
    session_abandon.add_argument("--session-id", required=True)

    subparsers.add_parser("session-status")

    set_status = subparsers.add_parser("set-run-status")
    set_status.add_argument("--run-id", required=True)
    set_status.add_argument("--status", required=True)
    set_status.add_argument("--pid", type=int)

    prepare_run_parser = subparsers.add_parser("prepare-run")
    prepare_run_parser.add_argument("agent", choices=["claude", "codex"])
    prepare_run_parser.add_argument("--run-id")

    subparsers.add_parser("run-resume-info")

    snapshot_open = subparsers.add_parser("snapshot-open")
    snapshot_open.add_argument("--message")

    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("name")

    archive_current = subparsers.add_parser("archive-current")
    archive_current.add_argument("name")

    reset_current = subparsers.add_parser("reset-current")
    reset_current.add_argument("--clear-run", action="store_true")

    render_hook = subparsers.add_parser("render-hook")
    render_hook.add_argument("kind", choices=["validate_static", "validate_surface", "prepare_runtime"])

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "sync":
            return command_sync(args)
        if args.command == "status":
            return command_status(args)
        if args.command == "doctor":
            return command_doctor(args)
        if args.command == "qa":
            return command_qa(args)
        if args.command == "queue-stats":
            return command_queue_stats(args)
        if args.command == "session-start":
            return command_session_start(args)
        if args.command == "session-update":
            return command_session_update(args)
        if args.command == "session-complete":
            return command_session_complete(args)
        if args.command == "session-abandon":
            return command_session_abandon(args)
        if args.command == "session-status":
            return command_session_status(args)
        if args.command == "set-run-status":
            return command_set_run_status(args)
        if args.command == "prepare-run":
            return command_prepare_run(args)
        if args.command == "run-resume-info":
            return command_run_resume_info(args)
        if args.command == "snapshot-open":
            return command_snapshot_open(args)
        if args.command == "archive":
            return command_archive(args)
        if args.command == "archive-current":
            return command_archive_current(args)
        if args.command == "reset-current":
            return command_reset_current(args)
        if args.command == "render-hook":
            return command_render_hook(args)
    except ForgeError as exc:
        print(f"forge: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
