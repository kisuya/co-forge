#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "bin" / "co-forge.js"


def run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise AssertionError(
            f"command failed: {' '.join(command)}\n"
            f"exit={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


class ForgeCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="co-forge-cli."))
        self.project = self.tempdir / "project"
        self.project.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir)

    def test_install_copies_harness_and_manifest(self) -> None:
        result = run(["node", str(CLI), "install"], cwd=self.project)

        self.assertIn("Installed co-forge", result.stdout)
        self.assertIn("/forge-init", result.stdout)
        self.assertTrue((self.project / "forge").exists())
        self.assertTrue((self.project / ".forge/scripts/runtime.py").exists())
        self.assertTrue((self.project / ".claude/skills/forge-init/SKILL.md").exists())
        self.assertTrue((self.project / ".agents/skills/forge-init").is_symlink())
        manifest_path = self.project / ".forge/install.json"
        self.assertTrue(manifest_path.exists())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["packageName"], "co-forge")
        gitignore = (self.project / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("# >>> co-forge managed >>>", gitignore)
        self.assertIn(".forge/run-context.json", gitignore)

    def test_upgrade_rejects_modified_managed_files(self) -> None:
        run(["node", str(CLI), "install"], cwd=self.project)
        launcher = self.project / "forge"
        launcher.write_text("#!/bin/bash\necho modified\n", encoding="utf-8")

        result = run(["node", str(CLI), "upgrade"], cwd=self.project, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Managed files changed locally", result.stderr)
        self.assertIn("- forge", result.stderr)

    def test_uninstall_removes_managed_files_and_preserves_docs(self) -> None:
        run(["node", str(CLI), "install"], cwd=self.project)
        (self.project / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
        docs_dir = self.project / "docs"
        docs_dir.mkdir(exist_ok=True)
        (docs_dir / "prompt.md").write_text("# Prompt\n", encoding="utf-8")

        result = run(["node", str(CLI), "uninstall"], cwd=self.project)

        self.assertIn("Uninstalled co-forge", result.stdout)
        self.assertFalse((self.project / "forge").exists())
        self.assertFalse((self.project / ".forge/install.json").exists())
        self.assertFalse((self.project / ".forge/scripts/runtime.py").exists())
        self.assertTrue((self.project / "AGENTS.md").exists())
        self.assertTrue((docs_dir / "prompt.md").exists())
        gitignore = (self.project / ".gitignore").read_text(encoding="utf-8")
        self.assertNotIn("# >>> co-forge managed >>>", gitignore)

    def test_install_uses_explicit_target_path(self) -> None:
        target = self.tempdir / "another-project"

        result = run(["node", str(CLI), "install", str(target)], cwd=self.project)

        self.assertIn(str(target), result.stdout)
        self.assertTrue((target / "forge").exists())
        self.assertFalse((self.project / "forge").exists())

    def test_cli_rejects_multiple_target_paths(self) -> None:
        result = run(["node", str(CLI), "install", "a", "b"], cwd=self.project, check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Specify at most one target path.", result.stderr)


if __name__ == "__main__":
    unittest.main()
