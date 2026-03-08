#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
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
QUEUE_PATH = Path(".forge/state/current/queue.json")
VALIDATION_REPORT_PATH = Path(".forge/state/current/last_validation.json")
RUNS_DIR = Path(".forge/runs")
WORKTREES_DIR = Path(".forge/worktrees")
RUN_CONTEXT_PATH = Path(".forge/run-context.json")
WORKER_LEDGER_NAME = "workers.jsonl"
WORKER_SUMMARY_NAME = "worker-summary.json"
ARCHIVE_SNAPSHOT = [
    Path("docs/prompt.md"),
    Path("docs/plans.md"),
    Path("docs/documentation.md"),
    Path("docs/prd.md"),
    Path("docs/architecture.md"),
    Path("docs/backlog.md"),
    QUEUE_PATH,
    VALIDATION_REPORT_PATH,
]
MILESTONE_STATUSES = {"planned", "active", "done", "blocked"}
TASK_STATUSES = {"pending", "done", "blocked"}
RUN_RESUMABLE_STATUSES = {"prepared", "interrupted", "needs_human", "failed", "max_sessions"}
CLAUDE_EFFORTS = {"low", "medium", "high"}
SUPPORTED_AGENTS = {"codex", "claude"}
WORKER_ROLES = {"explorer", "worker", "verifier"}
WORKER_FINISH_STATUSES = {"success", "failed", "cancelled"}
DEFAULT_SESSION_TASK_BUDGET = 6
DEFAULT_AGENT = "codex"
RUN_RELEVANT_DIRS = {
    ".forge",
    "api",
    "app",
    "client",
    "cmd",
    "docs",
    "internal",
    "lib",
    "packages",
    "pkg",
    "scripts",
    "server",
    "src",
    "tests",
    "web",
}
RUN_RELEVANT_FILES = {
    "AGENTS.md",
    "Cargo.toml",
    "Gemfile",
    "Makefile",
    "Procfile",
    "bun.lockb",
    "composer.json",
    "compose.yaml",
    "compose.yml",
    "deno.json",
    "deno.jsonc",
    "docker-compose.yaml",
    "docker-compose.yml",
    "go.mod",
    "manage.py",
    "mix.exs",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "vite.config.js",
    "vite.config.ts",
    "yarn.lock",
}


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


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


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


def parse_timestamp(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return time.mktime(time.strptime(value, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


def format_duration(seconds: int | None) -> str:
    if seconds is None or seconds < 0:
        return "?"
    if seconds < 60:
        return f"{seconds}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


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


def ensure_optional_string(value: Any, *, path: Path, line: int, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DocParseError(path, f"{label} must be a non-empty string when present.", line=line)
    return value


def ensure_optional_agent(value: Any, *, path: Path, line: int, label: str) -> str | None:
    agent = ensure_optional_string(value, path=path, line=line, label=label)
    if agent is not None and agent not in SUPPORTED_AGENTS:
        raise DocParseError(path, f"{label} must be one of {sorted(SUPPORTED_AGENTS)}.", line=line)
    return agent


def ensure_optional_positive_int(value: Any, *, path: Path, line: int, label: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise DocParseError(path, f"{label} must be a positive integer when present.", line=line)
    return value


def normalize_owned_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def owned_paths_overlap(left: str, right: str) -> bool:
    lhs = normalize_owned_path(left)
    rhs = normalize_owned_path(right)
    if not lhs or not rhs:
        return False
    return lhs == rhs or lhs.startswith(rhs + "/") or rhs.startswith(lhs + "/")


def task_signature(task: dict[str, Any]) -> str:
    payload = {
        "title": task["title"],
        "description": task["description"],
        "depends_on": task["depends_on"],
        "verification": task["verification"],
        "artifacts": task["artifacts"],
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def detect_dependency_cycle(tasks: list[dict[str, Any]]) -> list[str] | None:
    graph = {task["id"]: task["depends_on"] for task in tasks}
    visited: set[str] = set()
    stack: list[str] = []
    active: set[str] = set()

    def visit(node: str) -> list[str] | None:
        if node in active:
            cycle_start = stack.index(node)
            return stack[cycle_start:] + [node]
        if node in visited:
            return None
        visited.add(node)
        active.add(node)
        stack.append(node)
        for dependency in graph.get(node, []):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        active.remove(node)
        return None

    for node in graph:
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def parse_prompt(root: Path) -> dict[str, Any]:
    path = root / "docs/prompt.md"
    blocks = parse_toml_blocks(path)
    if not blocks:
        raise DocParseError(path, "Add a TOML block with project, user_surface, and commands.")
    data = blocks[0].data
    project = data.get("project")
    user_surface = data.get("user_surface")
    commands = data.get("commands")
    agents = data.get("agents") or {}
    orchestration = data.get("orchestration") or {}
    if not isinstance(project, dict):
        raise DocParseError(path, "Missing [project] table.", line=blocks[0].start_line)
    if not isinstance(user_surface, dict):
        raise DocParseError(path, "Missing [user_surface] table.", line=blocks[0].start_line)
    if not isinstance(commands, dict):
        raise DocParseError(path, "Missing [commands] table.", line=blocks[0].start_line)
    if not isinstance(agents, dict):
        raise DocParseError(path, "agents must be a table when present.", line=blocks[0].start_line)
    if not isinstance(orchestration, dict):
        raise DocParseError(path, "orchestration must be a table when present.", line=blocks[0].start_line)
    if not isinstance(project.get("name"), str) or not project["name"].strip():
        raise DocParseError(path, "project.name must be a non-empty string.", line=blocks[0].start_line)
    if not isinstance(project.get("one_liner"), str) or not project["one_liner"].strip():
        raise DocParseError(path, "project.one_liner must be a non-empty string.", line=blocks[0].start_line)
    if not isinstance(user_surface.get("kind"), str) or not user_surface["kind"].strip():
        raise DocParseError(path, "user_surface.kind must be a non-empty string.", line=blocks[0].start_line)
    codex_agent = agents.get("codex") or {}
    claude_agent = agents.get("claude") or {}
    if not isinstance(codex_agent, dict):
        raise DocParseError(path, "agents.codex must be a table.", line=blocks[0].start_line)
    if not isinstance(claude_agent, dict):
        raise DocParseError(path, "agents.claude must be a table.", line=blocks[0].start_line)
    claude_effort = ensure_optional_string(claude_agent.get("effort"), path=path, line=blocks[0].start_line, label="agents.claude.effort")
    if claude_effort is not None and claude_effort not in CLAUDE_EFFORTS:
        raise DocParseError(path, f"agents.claude.effort must be one of {sorted(CLAUDE_EFFORTS)}.", line=blocks[0].start_line)
    default_agent = ensure_optional_agent(
        orchestration.get("default_agent"),
        path=path,
        line=blocks[0].start_line,
        label="orchestration.default_agent",
    )
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
        "agents": {
            "codex": {
                "model": ensure_optional_string(codex_agent.get("model"), path=path, line=blocks[0].start_line, label="agents.codex.model"),
                "profile": ensure_optional_string(codex_agent.get("profile"), path=path, line=blocks[0].start_line, label="agents.codex.profile"),
            },
            "claude": {
                "model": ensure_optional_string(claude_agent.get("model"), path=path, line=blocks[0].start_line, label="agents.claude.model"),
                "effort": claude_effort,
            },
        },
        "orchestration": {
            "default_agent": default_agent or DEFAULT_AGENT,
            "session_task_budget": ensure_optional_positive_int(
                orchestration.get("session_task_budget"),
                path=path,
                line=blocks[0].start_line,
                label="orchestration.session_task_budget",
            )
            or DEFAULT_SESSION_TASK_BUDGET
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
            verification = ensure_list_of_strings(task.get("verification"), path=path, line=block.start_line, label=f"task.{task_id}.verification")
            artifacts = ensure_list_of_strings(task.get("artifacts"), path=path, line=block.start_line, label=f"task.{task_id}.artifacts")
            if not verification:
                raise DocParseError(path, f"Task '{task_id}' must define at least one verification step.", line=block.start_line)
            normalized_tasks.append(
                {
                    "id": task_id,
                    "title": title_value,
                    "description": description,
                    "depends_on": depends_on,
                    "verification": verification,
                    "artifacts": artifacts,
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
        milestone_out_of_scope = ensure_list_of_strings(milestone.get("out_of_scope"), path=path, line=block.start_line, label="milestone.out_of_scope")
        milestone_acceptance = ensure_list_of_strings(milestone.get("acceptance"), path=path, line=block.start_line, label="milestone.acceptance")
        if not milestone_acceptance:
            raise DocParseError(path, "milestone.acceptance must include at least one acceptance criterion.", line=block.start_line)
        if not validation_commands:
            raise DocParseError(path, "validation.commands must include at least one command.", line=block.start_line)
        if not smoke_scenarios:
            raise DocParseError(path, "validation.smoke_scenarios must include at least one user-facing scenario.", line=block.start_line)
        validation_matrix = block.data.get("validation_matrix", [])
        if not isinstance(validation_matrix, list):
            raise DocParseError(path, "[[validation_matrix]] entries must be objects.", line=block.start_line)
        normalized_matrix: list[dict[str, Any]] = []
        acceptance_coverage: dict[str, int] = {item: 0 for item in milestone_acceptance}
        for entry in validation_matrix:
            if not isinstance(entry, dict):
                raise DocParseError(path, "Each [[validation_matrix]] entry must be an object.", line=block.start_line)
            acceptance_name = entry.get("acceptance")
            if not isinstance(acceptance_name, str) or not acceptance_name.strip():
                raise DocParseError(path, "validation_matrix.acceptance must be a non-empty string.", line=block.start_line)
            if acceptance_name not in acceptance_coverage:
                raise DocParseError(path, f"validation_matrix acceptance '{acceptance_name}' is not listed in milestone.acceptance.", line=block.start_line)
            verified_by = ensure_list_of_strings(entry.get("verified_by"), path=path, line=block.start_line, label=f"validation_matrix.{acceptance_name}.verified_by")
            if not verified_by:
                raise DocParseError(path, f"validation_matrix for '{acceptance_name}' must list at least one verifying artifact or command.", line=block.start_line)
            acceptance_coverage[acceptance_name] += 1
            normalized_matrix.append({"acceptance": acceptance_name, "verified_by": verified_by})
        uncovered_acceptance = [item for item, count in acceptance_coverage.items() if count == 0]
        if uncovered_acceptance:
            raise DocParseError(path, f"Every acceptance criterion must appear in [[validation_matrix]]. Missing: {', '.join(uncovered_acceptance)}.", line=block.start_line)
        milestones.append(
            {
                "id": milestone_id,
                "title": title,
                "goal": goal,
                "status": status,
                "scope": milestone_scope,
                "out_of_scope": milestone_out_of_scope,
                "acceptance": milestone_acceptance,
                "validation": {
                    "commands": validation_commands,
                    "smoke_scenarios": smoke_scenarios,
                    "stop_and_fix": bool(validation.get("stop_and_fix", True)),
                    "matrix": normalized_matrix,
                },
                "tasks": normalized_tasks,
                "line": block.start_line,
            }
        )
    active = [milestone for milestone in milestones if milestone["status"] == "active"]
    if len(active) > 1:
        raise DocParseError(path, "Only one milestone can have status='active'.", line=active[1]["line"])
    return {"path": str(path.relative_to(root)), "hash": sha256(path), "milestones": milestones}


def sync_state(root: Path) -> dict[str, Any]:
    prompt = parse_prompt(root)
    plans = parse_plans(root)
    queue_path = root / QUEUE_PATH
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
            "active_milestone": None,
            "tasks": [],
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        write_json(queue_path, queue_payload)
        return {"queue": queue_payload, "active": None, "prompt": prompt}
    task_lookup = {task["id"]: task for task in active["tasks"]}
    for task in active["tasks"]:
        missing = [dependency for dependency in task["depends_on"] if dependency not in task_lookup]
        if missing:
            raise DocParseError(root / "docs/plans.md", f"Task '{task['id']}' depends on unknown task(s): {', '.join(missing)}.", line=active["line"])
        if task["id"] in task["depends_on"]:
            raise DocParseError(root / "docs/plans.md", f"Task '{task['id']}' cannot depend on itself.", line=active["line"])
    cycle = detect_dependency_cycle(active["tasks"])
    if cycle:
        raise DocParseError(root / "docs/plans.md", f"Active milestone contains a dependency cycle: {' -> '.join(cycle)}.", line=active["line"])
    previous_milestone_id = ((existing_queue.get("active_milestone") or {}).get("id"))
    merged_tasks: list[dict[str, Any]] = []
    for index, task in enumerate(active["tasks"], start=1):
        previous = existing_tasks.get(task["id"], {})
        signature = task_signature(task)
        status = "pending"
        notes = ""
        if previous_milestone_id == active["id"] and previous.get("signature") == signature:
            status = previous.get("status", "pending")
            notes = previous.get("notes", "")
        if status not in TASK_STATUSES:
            status = "pending"
        merged_tasks.append(
            {
                "id": task["id"],
                "title": task["title"],
                "description": task["description"],
                "depends_on": task["depends_on"],
                "verification": task["verification"],
                "artifacts": task["artifacts"],
                "status": status,
                "notes": notes,
                "signature": signature,
                "priority": index,
            }
        )
    queue_payload = {
        "project": prompt["project"]["name"],
        "active_milestone": {
            "id": active["id"],
            "title": active["title"],
            "goal": active["goal"],
            "scope": active["scope"],
            "out_of_scope": active["out_of_scope"],
            "acceptance": active["acceptance"],
            "validation": active["validation"],
        },
        "tasks": merged_tasks,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(queue_path, queue_payload)
    return {"queue": queue_payload, "active": active, "prompt": prompt}


def ensure_synced(root: Path) -> dict[str, Any]:
    return sync_state(root)


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


def run_dir_for(main_root: Path, payload: dict[str, Any] | None) -> Path | None:
    if not payload or not payload.get("run_id"):
        return None
    return main_root / RUNS_DIR / payload["run_id"]


def worker_ledger_paths(main_root: Path, payload: dict[str, Any] | None) -> tuple[Path, Path] | tuple[None, None]:
    run_dir = run_dir_for(main_root, payload)
    if run_dir is None:
        return None, None
    return run_dir / WORKER_LEDGER_NAME, run_dir / WORKER_SUMMARY_NAME


def load_worker_events(main_root: Path, payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    ledger_path, _ = worker_ledger_paths(main_root, payload)
    if ledger_path is None or not ledger_path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def analyze_worker_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    workers: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    active_workers: dict[str, dict[str, Any]] = {}
    max_concurrency = 0
    parallel_spans = 0
    conflicts_detected = 0
    in_parallel = False

    for event in events:
        worker_id = event.get("worker_id")
        if not isinstance(worker_id, str) or not worker_id:
            continue
        if event.get("event") == "worker_started":
            role = event.get("role", "worker")
            task_ids = [item for item in event.get("task_ids", []) if isinstance(item, str)]
            owned_paths = [normalize_owned_path(item) for item in event.get("owned_paths", []) if isinstance(item, str)]
            worker_record = {
                "worker_id": worker_id,
                "role": role,
                "task_ids": task_ids,
                "owned_paths": owned_paths,
                "started_at": event.get("started_at"),
                "finished_at": None,
                "status": "active",
                "summary": "",
                "conflict": False,
            }
            for other in active_workers.values():
                if not worker_record["owned_paths"] or not other.get("owned_paths"):
                    continue
                if any(
                    owned_paths_overlap(path, other_path)
                    for path in worker_record["owned_paths"]
                    for other_path in other["owned_paths"]
                ):
                    worker_record["conflict"] = True
                    conflicts_detected += 1
                    break
            workers[worker_id] = worker_record
            active_workers[worker_id] = worker_record
            order.append(worker_id)
            active_count = len(active_workers)
            max_concurrency = max(max_concurrency, active_count)
            if active_count >= 2 and not in_parallel:
                parallel_spans += 1
                in_parallel = True
        elif event.get("event") == "worker_finished":
            worker_record = workers.setdefault(
                worker_id,
                {
                    "worker_id": worker_id,
                    "role": "worker",
                    "task_ids": [],
                    "owned_paths": [],
                    "started_at": None,
                    "finished_at": None,
                    "status": "active",
                    "summary": "",
                    "conflict": False,
                },
            )
            worker_record["finished_at"] = event.get("finished_at")
            worker_record["status"] = event.get("status", "unknown")
            worker_record["summary"] = event.get("summary", "")
            active_workers.pop(worker_id, None)
            if len(active_workers) < 2:
                in_parallel = False

    recent_workers: list[dict[str, Any]] = []
    failures = 0
    write_workers = 0
    read_only_workers = 0
    for worker_id in order:
        record = workers[worker_id]
        if record.get("owned_paths"):
            write_workers += 1
        else:
            read_only_workers += 1
        if record.get("status") not in {"active", "success"}:
            failures += 1
        started_at = parse_timestamp(record.get("started_at"))
        finished_at = parse_timestamp(record.get("finished_at"))
        duration_seconds = None
        if started_at is not None and finished_at is not None:
            duration_seconds = max(0, int(finished_at - started_at))
        recent_workers.append(
            {
                "worker_id": record["worker_id"],
                "role": record.get("role", "worker"),
                "status": record.get("status", "unknown"),
                "task_ids": record.get("task_ids", []),
                "owned_paths": record.get("owned_paths", []),
                "started_at": record.get("started_at"),
                "finished_at": record.get("finished_at"),
                "duration_seconds": duration_seconds,
                "summary": record.get("summary", ""),
                "conflict": bool(record.get("conflict")),
            }
        )

    summary = {
        "workers_used": len(order),
        "max_concurrency": max_concurrency,
        "parallel_spans": parallel_spans,
        "write_workers": write_workers,
        "read_only_workers": read_only_workers,
        "conflicts_detected": conflicts_detected,
        "failures": failures,
        "active_workers": len(active_workers),
        "recent_workers": recent_workers[-5:],
    }
    return {"summary": summary, "workers": workers, "active_workers": active_workers}


def write_worker_summary(main_root: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    _, summary_path = worker_ledger_paths(main_root, payload)
    if summary_path is None:
        raise ForgeError("No active run is available for worker summaries.")
    summary = analyze_worker_events(load_worker_events(main_root, payload))["summary"]
    write_json(summary_path, summary)
    return summary


def current_worker_summary(main_root: Path) -> dict[str, Any] | None:
    current = current_run(main_root)
    _, summary_path = worker_ledger_paths(main_root, current)
    if summary_path is None:
        return None
    if summary_path.exists():
        return load_json(summary_path, default=None)
    if current:
        return write_worker_summary(main_root, current)
    return None


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


def active_run_for_workers(root: Path, main_root: Path) -> dict[str, Any]:
    current = current_run(main_root)
    if not current:
        raise ForgeError("No active run is available for worker logging.")
    worktree_path = current.get("worktree_path")
    if root != main_root and worktree_path and Path(worktree_path) != root:
        raise ForgeError(f"Worker logging must target the active run worktree at {worktree_path}.")
    return current


def ensure_clean_worktree(root: Path) -> None:
    changes = blocking_run_changes(root)
    if changes:
        raise ForgeError(
            "Working tree has tracked or execution-relevant untracked changes. Commit, stash, or ignore them before starting ./forge run: "
            + ", ".join(changes)
        )


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
    validation_report = qa_result or load_json(root / VALIDATION_REPORT_PATH, default=None)
    _, main_root = repo_context(root)
    current_run_info = current_run(main_root)
    worker_summary = current_worker_summary(main_root) if current_run_info else None
    run_summary = "none"
    if current_run_info:
        run_summary = f"{current_run_info.get('run_id')} ({current_run_info.get('status', 'unknown')})"
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
        f"- Queue updated: {queue.get('updated_at', 'unknown')}",
        f"- Active milestone: {milestone_label}",
        f"- Tasks: {stats['done']}/{stats['total']} done, {stats['pending']} pending, {stats['blocked']} blocked, {stats['available']} available",
        f"- Last QA: {validation_status} at {validation_time}",
        f"- Active run: {run_summary}",
    ]
    if worker_summary and worker_summary.get("workers_used", 0) > 0:
        lines.append(
            "- Parallel workers: "
            f"{worker_summary['workers_used']} used, peak {worker_summary['max_concurrency']}, "
            f"failures {worker_summary['failures']}, conflicts {worker_summary['conflicts_detected']}"
        )
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


def workspace_fingerprint(root: Path) -> str:
    entries = []
    for entry in git_status_entries(root):
        payload = {"code": entry["code"], "path": entry["path"]}
        target = root / entry["path"]
        if target.exists() and target.is_file():
            payload["sha256"] = sha256(target)
        elif target.exists():
            payload["kind"] = "dir"
        else:
            payload["missing"] = True
        entries.append(payload)
    head = run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, check=False).stdout.strip() or "none"
    encoded = json.dumps({"head": head, "entries": entries}, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def run_qa(root: Path, *, reuse_pass: bool = False) -> dict[str, Any]:
    synced = ensure_synced(root)
    active = synced["queue"].get("active_milestone") or {}
    validation = active.get("validation") or {}
    commands = validation.get("commands") or ["./.forge/scripts/validate_static.sh", "./.forge/scripts/validate_surface.sh"]
    fingerprint = workspace_fingerprint(root)
    existing = load_json(root / VALIDATION_REPORT_PATH, default=None)
    if reuse_pass and existing and existing.get("status") == "pass" and existing.get("workspace_fingerprint") == fingerprint:
        report = dict(existing)
        report["reused"] = True
        update_documentation_status(root, qa_result=report)
        return report
    results = run_commands(commands, cwd=root)
    status = "pass" if results and all(item["exit_code"] == 0 for item in results) else "fail"
    report = {
        "status": status,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_fingerprint": fingerprint,
        "reused": False,
        "commands": results,
    }
    write_json(root / VALIDATION_REPORT_PATH, report)
    update_documentation_status(root, qa_result=report)
    report["workspace_fingerprint"] = workspace_fingerprint(root)
    write_json(root / VALIDATION_REPORT_PATH, report)
    return report


def tracked_changes(root: Path) -> list[str]:
    unstaged = run(["git", "diff", "--name-only"], cwd=root, capture_output=True).stdout.splitlines()
    staged = run(["git", "diff", "--cached", "--name-only"], cwd=root, capture_output=True).stdout.splitlines()
    return sorted({item.strip() for item in [*unstaged, *staged] if item.strip()})


def git_status_entries(root: Path) -> list[dict[str, str]]:
    status_lines = run(["git", "status", "--porcelain"], cwd=root, capture_output=True).stdout.splitlines()
    entries: list[dict[str, str]] = []
    for line in status_lines:
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if path:
            entries.append({"code": line[:2], "path": path})
    return entries


def working_tree_changes(root: Path) -> list[str]:
    return sorted({entry["path"] for entry in git_status_entries(root)})


def is_run_relevant_path(path: str) -> bool:
    normalized = path.strip().lstrip("./")
    if not normalized:
        return False
    if normalized in RUN_RELEVANT_FILES:
        return True
    head = normalized.split("/", 1)[0]
    return head in RUN_RELEVANT_DIRS


def blocking_run_changes(root: Path) -> list[str]:
    relevant: list[str] = []
    for entry in git_status_entries(root):
        path = entry["path"]
        if entry["code"] == "??":
            if is_run_relevant_path(path):
                relevant.append(path)
            continue
        relevant.append(path)
    return sorted(set(relevant))


def snapshot_open(root: Path, *, message: str | None = None) -> dict[str, Any]:
    allowed = {
        "AGENTS.md",
        "docs/prompt.md",
        "docs/prd.md",
        "docs/architecture.md",
        "docs/backlog.md",
        "docs/plans.md",
        "docs/documentation.md",
    }
    changes = []
    for entry in git_status_entries(root):
        path = entry["path"]
        if entry["code"] == "??" and path not in allowed:
            continue
        changes.append(path)
    changes = sorted(set(changes))
    outside_scope = [item for item in changes if item not in allowed]
    if outside_scope:
        raise ForgeError(
            "Open snapshot found unrelated planning changes: " + ", ".join(outside_scope)
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
    state_root = root / ".forge/state/current"
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    ensure_documentation_markers(root)
    if leave_status_note:
        update_documentation_status(root)


def current_branch(root: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root, capture_output=True).stdout.strip()


def commit_all_changes(root: Path, *, message: str) -> str | None:
    if not working_tree_changes(root):
        return None
    run(["git", "add", "-A"], cwd=root)
    run(["git", "commit", "-m", message], cwd=root)
    return message


def cleanup_run_artifacts(main_root: Path, payload: dict[str, Any] | None) -> None:
    if not payload:
        write_current_run(main_root, None)
        return
    worktree_path = payload.get("worktree_path")
    branch = payload.get("branch")
    run_id = payload.get("run_id")
    if worktree_path and Path(worktree_path).exists():
        run(["git", "worktree", "remove", "--force", worktree_path], cwd=main_root)
    if branch:
        result = run(["git", "branch", "-d", branch], cwd=main_root, capture_output=True, check=False)
        if result.returncode != 0 and "not found" not in (result.stderr or ""):
            raise ForgeError((result.stderr or result.stdout or f"Failed to delete branch {branch}.").strip())
    if run_id:
        run_dir = main_root / RUNS_DIR / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
    write_current_run(main_root, None)


def land_current_run(root: Path, main_root: Path, name: str) -> dict[str, Any]:
    current = current_run(main_root)
    if current and current.get("status") in {"prepared", "running"}:
        raise ForgeError(f"Run {current['run_id']} is still active. Finish it before landing.")
    target_root = archive_current_target(root, main_root)
    merged = False
    close_commit = None
    branch = None
    if target_root != main_root:
        ensure_clean_worktree(main_root)
        milestone = queue_stats(target_root).get("active_milestone") or {}
        close_commit = commit_all_changes(
            target_root,
            message=f"Close milestone {milestone.get('id', name)}",
        )
        branch = current["branch"] if current else current_branch(target_root)
        merge_result = run(["git", "merge", "--no-ff", "--no-edit", branch], cwd=main_root, capture_output=True, check=False)
        if merge_result.returncode != 0:
            run(["git", "merge", "--abort"], cwd=main_root, capture_output=True, check=False)
            raise ForgeError((merge_result.stderr or merge_result.stdout or f"Failed to merge {branch}.").strip())
        merged = True
    archive_root = archive_project(main_root, target_root, main_root, name, reset_root=main_root)
    cleanup_run_artifacts(main_root, current)
    return {
        "merged": merged,
        "close_commit": close_commit,
        "branch": branch,
        "archive_root": str(archive_root),
    }


def archive_project(
    archive_owner_root: Path,
    snapshot_root: Path,
    main_root: Path,
    name: str,
    *,
    reset_root: Path | None = None,
) -> Path:
    current = current_run(main_root)
    if current and current.get("status") in {"prepared", "running"}:
        raise ForgeError(f"Run {current['run_id']} is still active. Finish it before archiving.")
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", name):
        raise ForgeError("Archive name must only contain letters, numbers, hyphens, and underscores.")
    archive_root = archive_owner_root / "docs/projects" / name
    if archive_root.exists():
        existing = {item.name for item in archive_root.iterdir()}
        if existing - {"retrospective.md"}:
            raise ForgeError(f"{archive_root} already exists.")
    else:
        archive_root.mkdir(parents=True, exist_ok=False)
    retrospective_candidates = [
        snapshot_root / "docs/projects" / name / "retrospective.md",
        main_root / "docs/projects" / name / "retrospective.md",
    ]
    for candidate in retrospective_candidates:
        if candidate.exists() and not (archive_root / "retrospective.md").exists():
            shutil.copy2(candidate, archive_root / "retrospective.md")
            break
    for relative in ARCHIVE_SNAPSHOT:
        source_candidates = [snapshot_root / relative, archive_owner_root / relative, main_root / relative]
        source = next((candidate for candidate in source_candidates if candidate.exists()), None)
        if source is None:
            continue
        destination = archive_root / relative.name
        if relative.parts[:3] == (".forge", "state", "current"):
            destination = archive_root / "state" / relative.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    if current:
        ledger_path, summary_path = worker_ledger_paths(main_root, current)
        for source, destination_name in (
            (ledger_path, WORKER_LEDGER_NAME),
            (summary_path, WORKER_SUMMARY_NAME),
        ):
            if source is None or not source.exists():
                continue
            destination = archive_root / "state" / destination_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    reset_project_state(reset_root or archive_owner_root, leave_status_note=False)
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
    synced = ensure_synced(root)
    stats = queue_stats(root)
    report = load_json(root / VALIDATION_REPORT_PATH, default=None)
    queue = load_json(root / QUEUE_PATH, default={}) or {}
    current = current_run(main_root)
    worker_summary = current_worker_summary(main_root) if current else None
    default_agent = synced["prompt"]["orchestration"].get("default_agent") or DEFAULT_AGENT
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
                    "queue_updated_at": queue.get("updated_at"),
                    "default_agent": default_agent,
                    "active_run": current,
                    "worker_summary": worker_summary,
                }
            )
        )
        return 0
    milestone = stats["active_milestone"]
    print("=== Forge Status ===")
    print(f"Repo: {root}")
    print(f"Queue updated: {queue.get('updated_at', 'never')}")
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
    print(f"Default run agent: {default_agent}")
    if current:
        print(
            f"Active run: {current.get('run_id')} [{current.get('status', 'unknown')}] "
            f"agent={current.get('agent', 'unknown')} at {current.get('worktree_path')}"
        )
        if worker_summary and worker_summary.get("workers_used", 0) > 0:
            print(
                "Parallel workers: "
                f"{worker_summary['workers_used']} used | peak {worker_summary['max_concurrency']} | "
                f"conflicts {worker_summary['conflicts_detected']} | failures {worker_summary['failures']}"
            )
            for worker in worker_summary.get("recent_workers", [])[-3:]:
                owned = worker.get("owned_paths") or []
                owned_label = f" paths={','.join(owned)}" if owned else ""
                duration_label = format_duration(worker.get("duration_seconds"))
                print(
                    f"- {worker['worker_id']} {worker['role']} {worker['status']} ({duration_label}){owned_label}"
                )
        if resumable_run(main_root):
            print("Resume run: ./forge run --resume")
    else:
        print("Active run: none")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    failures: list[str] = []
    checks: list[str] = []
    git_ok = bool(shutil.which("git"))
    python_ok = bool(shutil.which("python3"))
    codex_ok = bool(shutil.which("codex"))
    claude_ok = bool(shutil.which("claude"))
    checks.append(f"git: {'ok' if git_ok else 'missing'}")
    checks.append(f"python3: {'ok' if python_ok else 'missing'}")
    checks.append(f"claude CLI: {'ok' if claude_ok else 'missing'}")
    checks.append(f"codex CLI: {'ok' if codex_ok else 'missing'}")
    prompt: dict[str, Any] | None = None
    try:
        synced = ensure_synced(root)
        prompt = synced["prompt"]
        checks.append("docs sync: ok")
    except ForgeError as exc:
        failures.append(str(exc))
    if not git_ok:
        failures.append("git is required.")
    if not python_ok:
        failures.append("python3 is required.")
    if not codex_ok and not claude_ok:
        failures.append("Install at least one supported agent CLI (codex or claude).")
    if prompt:
        if codex_ok or claude_ok:
            choice = resolve_agent_choice(prompt, codex_ok=codex_ok, claude_ok=claude_ok)
            default_agent = choice["agent"]
            if choice["mode"] == "fallback":
                checks.append(f"default run agent: {default_agent} (fallback from {choice['preferred']})")
            else:
                checks.append(f"default run agent: {default_agent}")
        else:
            checks.append("default run agent: none")
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
    report = run_qa(root, reuse_pass=args.reuse_pass)
    reused_suffix = " [cached]" if report.get("reused") else ""
    print(f"QA {report['status']}{reused_suffix} ({len(report['commands'])} command(s))")
    for item in report["commands"]:
        status = "PASS" if item["exit_code"] == 0 else f"FAIL({item['exit_code']})"
        print(f"- {status} {item['command']}")
    return 0 if report["status"] == "pass" else 1


def command_queue_stats(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    ensure_synced(root)
    print(json.dumps(queue_stats(root)))
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


def resolve_agent_choice(prompt: dict[str, Any], *, codex_ok: bool, claude_ok: bool) -> dict[str, str]:
    default_agent = prompt["orchestration"].get("default_agent") or DEFAULT_AGENT
    codex_configured = bool(prompt["agents"]["codex"].get("model") or prompt["agents"]["codex"].get("profile"))
    claude_configured = bool(prompt["agents"]["claude"].get("model"))
    if default_agent == "codex" and codex_ok and codex_configured:
        return {"agent": "codex", "preferred": default_agent, "mode": "preferred"}
    if default_agent == "claude" and claude_ok and claude_configured:
        return {"agent": "claude", "preferred": default_agent, "mode": "preferred"}
    if default_agent == "codex" and codex_ok:
        return {"agent": "codex", "preferred": default_agent, "mode": "preferred"}
    if default_agent == "claude" and claude_ok:
        return {"agent": "claude", "preferred": default_agent, "mode": "preferred"}
    if codex_ok:
        return {"agent": "codex", "preferred": default_agent, "mode": "fallback"}
    if claude_ok:
        return {"agent": "claude", "preferred": default_agent, "mode": "fallback"}
    raise ForgeError("No supported agent CLI is available.")


def command_preferred_agent(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    prompt = parse_prompt(root)
    choice = resolve_agent_choice(prompt, codex_ok=bool(shutil.which("codex")), claude_ok=bool(shutil.which("claude")))
    if args.json:
        print(json.dumps(choice))
    else:
        print(choice["agent"])
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
    if root != main_root:
        if current and current.get("worktree_path") == str(root):
            raise ForgeError("Archive active run worktrees via python3 .forge/scripts/runtime.py land-current <name>.")
        raise ForgeError("Run archive from the main workspace root only.")
    if root == main_root and current and current.get("worktree_path"):
        raise ForgeError(f"Archive from {current['worktree_path']} or merge that worktree first.")
    archive_root = archive_project(root, root, main_root, args.name)
    print(f"Archived current project snapshot to {archive_root}")
    return 0


def command_archive_current(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    target_root = archive_current_target(root, main_root)
    if target_root != main_root:
        raise ForgeError("Use python3 .forge/scripts/runtime.py land-current <name> to merge and archive an active run.")
    current = current_run(main_root)
    archive_root = archive_project(target_root, target_root, main_root, args.name)
    if current:
        cleanup_run_artifacts(main_root, current)
    print(f"Archived current project snapshot to {archive_root}")
    return 0


def command_land_current(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    result = land_current_run(root, main_root, args.name)
    archive_root = result["archive_root"]
    if result["merged"]:
        print(f"Landed active run into {main_root} and archived snapshot to {archive_root}")
    else:
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


def command_agent_profile(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    prompt = parse_prompt(root)
    payload = prompt["agents"].get(args.agent) or {}
    print(json.dumps(payload))
    return 0


def command_orchestration_setting(args: argparse.Namespace) -> int:
    root, _ = repo_context(Path.cwd())
    prompt = parse_prompt(root)
    orchestration = prompt.get("orchestration") or {}
    if args.key not in orchestration:
        raise ForgeError(f"Unknown orchestration setting: {args.key}")
    print(orchestration[args.key])
    return 0


def command_worker_start(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    current = active_run_for_workers(root, main_root)
    if args.role == "worker" and not args.owned_path:
        raise ForgeError("Write-capable workers must declare at least one --owned-path.")
    events = load_worker_events(main_root, current)
    analyzed = analyze_worker_events(events)
    if args.worker_id in analyzed["workers"]:
        raise ForgeError(f"Worker '{args.worker_id}' is already recorded for this run.")
    owned_paths = [normalize_owned_path(path) for path in args.owned_path]
    for other in analyzed["active_workers"].values():
        if not owned_paths or not other.get("owned_paths"):
            continue
        if any(
            owned_paths_overlap(path, other_path)
            for path in owned_paths
            for other_path in other["owned_paths"]
        ):
            raise ForgeError(
                f"Worker '{args.worker_id}' overlaps with active worker '{other['worker_id']}' on owned paths."
            )
    payload = {
        "event": "worker_started",
        "worker_id": args.worker_id,
        "role": args.role,
        "task_ids": args.task_id,
        "owned_paths": owned_paths,
        "started_at": now(),
    }
    ledger_path, _ = worker_ledger_paths(main_root, current)
    assert ledger_path is not None
    append_jsonl(ledger_path, payload)
    summary = write_worker_summary(main_root, current)
    print(json.dumps({"event": payload, "summary": summary}))
    return 0


def command_worker_finish(args: argparse.Namespace) -> int:
    root, main_root = repo_context(Path.cwd())
    current = active_run_for_workers(root, main_root)
    analyzed = analyze_worker_events(load_worker_events(main_root, current))
    if args.worker_id not in analyzed["workers"]:
        raise ForgeError(f"Worker '{args.worker_id}' was never started.")
    if args.worker_id not in analyzed["active_workers"]:
        raise ForgeError(f"Worker '{args.worker_id}' is not currently active.")
    payload = {
        "event": "worker_finished",
        "worker_id": args.worker_id,
        "status": args.status,
        "summary": args.summary or "",
        "finished_at": now(),
    }
    ledger_path, _ = worker_ledger_paths(main_root, current)
    assert ledger_path is not None
    append_jsonl(ledger_path, payload)
    summary = write_worker_summary(main_root, current)
    print(json.dumps({"event": payload, "summary": summary}))
    return 0


def command_worker_summary(args: argparse.Namespace) -> int:
    _, main_root = repo_context(Path.cwd())
    current = current_run(main_root)
    if not current:
        raise ForgeError("No active run is available.")
    summary = current_worker_summary(main_root) or {
        "workers_used": 0,
        "max_concurrency": 0,
        "parallel_spans": 0,
        "write_workers": 0,
        "read_only_workers": 0,
        "conflicts_detected": 0,
        "failures": 0,
        "active_workers": 0,
        "recent_workers": [],
    }
    print(json.dumps(summary))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forge v2 runtime helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--brief", action="store_true")

    subparsers.add_parser("doctor")
    qa_parser = subparsers.add_parser("qa")
    qa_parser.add_argument("--reuse-pass", action="store_true")
    subparsers.add_parser("queue-stats")

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

    land_current = subparsers.add_parser("land-current")
    land_current.add_argument("name")

    reset_current = subparsers.add_parser("reset-current")
    reset_current.add_argument("--clear-run", action="store_true")

    render_hook = subparsers.add_parser("render-hook")
    render_hook.add_argument("kind", choices=["validate_static", "validate_surface", "prepare_runtime"])

    agent_profile = subparsers.add_parser("agent-profile")
    agent_profile.add_argument("agent", choices=["codex", "claude"])

    preferred_agent = subparsers.add_parser("preferred-agent")
    preferred_agent.add_argument("--json", action="store_true")

    orchestration_setting = subparsers.add_parser("orchestration-setting")
    orchestration_setting.add_argument("key", choices=["session_task_budget"])

    worker_start = subparsers.add_parser("worker-start")
    worker_start.add_argument("--worker-id", required=True)
    worker_start.add_argument("--role", choices=sorted(WORKER_ROLES), required=True)
    worker_start.add_argument("--task-id", action="append", default=[])
    worker_start.add_argument("--owned-path", action="append", default=[])

    worker_finish = subparsers.add_parser("worker-finish")
    worker_finish.add_argument("--worker-id", required=True)
    worker_finish.add_argument("--status", choices=sorted(WORKER_FINISH_STATUSES), required=True)
    worker_finish.add_argument("--summary")

    subparsers.add_parser("worker-summary")

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
        if args.command == "land-current":
            return command_land_current(args)
        if args.command == "reset-current":
            return command_reset_current(args)
        if args.command == "render-hook":
            return command_render_hook(args)
        if args.command == "agent-profile":
            return command_agent_profile(args)
        if args.command == "preferred-agent":
            return command_preferred_agent(args)
        if args.command == "orchestration-setting":
            return command_orchestration_setting(args)
        if args.command == "worker-start":
            return command_worker_start(args)
        if args.command == "worker-finish":
            return command_worker_finish(args)
        if args.command == "worker-summary":
            return command_worker_summary(args)
    except ForgeError as exc:
        print(f"forge: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
