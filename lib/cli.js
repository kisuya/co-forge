"use strict";

const path = require("path");

const { installForge, uninstallForge, upgradeForge, readPackageVersion } = require("./manager");

function printHelp() {
  const version = readPackageVersion();
  console.log(
    [
      `co-forge ${version}`,
      "",
      "Usage:",
      "  co-forge install [target] [--force]",
      "  co-forge upgrade [target] [--force]",
      "  co-forge uninstall [target] [--force]",
      "",
      "Arguments:",
      "  target    Project directory to manage. Defaults to the current directory.",
      "",
      "Options:",
      "  --force   Overwrite or remove managed files even when they were modified locally.",
      "  -h, --help  Show this help text.",
      "",
      "Examples:",
      "  co-forge install",
      "  co-forge install ../my-project",
      "  co-forge upgrade /absolute/path/to/project",
    ].join("\n"),
  );
}

function parseArgs(argv) {
  if (argv.length === 0 || argv.includes("-h") || argv.includes("--help")) {
    return { help: true };
  }

  const [command, ...rest] = argv;
  let force = false;
  let target = process.cwd();
  let targetSet = false;

  for (const token of rest) {
    if (token === "--force") {
      force = true;
      continue;
    }
    if (token.startsWith("-")) {
      throw new Error(`Unknown option: ${token}`);
    }
    if (targetSet) {
      throw new Error("Specify at most one target path.");
    }
    target = path.resolve(token);
    targetSet = true;
  }

  if (!["install", "upgrade", "uninstall"].includes(command)) {
    throw new Error(`Unknown command: ${command}`);
  }

  return { command, force, target };
}

function printResult(result) {
  console.log(result.summary);
  for (const line of result.details) {
    console.log(line);
  }
}

function runCli(argv) {
  try {
    const args = parseArgs(argv);
    if (args.help) {
      printHelp();
      process.exitCode = 0;
      return;
    }

    let result;
    if (args.command === "install") {
      result = installForge({ targetRoot: args.target, force: args.force });
    } else if (args.command === "upgrade") {
      result = upgradeForge({ targetRoot: args.target, force: args.force });
    } else {
      result = uninstallForge({ targetRoot: args.target, force: args.force });
    }

    printResult(result);
    process.exitCode = 0;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`co-forge: ${message}`);
    process.exitCode = 1;
  }
}

module.exports = {
  runCli,
};
