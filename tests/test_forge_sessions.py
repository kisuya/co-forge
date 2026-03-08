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
    ".forge/worktrees",
    "__pycache__",
]


def run(command: list[str], cwd: Path, *, check: bool = True, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, env=env)
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
        write_file(self.project / "docs/prd.md", "# PRD\n")
        write_file(self.project / "docs/architecture.md", "# Architecture\n")
        write_file(self.project / "docs/backlog.md", "# Backlog\n")
        run(["git", "init", "-q"], self.project)
        run(["git", "config", "user.name", "Forge Test"], self.project)
        run(["git", "config", "user.email", "forge@example.com"], self.project)
        run(["bash", ".forge/scripts/scaffold.sh"], self.project)

    def tearDown(self) -> None:
        shutil.rmtree(self.project)

    def isolated_path_env(self, *, include_codex: bool = False, include_claude: bool = False) -> dict[str, str]:
        bindir = self.project / ".forge/worktrees/.tmp-bin"
        bindir.mkdir(parents=True, exist_ok=True)
        for tool in ("git", "python3"):
            target = shutil.which(tool)
            assert target is not None
            link = bindir / tool
            if link.exists() or link.is_symlink():
                link.unlink()
            os.symlink(target, link)
        if include_codex:
            (bindir / "codex").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            os.chmod(bindir / "codex", 0o755)
        if include_claude:
            (bindir / "claude").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            os.chmod(bindir / "claude", 0o755)
        env = os.environ.copy()
        env["PATH"] = f"{bindir}:/usr/bin:/bin"
        return env

    def install_stub_codex(self, mode: str) -> dict[str, str]:
        bindir = self.project / ".forge/worktrees/.tmp-bin"
        bindir.mkdir(parents=True, exist_ok=True)
        for tool in ("git", "python3"):
            target = shutil.which(tool)
            assert target is not None
            link = bindir / tool
            if link.exists() or link.is_symlink():
                link.unlink()
            os.symlink(target, link)
        stub = bindir / "codex"
        stub.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/bash
                set -euo pipefail
                if [ -n "${{FORGE_CAPTURE_CODEX_ARGS:-}}" ]; then
                  printf '%s\n' "$@" > "$FORGE_CAPTURE_CODEX_ARGS"
                fi
                if [ -n "${{FORGE_CAPTURE_CODEX_PROMPT:-}}" ]; then
                  last_arg="${{!#}}"
                  printf '%s' "$last_arg" > "$FORGE_CAPTURE_CODEX_PROMPT"
                fi
                case "${{FORGE_TEST_AGENT_MODE:-{mode}}}" in
                  progress)
                    printf 'progress\\n' >> milestone-output.txt
                    ;;
                  complete)
                    printf 'done\\n' > milestone-output.txt
                    python3 - <<'PY'
import json
from pathlib import Path

queue_path = Path('.forge/state/current/queue.json')
queue = json.loads(queue_path.read_text(encoding='utf-8'))
for task in queue.get('tasks', []):
    task['status'] = 'done'
    task['notes'] = f"completed by stub for {{task['id']}}"
queue_path.write_text(json.dumps(queue, indent=2) + '\\n', encoding='utf-8')

docs_path = Path('docs/documentation.md')
content = docs_path.read_text(encoding='utf-8')
marker = "## Session Notes\\n"
note = "- Stub agent completed the milestone in the active worktree.\\n"
if note not in content and marker in content:
    content = content.replace(marker, marker + note, 1)
docs_path.write_text(content, encoding='utf-8')
PY
                    ;;
                  notes)
                    printf '\\n- synthetic progress\\n' >> docs/documentation.md
                    ;;
                  pwdfail)
                    printf '%s\\n' "$PWD" > forge-run-cwd.txt
                    exit 1
                    ;;
                  noop)
                    ;;
                  *)
                    echo "unknown FORGE_TEST_AGENT_MODE" >&2
                    exit 2
                    ;;
                esac
                exit 0
                """
            ),
            encoding="utf-8",
        )
        os.chmod(stub, 0o755)
        env = os.environ.copy()
        env["PATH"] = f"{bindir}:/usr/bin:/bin"
        env["FORGE_TEST_AGENT_MODE"] = mode
        return env

    def write_active_plan(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Milestone"
            goal = "Drive orchestrator tests"
            status = "active"
            scope = ["scope"]
            out_of_scope = ["next milestone"]
            acceptance = ["acceptance"]

            [[task]]
            id = "task-a"
            title = "Task A"
            description = "Keep one task pending."
            depends_on = []
            verification = ["Run milestone validations"]
            artifacts = ["tests/task_a.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh", "./.forge/scripts/validate_surface.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "acceptance"
            verified_by = ["tests/task_a.py", "./.forge/scripts/validate_surface.sh"]
            ```
            """,
        )
        run(["python3", ".forge/scripts/runtime.py", "sync"], self.project)
        run(["git", "add", "docs/plans.md", "docs/documentation.md"], self.project)
        run(["git", "commit", "-m", "Open milestone m1"], self.project)

    def test_status_reports_run_and_not_phase_session_state(self) -> None:
        status = run(["./forge", "status"], self.project)
        self.assertIn("Queue updated:", status.stdout)
        self.assertIn("Active run: none", status.stdout)
        self.assertNotIn("Active phase session:", status.stdout)

    def test_task_status_resets_when_task_definition_changes(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Milestone"
            goal = "Track task semantics"
            status = "active"
            scope = ["scope"]
            out_of_scope = ["other work"]
            acceptance = ["acceptance"]

            [[task]]
            id = "task-a"
            title = "Initial task"
            description = "First description."
            depends_on = []
            verification = ["Run static validation"]
            artifacts = ["tests/task_a.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "acceptance"
            verified_by = ["tests/task_a.py"]
            ```
            """,
        )
        run(["python3", ".forge/scripts/runtime.py", "sync"], self.project)
        queue_path = self.project / ".forge/state/current/queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["tasks"][0]["status"] = "done"
        queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")

        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Milestone"
            goal = "Track task semantics"
            status = "active"
            scope = ["scope"]
            out_of_scope = ["other work"]
            acceptance = ["acceptance"]

            [[task]]
            id = "task-a"
            title = "Changed task"
            description = "Second description."
            depends_on = []
            verification = ["Run surface validation"]
            artifacts = ["tests/task_a_v2.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "acceptance"
            verified_by = ["tests/task_a_v2.py"]
            ```
            """,
        )
        run(["python3", ".forge/scripts/runtime.py", "sync"], self.project)
        updated = json.loads(queue_path.read_text(encoding="utf-8"))
        self.assertEqual(updated["tasks"][0]["status"], "pending")
        self.assertNotIn("description", updated["tasks"][0])

    def test_run_resumes_existing_worktree_by_default(self) -> None:
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "claude", "--run-id", "resume-check"],
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
        self.assertIn("Agent: claude", resumed.stdout)
        self.assertIn("No active milestone. Run forge-open first.", resumed.stdout)

        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["run_id"], "resume-check")
        self.assertEqual(current["worktree_path"], prepared_payload["worktree_path"])
        self.assertEqual(current["status"], "idle")
        self.assertEqual(current["agent"], "claude")

    def test_public_lifecycle_runs_in_worktree_and_lands_cleanly(self) -> None:
        write_file(
            self.project / "docs/prompt.md",
            """
            # Prompt

            ```toml
            [project]
            name = "Lifecycle Project"
            one_liner = "Exercise public forge lifecycle commands"

            [user_surface]
            kind = "cli"
            entrypoint = "./forge"

            [commands]
            runtime_prepare = []
            runtime_doctor = []
            validate_static = ["test -f milestone-output.txt"]
            validate_surface = ["grep -q '^done$' milestone-output.txt"]

            [orchestration]
            default_agent = "codex"
            ```
            """,
        )
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1-public"
            title = "Public lifecycle milestone"
            goal = "Verify the public forge lifecycle end to end."
            status = "active"
            scope = ["Create one shipped artifact inside the run worktree"]
            out_of_scope = ["Multiple milestones"]
            acceptance = ["A public run can complete and land without mutating main before close"]

            [[task]]
            id = "task-ship"
            title = "Create shipped artifact"
            description = "Write milestone-output.txt from the active worktree and close the queue."
            depends_on = []
            verification = ["test -f milestone-output.txt"]
            artifacts = ["milestone-output.txt"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh", "./.forge/scripts/validate_surface.sh"]
            smoke_scenarios = ["A run writes the artifact in the isolated worktree, then land-current brings it back to main."]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "A public run can complete and land without mutating main before close"
            verified_by = ["milestone-output.txt", "./.forge/scripts/validate_surface.sh"]
            ```
            """,
        )
        run(["./forge", "doctor"], self.project)
        run(["python3", ".forge/scripts/runtime.py", "sync"], self.project)
        run(["python3", ".forge/scripts/runtime.py", "snapshot-open"], self.project)

        env = self.install_stub_codex("complete")
        result = run(["./forge", "run", "codex", "--fresh"], self.project, env=env)
        self.assertIn("Active milestone complete.", result.stdout)

        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["status"], "milestone_complete")
        worktree = Path(current["worktree_path"])
        self.assertTrue((worktree / "milestone-output.txt").exists())
        self.assertFalse((self.project / "milestone-output.txt").exists())

        status = run(["./forge", "status"], self.project)
        self.assertIn("Tasks: 1/1 done | 0 pending | 0 blocked | 0 available", status.stdout)
        self.assertIn("Acceptance coverage: 1/1 mapped", status.stdout)
        self.assertIn("Active run:", status.stdout)
        self.assertIn("[milestone_complete]", status.stdout)

        landed = run(["python3", ".forge/scripts/runtime.py", "land-current", "public-lifecycle"], self.project)
        self.assertIn("Landed active run into", landed.stdout)
        self.assertTrue((self.project / "milestone-output.txt").exists())
        self.assertFalse(worktree.exists())
        self.assertFalse((self.project / ".forge/runs/current.json").exists())
        self.assertTrue((self.project / "docs/projects/public-lifecycle/state/queue.json").exists())
        archived_queue = json.loads((self.project / "docs/projects/public-lifecycle/state/queue.json").read_text(encoding="utf-8"))
        self.assertEqual(archived_queue["tasks"][0]["status"], "done")
        branches = run(["git", "branch", "--list", "codex/run-*"], self.project)
        self.assertEqual(branches.stdout.strip(), "")

    def test_run_executes_orchestrator_inside_worktree(self) -> None:
        self.write_active_plan()
        env = self.install_stub_codex("pwdfail")

        result = run(["./forge", "run", "codex", "--fresh"], self.project, env=env, check=False)
        self.assertNotEqual(result.returncode, 0)

        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        worktree = Path(current["worktree_path"])
        self.assertEqual((worktree / "forge-run-cwd.txt").read_text(encoding="utf-8").strip(), str(worktree))
        self.assertFalse((self.project / "forge-run-cwd.txt").exists())

    def test_run_prefers_available_agent_when_codex_missing(self) -> None:
        env = self.isolated_path_env(include_claude=True)
        run_result = run(["./forge", "run", "--fresh"], self.project, env=env)
        self.assertIn("Agent: claude", run_result.stdout)
        self.assertIn("No active milestone. Run forge-open first.", run_result.stdout)

    def test_run_prefers_prompt_default_agent_when_both_are_available(self) -> None:
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

            [orchestration]
            default_agent = "claude"
            ```
            """,
        )
        run(["git", "add", "docs/prompt.md"], self.project)
        run(["git", "commit", "-m", "Set default agent to claude"], self.project)
        env = self.isolated_path_env(include_codex=True, include_claude=True)
        run_result = run(["./forge", "run", "--fresh"], self.project, env=env)
        self.assertIn("Agent: claude", run_result.stdout)

    def test_run_reports_fallback_when_default_agent_is_unavailable(self) -> None:
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

            [orchestration]
            default_agent = "claude"
            ```
            """,
        )
        run(["git", "add", "docs/prompt.md"], self.project)
        run(["git", "commit", "-m", "Prefer claude"], self.project)
        env = self.isolated_path_env(include_codex=True)
        run_result = run(["./forge", "run", "--fresh"], self.project, env=env)
        self.assertIn("Agent: codex", run_result.stdout)
        self.assertIn("Preferred agent claude unavailable; using codex.", run_result.stderr)

    def test_run_blocks_on_untracked_changes_before_prepare(self) -> None:
        (self.project / "docs/untracked-spec.md").write_text("# Draft\n", encoding="utf-8")
        blocked = run(["./forge", "run", "--fresh"], self.project, check=False)
        self.assertNotEqual(blocked.returncode, 0)
        self.assertIn("execution-relevant untracked changes", blocked.stderr)

    def test_run_ignores_irrelevant_untracked_scratch_before_prepare(self) -> None:
        (self.project / "notes/scratch.md").parent.mkdir(parents=True, exist_ok=True)
        (self.project / "notes/scratch.md").write_text("todo\n", encoding="utf-8")
        env = self.isolated_path_env(include_codex=True)
        allowed = run(["./forge", "run", "--fresh"], self.project, env=env)
        self.assertIn("Agent: codex", allowed.stdout)
        self.assertIn("No active milestone. Run forge-open first.", allowed.stdout)

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

    def test_land_current_from_main_root_merges_worktree_and_resets_main_copy(self) -> None:
        self.write_active_plan()
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
        worktree = Path(prepared_payload["worktree_path"])
        (worktree / "milestone-output.txt").write_text("shipped\n", encoding="utf-8")
        (worktree / "docs/backlog.md").write_text("# Backlog\n\n- carry forward\n", encoding="utf-8")
        queue_path = worktree / ".forge/state/current/queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["tasks"][0]["status"] = "done"
        queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
        validation_path = worktree / ".forge/state/current/last_validation.json"
        validation_path.write_text(
            json.dumps({"status": "pass", "finished_at": "now", "commands": []}, indent=2) + "\n",
            encoding="utf-8",
        )

        archived = run(
            ["python3", ".forge/scripts/runtime.py", "land-current", "close-phase"],
            self.project,
        )
        self.assertIn("Landed active run into", archived.stdout)
        self.assertTrue((self.project / "milestone-output.txt").exists())
        self.assertIn("carry forward", (self.project / "docs/backlog.md").read_text(encoding="utf-8"))
        self.assertFalse((self.project / ".forge/runs/current.json").exists())
        self.assertIn(
            "No active milestone. Run `/forge-open` or `$forge-open` to open the next phase.",
            (self.project / "docs/plans.md").read_text(encoding="utf-8"),
        )
        self.assertTrue((self.project / "docs/projects/close-phase/documentation.md").exists())
        archived_queue = json.loads((self.project / "docs/projects/close-phase/state/queue.json").read_text(encoding="utf-8"))
        archived_validation = json.loads((self.project / "docs/projects/close-phase/state/last_validation.json").read_text(encoding="utf-8"))
        self.assertEqual(archived_queue["tasks"][0]["status"], "done")
        self.assertEqual(archived_validation["status"], "pass")
        self.assertFalse(worktree.exists())
        branches = run(["git", "branch", "--list", "codex/run-close-check"], self.project)
        self.assertEqual(branches.stdout.strip(), "")

    def test_worker_ledger_summary_is_visible_in_status(self) -> None:
        self.write_active_plan()
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "worker-check"],
            self.project,
        )
        worktree = Path(json.loads(prepared.stdout)["worktree_path"])

        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-start",
                "--worker-id",
                "w1",
                "--role",
                "explorer",
                "--task-id",
                "task-a",
            ],
            worktree,
        )
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-start",
                "--worker-id",
                "w2",
                "--role",
                "worker",
                "--task-id",
                "task-a",
                "--owned-path",
                "src/ui/form",
                "--owned-path",
                "tests/ui/form",
            ],
            worktree,
        )
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-finish",
                "--worker-id",
                "w1",
                "--status",
                "success",
                "--summary",
                "Explored the form API",
            ],
            worktree,
        )
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-finish",
                "--worker-id",
                "w2",
                "--status",
                "success",
                "--summary",
                "Implemented the form slice",
            ],
            worktree,
        )

        status = run(["./forge", "status"], self.project)
        self.assertIn("Parallel workers: 2 used | peak 2", status.stdout)
        self.assertIn("- w2 worker success", status.stdout)

        summary = run(["python3", ".forge/scripts/runtime.py", "worker-summary"], worktree)
        payload = json.loads(summary.stdout)
        self.assertEqual(payload["workers_used"], 2)
        self.assertEqual(payload["max_concurrency"], 2)
        self.assertEqual(payload["write_workers"], 1)
        self.assertEqual(payload["read_only_workers"], 1)

    def test_worker_start_rejects_overlapping_owned_paths(self) -> None:
        self.write_active_plan()
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "worker-overlap"],
            self.project,
        )
        worktree = Path(json.loads(prepared.stdout)["worktree_path"])

        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-start",
                "--worker-id",
                "w1",
                "--role",
                "worker",
                "--task-id",
                "task-a",
                "--owned-path",
                "src/ui",
            ],
            worktree,
        )
        conflict = run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-start",
                "--worker-id",
                "w2",
                "--role",
                "worker",
                "--task-id",
                "task-a",
                "--owned-path",
                "src/ui/form",
            ],
            worktree,
            check=False,
        )
        self.assertNotEqual(conflict.returncode, 0)
        self.assertIn("overlaps with active worker", conflict.stderr)

    def test_land_current_archives_worker_ledger(self) -> None:
        self.write_active_plan()
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "worker-archive"],
            self.project,
        )
        prepared_payload = json.loads(prepared.stdout)
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "set-run-status",
                "--run-id",
                "worker-archive",
                "--status",
                "needs_human",
            ],
            self.project,
        )
        worktree = Path(prepared_payload["worktree_path"])
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-start",
                "--worker-id",
                "w1",
                "--role",
                "explorer",
                "--task-id",
                "task-a",
            ],
            worktree,
        )
        run(
            [
                "python3",
                ".forge/scripts/runtime.py",
                "worker-finish",
                "--worker-id",
                "w1",
                "--status",
                "success",
                "--summary",
                "Investigated API contract",
            ],
            worktree,
        )
        queue_path = worktree / ".forge/state/current/queue.json"
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        queue["tasks"][0]["status"] = "done"
        queue_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
        validation_path = worktree / ".forge/state/current/last_validation.json"
        validation_path.write_text(
            json.dumps({"status": "pass", "finished_at": "now", "commands": []}, indent=2) + "\n",
            encoding="utf-8",
        )

        run(["python3", ".forge/scripts/runtime.py", "land-current", "worker-archive"], self.project)

        archived_summary = json.loads(
            (self.project / "docs/projects/worker-archive/state/worker-summary.json").read_text(encoding="utf-8")
        )
        archived_ledger = (self.project / "docs/projects/worker-archive/state/workers.jsonl").read_text(encoding="utf-8")
        self.assertEqual(archived_summary["workers_used"], 1)
        self.assertIn("\"worker_id\": \"w1\"", archived_ledger)

    def test_reset_current_preserves_human_documentation_sections(self) -> None:
        documentation = self.project / "docs/documentation.md"
        documentation.write_text(
            textwrap.dedent(
                """
                # Documentation

                <!-- forge:status:start -->
                old
                <!-- forge:status:end -->

                ## Session Notes
                - keep this note

                ## Decisions
                - keep this decision

                ## Known Issues
                - keep this issue
                """
            ).lstrip(),
            encoding="utf-8",
        )

        run(["python3", ".forge/scripts/runtime.py", "reset-current"], self.project)

        content = documentation.read_text(encoding="utf-8")
        self.assertIn("keep this note", content)
        self.assertIn("keep this decision", content)
        self.assertIn("keep this issue", content)
        self.assertIn("## Machine Status", content)

    def test_orchestrator_treats_material_file_change_as_progress(self) -> None:
        self.write_active_plan()
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "progress-check"],
            self.project,
        )
        worktree = Path(json.loads(prepared.stdout)["worktree_path"])
        env = self.install_stub_codex("progress")

        result = run(["./.forge/scripts/orchestrate.sh", "codex", "3"], worktree, env=env)

        self.assertIn("Reached max sessions.", result.stdout)
        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["status"], "max_sessions")

    def test_orchestrator_uses_slim_prompt_and_run_specific_mcp_override(self) -> None:
        self.write_active_plan()
        documentation = self.project / "docs/documentation.md"
        documentation.write_text(
            documentation.read_text(encoding="utf-8") + "\n## Extra\n" + ("very long context line\n" * 40),
            encoding="utf-8",
        )
        run(["git", "add", "docs/documentation.md"], self.project)
        run(["git", "commit", "-m", "Add long documentation note"], self.project)
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "prompt-check"],
            self.project,
        )
        worktree = Path(json.loads(prepared.stdout)["worktree_path"])
        env = self.install_stub_codex("noop")
        args_path = worktree / "captured-codex-args.txt"
        prompt_path = worktree / "captured-codex-prompt.txt"
        env["FORGE_CAPTURE_CODEX_ARGS"] = str(args_path)
        env["FORGE_CAPTURE_CODEX_PROMPT"] = str(prompt_path)

        run(["./.forge/scripts/orchestrate.sh", "codex", "1"], worktree, env=env)

        args_output = args_path.read_text(encoding="utf-8")
        prompt_output = prompt_path.read_text(encoding="utf-8")
        self.assertIn("mcp_servers={}", args_output)
        self.assertIn("Read these files directly", prompt_output)
        self.assertIn("AGENTS.md", prompt_output)
        self.assertNotIn("## Durable Spec", prompt_output)
        self.assertNotIn("very long context line", prompt_output)

    def test_orchestrator_ignores_documentation_note_only_churn(self) -> None:
        self.write_active_plan()
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "notes-check"],
            self.project,
        )
        worktree = Path(json.loads(prepared.stdout)["worktree_path"])
        env = self.install_stub_codex("notes")

        result = run(["./.forge/scripts/orchestrate.sh", "codex", "5"], worktree, env=env)

        self.assertIn("No measurable progress for 3 sessions. Stopping.", result.stdout)
        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["status"], "needs_human")
        commits = run(["git", "log", "--grep=^Session ", "--oneline"], worktree)
        self.assertEqual(commits.stdout.strip(), "")

    def test_orchestrator_stops_after_three_sessions_without_progress(self) -> None:
        self.write_active_plan()
        prepared = run(
            ["python3", ".forge/scripts/runtime.py", "prepare-run", "codex", "--run-id", "stall-check"],
            self.project,
        )
        worktree = Path(json.loads(prepared.stdout)["worktree_path"])
        env = self.install_stub_codex("noop")

        result = run(["./.forge/scripts/orchestrate.sh", "codex", "5"], worktree, env=env)

        self.assertIn("No measurable progress for 3 sessions. Stopping.", result.stdout)
        current = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current["status"], "needs_human")


if __name__ == "__main__":
    unittest.main()
