#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RSYNC_EXCLUDES = [
    ".git",
    ".forge/state/current",
    ".forge/runs",
    ".forge/sessions",
    ".forge/worktrees",
    "__pycache__",
]


def run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(command)}\n"
            f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def make_project_copy() -> Path:
    tempdir = Path(tempfile.mkdtemp(prefix="forge-v2-test."))
    command = ["rsync", "-a"]
    for item in RSYNC_EXCLUDES:
        command.extend(["--exclude", item])
    command.extend([f"{REPO_ROOT}/", str(tempdir)])
    run(command, REPO_ROOT)
    return tempdir


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class ForgeRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project = make_project_copy()
        write_file(
            self.project / "AGENTS.md",
            """
            # AGENTS

            Use ./forge status before starting work.
            """,
        )
        write_file(
            self.project / "docs/prompt.md",
            """
            # Prompt

            ```toml
            [project]
            name = "Smoke Project"
            one_liner = "Validate the Forge v2 runtime"

            [user_surface]
            kind = "cli"
            entrypoint = "./forge"

            [commands]
            runtime_prepare = []
            runtime_doctor = []
            validate_static = ["test -f docs/plans.md"]
            validate_surface = ["test -f docs/documentation.md"]
            ```
            """,
        )
        write_file(
            self.project / "docs/implement.md",
            """
            # Implement

            Keep scope inside the active milestone and run ./forge qa before exit.
            """,
        )
        write_file(self.project / "docs/prd.md", "# PRD\n")
        write_file(self.project / "docs/architecture.md", "# Architecture\n")
        write_file(self.project / "docs/conventions.md", "# Conventions\n")
        write_file(self.project / "docs/tech_stack.md", "# Tech Stack\n")
        write_file(self.project / "docs/backlog.md", "# Backlog\n")
        run(["git", "init", "-q"], self.project)
        run(["git", "config", "user.name", "Forge Test"], self.project)
        run(["git", "config", "user.email", "forge@example.com"], self.project)
        run(["bash", ".forge/scripts/scaffold.sh"], self.project)

    def tearDown(self) -> None:
        shutil.rmtree(self.project)

    def test_status_reports_doc_errors_with_line_numbers(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Invalid milestone"
            goal = "Trigger dependency validation"
            status = "active"

            [[task]]
            id = "task-a"
            title = "Broken dependency"
            description = "This task references a missing dependency."
            depends_on = ["task-missing"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true
            ```
            """,
        )

        result = run(["./forge", "status"], self.project, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("docs/plans.md:", result.stderr)
        self.assertIn("depends on unknown task(s): task-missing", result.stderr)

    def test_doctor_executes_prepare_runtime_doctor_commands(self) -> None:
        write_file(
            self.project / "docs/prompt.md",
            """
            # Prompt

            ```toml
            [project]
            name = "Smoke Project"
            one_liner = "Validate doctor hooks"

            [user_surface]
            kind = "cli"
            entrypoint = "./forge"

            [commands]
            runtime_prepare = []
            runtime_doctor = ["test -f .doctor-sentinel"]
            validate_static = ["test -f docs/plans.md"]
            validate_surface = ["test -f docs/documentation.md"]
            ```
            """,
        )
        hook = run(["python3", ".forge/scripts/runtime.py", "render-hook", "prepare_runtime"], self.project)
        prepare_runtime = self.project / ".forge/scripts/prepare_runtime.sh"
        prepare_runtime.write_text(hook.stdout, encoding="utf-8")
        os.chmod(prepare_runtime, 0o755)

        doctor_fail = run(["./forge", "doctor"], self.project, check=False)
        self.assertNotEqual(doctor_fail.returncode, 0)
        self.assertIn("prepare_runtime.sh", doctor_fail.stdout)

        (self.project / ".doctor-sentinel").write_text("ok\n", encoding="utf-8")
        doctor_pass = run(["./forge", "doctor"], self.project)
        self.assertIn("All checks passed.", doctor_pass.stdout)

    def test_run_prepares_worktree_and_archive_must_happen_there(self) -> None:
        run_result = run(["./forge", "run", "codex"], self.project)
        self.assertIn("No active milestone. Run forge-open first.", run_result.stdout)

        current_run = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current_run["status"], "idle")
        worktree = Path(current_run["worktree_path"])
        self.assertTrue((worktree / ".forge/run-context.json").exists())

        root_status = run(["./forge", "status"], self.project)
        self.assertIn(str(worktree), root_status.stdout)
        self.assertIn("Milestone: none", root_status.stdout)
        self.assertIn("idle", root_status.stdout)

        archive_from_root = run(["./forge", "archive", "blocked-phase"], self.project, check=False)
        self.assertNotEqual(archive_from_root.returncode, 0)
        self.assertIn("Archive from", archive_from_root.stderr)

        archive_from_worktree = run(["./forge", "archive", "blocked-phase"], worktree)
        self.assertIn("Archived current project snapshot", archive_from_worktree.stdout)
        self.assertTrue((worktree / "docs/projects/blocked-phase/documentation.md").exists())
        self.assertFalse((self.project / ".forge/runs/current.json").exists())


if __name__ == "__main__":
    unittest.main()
