#!/usr/bin/env python3

from __future__ import annotations

import json
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
    tempdir = Path(tempfile.mkdtemp(prefix="forge-v2-session-test."))
    command = ["rsync", "-a"]
    for item in RSYNC_EXCLUDES:
        command.extend(["--exclude", item])
    command.extend([f"{REPO_ROOT}/", str(tempdir)])
    run(command, REPO_ROOT)
    return tempdir


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


class ForgeSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.project = make_project_copy()
        write_file(self.project / "AGENTS.md", "# AGENTS\n")
        write_file(
            self.project / "docs/prompt.md",
            """
            # Prompt

            ```toml
            [project]
            name = "Session Project"
            one_liner = "Exercise session resume behavior"

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
        write_file(self.project / "docs/implement.md", "# Implement\n")
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

    def test_phase_session_resumes_and_status_reports_next_action(self) -> None:
        created = run(
            ["python3", ".forge/scripts/runtime.py", "session-start", "--phase", "open"],
            self.project,
        )
        created_payload = json.loads(created.stdout)
        self.assertEqual(created_payload["mode"], "created")

        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "session-update",
                "--session-id",
                created_payload["session_id"],
                "--status",
                "awaiting_review",
                "--next-action",
                "Review docs/plans.md with the user.",
                "--draft-file",
                "docs/plans.md",
                "--pending-question",
                "Include export in this milestone?",
            ],
            self.project,
        )

        resumed = run(
            ["python3", ".forge/scripts/runtime.py", "session-start", "--phase", "open"],
            self.project,
        )
        resumed_payload = json.loads(resumed.stdout)
        self.assertEqual(resumed_payload["mode"], "resume")
        self.assertEqual(resumed_payload["session_id"], created_payload["session_id"])

        status = run(["./forge", "status"], self.project)
        self.assertIn("Active phase session:", status.stdout)
        self.assertIn("/forge-open", status.stdout)
        self.assertIn("Review docs/plans.md with the user.", status.stdout)

        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "session-complete",
                "--session-id",
                created_payload["session_id"],
                "--status",
                "deferred",
            ],
            self.project,
        )
        deferred_status = run(["./forge", "status"], self.project)
        self.assertIn("deferred", deferred_status.stdout)

    def test_run_resumes_existing_worktree_by_default(self) -> None:
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "resume-check"],
            self.project,
        )
        prepared_payload = json.loads(prepared.stdout)
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "set-run-status",
                "--run-id",
                "resume-check",
                "--status",
                "interrupted",
            ],
            self.project,
        )

        resumed = run(["./forge", "run"], self.project)
        self.assertIn("Run ID: resume-check", resumed.stdout)
        self.assertIn("No active milestone. Run forge-open first.", resumed.stdout)

        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["run_id"], "resume-check")
        self.assertEqual(current["worktree_path"], prepared_payload["worktree_path"])
        self.assertEqual(current["status"], "idle")

    def test_stale_running_run_is_recovered_for_resume(self) -> None:
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "stale-check"],
            self.project,
        )
        prepared_payload = json.loads(prepared.stdout)
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "set-run-status",
                "--run-id",
                "stale-check",
                "--status",
                "running",
                "--pid",
                "999999",
            ],
            self.project,
        )

        status = run(["./forge", "status"], self.project)
        self.assertIn("stale-check [interrupted]", status.stdout)
        self.assertIn("./forge run --resume", status.stdout)

        resumed = run(["./forge", "run", "--resume"], self.project)
        self.assertIn("Run ID: stale-check", resumed.stdout)
        self.assertIn("No active milestone. Run forge-open first.", resumed.stdout)

        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["run_id"], "stale-check")
        self.assertEqual(current["worktree_path"], prepared_payload["worktree_path"])
        self.assertEqual(current["status"], "idle")

    def test_archive_current_from_main_root_resets_main_copy(self) -> None:
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "close-check"],
            self.project,
        )
        prepared_payload = json.loads(prepared.stdout)
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "set-run-status",
                "--run-id",
                "close-check",
                "--status",
                "needs_human",
            ],
            self.project,
        )

        archived = run(
            ["python3", ".forge/scripts/runtime.py", "archive-current", "close-phase"],
            self.project,
        )
        self.assertIn("Archived current project snapshot", archived.stdout)
        self.assertFalse((self.project / ".forge/runs/current.json").exists())
        self.assertIn(
            "No active milestone. Run `/forge-open` or `$forge-open` to open the next phase.",
            (self.project / "docs/plans.md").read_text(encoding="utf-8"),
        )

        worktree = Path(prepared_payload["worktree_path"])
        self.assertTrue((worktree / "docs/projects/close-phase/documentation.md").exists())


if __name__ == "__main__":
    unittest.main()
