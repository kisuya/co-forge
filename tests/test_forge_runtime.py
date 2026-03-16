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

            [agents.codex]
            model = "gpt-5.4"

            [agents.claude]
            model = "claude-opus-4-6"
            effort = "high"
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
            scope = ["dependency check"]
            out_of_scope = ["shipping"]
            acceptance = ["Known dependencies resolve"]

            [[task]]
            id = "task-a"
            title = "Broken dependency"
            description = "This task references a missing dependency."
            depends_on = ["task-missing"]
            verification = ["Queue dependency graph validates"]
            artifacts = ["docs/plans.md"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "Known dependencies resolve"
            verified_by = ["./.forge/scripts/validate_static.sh"]
            ```
            """,
        )

        result = run(["./forge", "status"], self.project, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("docs/plans.md:", result.stderr)
        self.assertIn("depends on unknown task(s): task-missing", result.stderr)

    def test_status_does_not_dirty_tracked_docs(self) -> None:
        before = run(["git", "status", "--short"], self.project)
        self.assertEqual(before.stdout.strip(), "")

        run(["./forge", "status"], self.project)

        after = run(["git", "status", "--short"], self.project)
        self.assertEqual(after.stdout.strip(), "")

    def test_cycle_in_plans_is_rejected(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Cyclic milestone"
            goal = "Reject cycles"
            status = "active"
            scope = ["cycle"]
            out_of_scope = ["shipping"]
            acceptance = ["none"]

            [[task]]
            id = "task-a"
            title = "A"
            description = "Depends on B."
            depends_on = ["task-b"]
            verification = ["Dependency graph is acyclic"]
            artifacts = ["docs/plans.md"]

            [[task]]
            id = "task-b"
            title = "B"
            description = "Depends on A."
            depends_on = ["task-a"]
            verification = ["Dependency graph is acyclic"]
            artifacts = ["docs/plans.md"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "none"
            verified_by = ["./.forge/scripts/validate_static.sh"]
            ```
            """,
        )

        result = run(["./forge", "status"], self.project, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency cycle", result.stderr)

    def test_agent_profile_is_parsed_from_prompt(self) -> None:
        result = run(["python3", ".forge/scripts/runtime.py", "agent-profile", "claude"], self.project)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["model"], "claude-opus-4-6")
        self.assertEqual(payload["effort"], "high")

    def test_session_brief_is_summary_not_full_doc_dump(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Slim prompt"
            goal = "Keep session prompts compact"
            status = "active"
            scope = ["scope one", "scope two"]
            out_of_scope = ["scope three"]
            acceptance = ["Users can finish the flow"]

            [[task]]
            id = "task-a"
            title = "Task A"
            description = "Task description."
            depends_on = []
            verification = ["Run static validation"]
            artifacts = ["tests/test_a.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "Users can finish the flow"
            verified_by = ["tests/test_a.py"]
            ```
            """,
        )
        write_file(
            self.project / "docs/documentation.md",
            """
            # Documentation

            <!-- forge:status:start -->
            _No machine status yet._
            <!-- forge:status:end -->

            ## Session Notes
            - note 1
            - note 2
            - note 3
            - note 4

            ## Decisions
            - keep the UI server-rendered

            ## Known Issues
            - reminder delivery not built
            """,
        )
        run(["python3", ".forge/scripts/runtime.py", "sync"], self.project)

        result = run(["python3", ".forge/scripts/runtime.py", "session-brief"], self.project)
        self.assertIn("Active milestone: m1 — Slim prompt", result.stdout)
        self.assertIn("Available tasks:", result.stdout)
        self.assertIn("Read these files directly", result.stdout)
        self.assertNotIn('type = "milestone"', result.stdout)
        self.assertNotIn("## Session Notes", result.stdout)

    def test_run_mcp_config_defaults_to_empty(self) -> None:
        codex = run(["python3", ".forge/scripts/runtime.py", "run-mcp-config", "codex"], self.project)
        claude = run(["python3", ".forge/scripts/runtime.py", "run-mcp-config", "claude"], self.project)
        codex_payload = json.loads(codex.stdout)
        claude_payload = json.loads(claude.stdout)
        self.assertEqual(codex_payload["allowed"], [])
        self.assertEqual(codex_payload["config"], "mcp_servers={}")
        self.assertEqual(claude_payload["allowed"], [])
        self.assertEqual(json.loads(claude_payload["config"]), {"mcpServers": {}})

    def test_run_mcp_config_can_opt_in_playwright(self) -> None:
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

            [orchestration]
            run_mcps = ["playwright"]

            [agents.codex]
            model = "gpt-5.4"

            [agents.claude]
            model = "claude-opus-4-6"
            effort = "high"
            ```
            """,
        )
        codex = run(["python3", ".forge/scripts/runtime.py", "run-mcp-config", "codex"], self.project)
        claude = run(["python3", ".forge/scripts/runtime.py", "run-mcp-config", "claude"], self.project)
        self.assertIn("playwright", codex.stdout)
        self.assertIn("@playwright/mcp@latest", codex.stdout)
        claude_payload = json.loads(claude.stdout)
        self.assertEqual(claude_payload["allowed"], ["playwright"])
        self.assertEqual(
            json.loads(claude_payload["config"]),
            {"mcpServers": {"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}}},
        )

    def test_plans_require_validation_matrix_for_each_acceptance(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Missing matrix"
            goal = "Reject incomplete test mapping"
            status = "active"
            scope = ["scope"]
            out_of_scope = ["out"]
            acceptance = ["A", "B"]

            [[task]]
            id = "task-a"
            title = "Task A"
            description = "A task."
            depends_on = []
            verification = ["Run static validation"]
            artifacts = ["tests/test_a.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "A"
            verified_by = ["tests/test_a.py"]
            ```
            """,
        )

        result = run(["./forge", "status"], self.project, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Every acceptance criterion must appear in [[validation_matrix]]", result.stderr)

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

    def test_doctor_requires_at_least_one_agent_cli(self) -> None:
        env = self.isolated_path_env()
        result = run(["./forge", "doctor"], self.project, check=False, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Install at least one supported agent CLI", result.stdout)

    def test_doctor_requires_npx_for_selected_playwright_mcp(self) -> None:
        write_file(
            self.project / "docs/prompt.md",
            """
            # Prompt

            ```toml
            [project]
            name = "Smoke Project"
            one_liner = "Validate MCP doctor checks"

            [user_surface]
            kind = "web"
            entrypoint = "http://localhost:3000"

            [commands]
            runtime_prepare = []
            runtime_doctor = []
            validate_static = ["test -f docs/plans.md"]
            validate_surface = ["test -f docs/documentation.md"]

            [orchestration]
            run_mcps = ["playwright"]

            [agents.codex]
            model = "gpt-5.4"
            ```
            """,
        )
        env = self.isolated_path_env(include_codex=True)
        result = run(["./forge", "doctor"], self.project, check=False, env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("playwright MCP launcher (npx): missing", result.stdout)
        self.assertIn("run_mcps includes 'playwright' but 'npx' is not available.", result.stdout)

    def test_doctor_accepts_remote_docs_mcp_without_extra_binary(self) -> None:
        write_file(
            self.project / "docs/prompt.md",
            """
            # Prompt

            ```toml
            [project]
            name = "Smoke Project"
            one_liner = "Validate MCP doctor checks"

            [user_surface]
            kind = "api"
            entrypoint = "http://localhost:8000"

            [commands]
            runtime_prepare = []
            runtime_doctor = []
            validate_static = ["test -f docs/plans.md"]
            validate_surface = ["test -f docs/documentation.md"]

            [orchestration]
            run_mcps = ["openaiDeveloperDocs"]

            [agents.codex]
            model = "gpt-5.4"
            ```
            """,
        )
        env = self.isolated_path_env(include_codex=True)
        result = run(["./forge", "doctor"], self.project, env=env)
        self.assertIn("run MCP allowlist: openaiDeveloperDocs", result.stdout)
        self.assertIn("openaiDeveloperDocs MCP: remote endpoint configured", result.stdout)
        self.assertIn("All checks passed.", result.stdout)

    def test_run_prepares_worktree_and_archive_must_happen_there(self) -> None:
        run_result = run(["./forge", "run", "codex"], self.project)
        self.assertIn("No active milestone. Run forge-open first.", run_result.stdout)

        current_run = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        self.assertEqual(current_run["status"], "idle")
        worktree = Path(current_run["worktree_path"])
        self.assertTrue((worktree / ".forge/run-context.json").exists())
        self.assertTrue((worktree / ".forge/scripts/runtime.py").exists())

        root_status = run(["./forge", "status"], self.project)
        self.assertIn(str(worktree), root_status.stdout)
        self.assertIn("Milestone: none", root_status.stdout)
        self.assertIn("idle", root_status.stdout)

        archive_from_root = run(["./forge", "archive", "blocked-phase"], self.project, check=False)
        self.assertNotEqual(archive_from_root.returncode, 0)
        self.assertIn("Archive from", archive_from_root.stderr)

        archive_from_worktree = run(["./forge", "archive", "blocked-phase"], worktree, check=False)
        self.assertNotEqual(archive_from_worktree.returncode, 0)
        self.assertIn("land-current", archive_from_worktree.stderr)

    def test_run_bootstraps_runtime_into_worktree_when_harness_is_gitignored(self) -> None:
        gitignore = self.project / ".gitignore"
        gitignore.write_text(gitignore.read_text(encoding="utf-8") + "\n.forge/\n", encoding="utf-8")
        run(["git", "rm", "--cached", "-r", ".forge"], self.project)
        run(["git", "add", ".gitignore"], self.project)
        run(["git", "commit", "-m", "Ignore forge runtime"], self.project)

        self.assertTrue((self.project / ".forge/scripts/runtime.py").exists())

        run_result = run(["./forge", "run", "codex"], self.project)
        self.assertIn("No active milestone. Run forge-open first.", run_result.stdout)

        current_run = json.loads((self.project / ".forge/runs/current.json").read_text(encoding="utf-8"))
        worktree = Path(current_run["worktree_path"])
        self.assertTrue((worktree / ".forge/scripts/runtime.py").exists())

    def test_qa_reuses_recent_pass_when_workspace_is_unchanged(self) -> None:
        counter_dir = Path(tempfile.mkdtemp(prefix="forge-qa-counter."))
        counter_file = counter_dir / "counter.txt"
        validate_surface = self.project / ".forge/scripts/validate_surface.sh"
        validate_surface.write_text(
            textwrap.dedent(
                f"""\
                #!/bin/bash
                set -euo pipefail
                if [ "${{1:-}}" = "--doctor" ]; then
                  echo "validate_surface.sh: configured"
                  exit 0
                fi
                python3 - <<'PY'
                from pathlib import Path
                counter = Path({str(counter_file)!r})
                count = int(counter.read_text() or "0") if counter.exists() else 0
                counter.write_text(str(count + 1))
                PY
                """
            ),
            encoding="utf-8",
        )
        os.chmod(validate_surface, 0o755)

        first = run(["python3", ".forge/scripts/runtime.py", "qa"], self.project)
        self.assertIn("QA pass", first.stdout)
        second = run(["python3", ".forge/scripts/runtime.py", "qa", "--reuse-pass"], self.project)
        self.assertIn("QA pass [cached]", second.stdout)
        self.assertEqual(counter_file.read_text(encoding="utf-8"), "1")
        shutil.rmtree(counter_dir)

    def test_sync_writes_thin_execution_queue(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Thin queue"
            goal = "Keep queue.json focused on execution state"
            status = "active"
            scope = ["scope"]
            out_of_scope = ["out"]
            acceptance = ["acceptance"]

            [[task]]
            id = "task-a"
            title = "Task A"
            description = "Task description."
            depends_on = []
            verification = ["Run static validation"]
            artifacts = ["tests/test_a.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "acceptance"
            verified_by = ["tests/test_a.py"]
            ```
            """,
        )

        run(["python3", ".forge/scripts/runtime.py", "sync"], self.project)
        queue = json.loads((self.project / ".forge/state/current/queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queue["active_milestone_id"], "m1")
        self.assertEqual(sorted(queue["tasks"][0].keys()), ["id", "notes", "priority", "signature", "status"])

    def test_status_and_qa_show_acceptance_coverage(self) -> None:
        write_file(
            self.project / "docs/plans.md",
            """
            # Plans

            ```toml
            type = "milestone"

            [milestone]
            id = "m1"
            title = "Coverage"
            goal = "Expose acceptance coverage in status and qa"
            status = "active"
            scope = ["scope"]
            out_of_scope = ["out"]
            acceptance = ["Users can complete the main flow"]

            [[task]]
            id = "task-a"
            title = "Task A"
            description = "Task description."
            depends_on = []
            verification = ["Run static validation"]
            artifacts = ["tests/test_a.py"]

            [validation]
            commands = ["./.forge/scripts/validate_static.sh", "./.forge/scripts/validate_surface.sh"]
            smoke_scenarios = ["docs exist"]
            stop_and_fix = true

            [[validation_matrix]]
            acceptance = "Users can complete the main flow"
            verified_by = ["tests/test_a.py", "./.forge/scripts/validate_surface.sh"]
            ```
            """,
        )

        status = run(["./forge", "status"], self.project)
        self.assertIn("Acceptance coverage: 1/1 mapped", status.stdout)
        self.assertIn("Users can complete the main flow <= tests/test_a.py, ./.forge/scripts/validate_surface.sh", status.stdout)

        qa = run(["python3", ".forge/scripts/runtime.py", "qa"], self.project)
        self.assertIn("Acceptance coverage: 1/1 mapped", qa.stdout)
        self.assertIn("Users can complete the main flow <= tests/test_a.py, ./.forge/scripts/validate_surface.sh", qa.stdout)


if __name__ == "__main__":
    unittest.main()
