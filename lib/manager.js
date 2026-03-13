"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const PACKAGE_ROOT = path.resolve(__dirname, "..");
const MANIFEST_PATH = ".forge/install.json";
const GITIGNORE_START = "# >>> co-forge managed >>>";
const GITIGNORE_END = "# <<< co-forge managed <<<";
const GITIGNORE_BLOCK = [
  GITIGNORE_START,
  "# Forge v2 runtime state",
  ".forge/state/current/",
  ".forge/runs/",
  ".forge/worktrees/",
  ".forge/run-context.json",
  GITIGNORE_END,
];
const COPY_ROOTS = ["forge", ".forge/scripts", ".forge/templates", ".forge/references", ".claude/skills"];
const PRUNE_DIRS = [
  ".agents/skills",
  ".agents",
  ".claude/skills",
  ".claude",
  ".forge/scripts",
  ".forge/templates",
  ".forge/references",
  ".forge/state/current",
  ".forge/state",
  ".forge/runs",
  ".forge/worktrees",
  ".forge",
];
const RUNTIME_CLEANUP_PATHS = [
  ".forge/run-context.json",
  ".forge/scripts/prepare_runtime.sh",
  ".forge/scripts/validate_static.sh",
  ".forge/scripts/validate_surface.sh",
  ".forge/state/current",
  ".forge/runs",
  ".forge/worktrees",
];

function readPackageVersion() {
  const packageJsonPath = path.join(PACKAGE_ROOT, "package.json");
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
  return packageJson.version;
}

function timestamp() {
  return new Date().toISOString();
}

function normalizePath(relativePath) {
  return relativePath.split(path.sep).join("/");
}

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function walkFiles(relativeRoot) {
  const sourceRoot = path.join(PACKAGE_ROOT, relativeRoot);
  const rootStat = fs.lstatSync(sourceRoot);
  if (rootStat.isFile()) {
    return [normalizePath(relativeRoot)];
  }

  const files = [];
  const entries = fs.readdirSync(sourceRoot, { withFileTypes: true });
  for (const entry of entries) {
    const childRelative = path.posix.join(normalizePath(relativeRoot), entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(childRelative));
    } else if (entry.isFile()) {
      files.push(childRelative);
    }
  }
  return files;
}

function skillNames() {
  const skillsRoot = path.join(PACKAGE_ROOT, ".claude/skills");
  return fs
    .readdirSync(skillsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function desiredSpec() {
  const copiedFiles = COPY_ROOTS.flatMap((relativeRoot) => walkFiles(relativeRoot))
    .sort()
    .map((relativePath) => ({
      path: relativePath,
      type: "file",
      sourcePath: path.join(PACKAGE_ROOT, relativePath),
    }));
  const symlinks = skillNames().map((name) => ({
    path: `.agents/skills/${name}`,
    type: "symlink",
    target: `../../.claude/skills/${name}`,
  }));
  return { copiedFiles, symlinks };
}

function hashFile(absolutePath) {
  const digest = crypto.createHash("sha256");
  digest.update(fs.readFileSync(absolutePath));
  return digest.digest("hex");
}

function sameFileContent(sourcePath, targetPath) {
  if (!fs.existsSync(targetPath)) {
    return false;
  }
  const sourceStat = fs.lstatSync(sourcePath);
  const targetStat = fs.lstatSync(targetPath);
  if (!sourceStat.isFile() || !targetStat.isFile()) {
    return false;
  }
  return hashFile(sourcePath) === hashFile(targetPath);
}

function sameSymlinkTarget(targetPath, desiredTarget) {
  if (!fs.existsSync(targetPath)) {
    return false;
  }
  const targetStat = fs.lstatSync(targetPath);
  if (!targetStat.isSymbolicLink()) {
    return false;
  }
  return fs.readlinkSync(targetPath) === desiredTarget;
}

function readManifest(targetRoot) {
  const manifestPath = path.join(targetRoot, MANIFEST_PATH);
  if (!fs.existsSync(manifestPath)) {
    return null;
  }
  return JSON.parse(fs.readFileSync(manifestPath, "utf8"));
}

function writeManifest(targetRoot, manifest) {
  const manifestPath = path.join(targetRoot, MANIFEST_PATH);
  ensureDir(path.dirname(manifestPath));
  fs.writeFileSync(manifestPath, `${JSON.stringify(manifest, null, 2)}\n`, "utf8");
}

function statEntry(targetRoot, entry) {
  const absolutePath = path.join(targetRoot, entry.path);
  if (!fs.existsSync(absolutePath)) {
    return { exists: false };
  }
  const stat = fs.lstatSync(absolutePath);
  if (entry.type === "file") {
    return {
      exists: true,
      type: stat.isFile() ? "file" : stat.isSymbolicLink() ? "symlink" : "other",
      sha256: stat.isFile() ? hashFile(absolutePath) : null,
    };
  }
  return {
    exists: true,
    type: stat.isSymbolicLink() ? "symlink" : stat.isFile() ? "file" : "other",
    target: stat.isSymbolicLink() ? fs.readlinkSync(absolutePath) : null,
  };
}

function modifiedEntries(targetRoot, manifest) {
  const modified = [];
  for (const entry of manifest.copiedFiles || []) {
    const current = statEntry(targetRoot, { path: entry.path, type: "file" });
    if (!current.exists || current.type !== "file" || current.sha256 !== entry.sha256) {
      modified.push(entry.path);
    }
  }
  for (const entry of manifest.symlinks || []) {
    const current = statEntry(targetRoot, { path: entry.path, type: "symlink" });
    if (!current.exists || current.type !== "symlink" || current.target !== entry.target) {
      modified.push(entry.path);
    }
  }
  return modified.sort();
}

function validateConflicts(targetRoot, spec, allowedPaths) {
  const conflicts = [];
  const allowed = new Set(allowedPaths);

  for (const entry of spec.copiedFiles) {
    const absolutePath = path.join(targetRoot, entry.path);
    if (!fs.existsSync(absolutePath)) {
      continue;
    }
    if (allowed.has(entry.path)) {
      continue;
    }
    if (!sameFileContent(entry.sourcePath, absolutePath)) {
      conflicts.push(entry.path);
    }
  }

  for (const entry of spec.symlinks) {
    const absolutePath = path.join(targetRoot, entry.path);
    if (!fs.existsSync(absolutePath)) {
      continue;
    }
    if (allowed.has(entry.path)) {
      continue;
    }
    if (!sameSymlinkTarget(absolutePath, entry.target)) {
      conflicts.push(entry.path);
    }
  }

  return conflicts.sort();
}

function renderConflictError(prefix, entries) {
  return `${prefix}:\n${entries.map((entry) => `- ${entry}`).join("\n")}`;
}

function ensureGitignoreBlock(targetRoot) {
  const gitignorePath = path.join(targetRoot, ".gitignore");
  const existing = fs.existsSync(gitignorePath) ? fs.readFileSync(gitignorePath, "utf8") : "";
  const block = `${GITIGNORE_BLOCK.join("\n")}\n`;

  let updated;
  if (existing.includes(GITIGNORE_START) && existing.includes(GITIGNORE_END)) {
    const pattern = new RegExp(`${escapeRegExp(GITIGNORE_START)}[\\s\\S]*?${escapeRegExp(GITIGNORE_END)}\\n?`, "m");
    updated = existing.replace(pattern, block);
  } else if (existing.trim().length === 0) {
    updated = block;
  } else {
    updated = `${existing.replace(/\s*$/, "\n\n")}${block}`;
  }

  fs.writeFileSync(gitignorePath, updated, "utf8");
}

function removeGitignoreBlock(targetRoot) {
  const gitignorePath = path.join(targetRoot, ".gitignore");
  if (!fs.existsSync(gitignorePath)) {
    return;
  }

  const existing = fs.readFileSync(gitignorePath, "utf8");
  if (!existing.includes(GITIGNORE_START) || !existing.includes(GITIGNORE_END)) {
    return;
  }

  const pattern = new RegExp(`\\n?${escapeRegExp(GITIGNORE_START)}[\\s\\S]*?${escapeRegExp(GITIGNORE_END)}\\n?`, "m");
  const updated = existing.replace(pattern, "\n").replace(/\n{3,}/g, "\n\n").replace(/^\n/, "");
  fs.writeFileSync(gitignorePath, updated, "utf8");
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function copyFileEntry(targetRoot, entry) {
  const destination = path.join(targetRoot, entry.path);
  ensureDir(path.dirname(destination));
  fs.copyFileSync(entry.sourcePath, destination);
  const sourceMode = fs.statSync(entry.sourcePath).mode & 0o777;
  fs.chmodSync(destination, sourceMode);
  return {
    path: entry.path,
    sha256: hashFile(destination),
    mode: sourceMode,
  };
}

function createSymlinkEntry(targetRoot, entry) {
  const destination = path.join(targetRoot, entry.path);
  ensureDir(path.dirname(destination));
  if (fs.existsSync(destination)) {
    fs.rmSync(destination, { recursive: true, force: true });
  }
  fs.symlinkSync(entry.target, destination, "dir");
  return {
    path: entry.path,
    target: entry.target,
  };
}

function createRuntimeDirectories(targetRoot) {
  for (const relativePath of [".forge/state/current", ".forge/runs", ".forge/worktrees"]) {
    ensureDir(path.join(targetRoot, relativePath));
  }
}

function installForge({ targetRoot, force }) {
  const resolvedTarget = path.resolve(targetRoot);
  ensureDir(resolvedTarget);

  const manifest = readManifest(resolvedTarget);
  if (manifest && !force) {
    throw new Error("Forge is already installed here. Use `co-forge upgrade` or pass --force.");
  }

  const spec = desiredSpec();
  const conflicts = validateConflicts(resolvedTarget, spec, []);
  if (conflicts.length > 0 && !force) {
    throw new Error(renderConflictError("Refusing to overwrite existing files", conflicts));
  }

  const copiedFiles = spec.copiedFiles.map((entry) => copyFileEntry(resolvedTarget, entry));
  const symlinks = spec.symlinks.map((entry) => createSymlinkEntry(resolvedTarget, entry));
  createRuntimeDirectories(resolvedTarget);
  ensureGitignoreBlock(resolvedTarget);

  writeManifest(resolvedTarget, {
    packageName: "co-forge",
    packageVersion: readPackageVersion(),
    installedAt: timestamp(),
    copiedFiles,
    symlinks,
  });

  const details = [
    `Target: ${resolvedTarget}`,
    `Copied ${copiedFiles.length} files and created ${symlinks.length} symlinks.`,
    "Next: run `/forge-init` or `$forge-init` in this project.",
  ];
  return {
    summary: `Installed co-forge ${readPackageVersion()}.`,
    details,
  };
}

function upgradeForge({ targetRoot, force }) {
  const resolvedTarget = path.resolve(targetRoot);
  const manifest = readManifest(resolvedTarget);
  if (!manifest) {
    throw new Error("No managed install found. Run `co-forge install` first.");
  }

  const modified = modifiedEntries(resolvedTarget, manifest);
  if (modified.length > 0 && !force) {
    throw new Error(renderConflictError("Managed files changed locally; refusing to upgrade", modified));
  }

  const spec = desiredSpec();
  const allowedPaths = [
    ...(manifest.copiedFiles || []).map((entry) => entry.path),
    ...(manifest.symlinks || []).map((entry) => entry.path),
  ];
  const conflicts = validateConflicts(resolvedTarget, spec, allowedPaths);
  if (conflicts.length > 0 && !force) {
    throw new Error(renderConflictError("Upgrade would overwrite unmanaged files", conflicts));
  }

  const desiredFileSet = new Set(spec.copiedFiles.map((entry) => entry.path));
  const desiredLinkSet = new Set(spec.symlinks.map((entry) => entry.path));

  for (const entry of manifest.symlinks || []) {
    if (!desiredLinkSet.has(entry.path)) {
      fs.rmSync(path.join(resolvedTarget, entry.path), { recursive: true, force: true });
    }
  }
  for (const entry of manifest.copiedFiles || []) {
    if (!desiredFileSet.has(entry.path)) {
      fs.rmSync(path.join(resolvedTarget, entry.path), { recursive: true, force: true });
    }
  }

  const copiedFiles = spec.copiedFiles.map((entry) => copyFileEntry(resolvedTarget, entry));
  const symlinks = spec.symlinks.map((entry) => createSymlinkEntry(resolvedTarget, entry));
  ensureGitignoreBlock(resolvedTarget);
  createRuntimeDirectories(resolvedTarget);
  writeManifest(resolvedTarget, {
    packageName: "co-forge",
    packageVersion: readPackageVersion(),
    installedAt: timestamp(),
    copiedFiles,
    symlinks,
  });
  pruneEmptyDirectories(resolvedTarget);

  return {
    summary: `Upgraded co-forge to ${readPackageVersion()}.`,
    details: [`Target: ${resolvedTarget}`, `Synced ${copiedFiles.length} files and ${symlinks.length} symlinks.`],
  };
}

function uninstallForge({ targetRoot, force }) {
  const resolvedTarget = path.resolve(targetRoot);
  const manifest = readManifest(resolvedTarget);
  if (!manifest) {
    throw new Error("No managed install found. Nothing to uninstall.");
  }

  const modified = modifiedEntries(resolvedTarget, manifest);
  if (modified.length > 0 && !force) {
    throw new Error(renderConflictError("Managed files changed locally; refusing to uninstall", modified));
  }

  for (const entry of manifest.symlinks || []) {
    fs.rmSync(path.join(resolvedTarget, entry.path), { recursive: true, force: true });
  }
  for (const entry of manifest.copiedFiles || []) {
    fs.rmSync(path.join(resolvedTarget, entry.path), { recursive: true, force: true });
  }
  for (const relativePath of RUNTIME_CLEANUP_PATHS) {
    fs.rmSync(path.join(resolvedTarget, relativePath), { recursive: true, force: true });
  }

  fs.rmSync(path.join(resolvedTarget, MANIFEST_PATH), { force: true });
  removeGitignoreBlock(resolvedTarget);
  pruneEmptyDirectories(resolvedTarget);

  return {
    summary: "Uninstalled co-forge.",
    details: [`Target: ${resolvedTarget}`, "User docs such as AGENTS.md and docs/* were left untouched."],
  };
}

function pruneEmptyDirectories(targetRoot) {
  for (const relativePath of PRUNE_DIRS) {
    const absolutePath = path.join(targetRoot, relativePath);
    if (!fs.existsSync(absolutePath) || !fs.lstatSync(absolutePath).isDirectory()) {
      continue;
    }
    if (fs.readdirSync(absolutePath).length === 0) {
      fs.rmdirSync(absolutePath);
    }
  }
}

module.exports = {
  installForge,
  readPackageVersion,
  uninstallForge,
  upgradeForge,
};
