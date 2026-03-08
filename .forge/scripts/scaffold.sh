#!/bin/bash
# Forge v2 scaffold — installs runtime infrastructure for long-horizon runs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FORGE_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Forge V2 Scaffold ==="

if [ ! -f "AGENTS.md" ]; then
  echo "Error: AGENTS.md not found. Run /forge-init or \$forge-init first." >&2
  exit 1
fi

if [ ! -d "docs" ]; then
  echo "Error: docs/ not found. Run /forge-init or \$forge-init first." >&2
  exit 1
fi

if [ ! -f "docs/prompt.md" ]; then
  echo "Error: docs/prompt.md not found. Forge v2 requires prompt.md before scaffold." >&2
  exit 1
fi

if [ ! -f "docs/implement.md" ]; then
  echo "Error: docs/implement.md not found. Forge v2 requires implement.md before scaffold." >&2
  exit 1
fi

ORIGIN_URL="$(git remote get-url origin 2>/dev/null || echo "")"
if echo "$ORIGIN_URL" | grep -qE 'kisuya/co-forge(\.git)?$'; then
  echo ""
  echo "Warning: origin points to the template repository."
  if [ -t 0 ]; then
    read -rp "Remove origin remote now? (Y/n): " ANSWER
    ANSWER="${ANSWER:-Y}"
  else
    ANSWER="Y"
    echo "  Non-interactive environment detected — removing origin automatically."
  fi
  if [[ "$ANSWER" =~ ^[Yy]$ ]]; then
    git remote remove origin
    echo "  Removed origin. Add your own repo remote before pushing."
  fi
  echo ""
fi

echo "Creating runtime directories..."
mkdir -p .claude/skills .agents/skills .forge/state/current .forge/runs .forge/worktrees .forge/sessions docs/projects tests

if [ ! -d ".git" ]; then
  echo "Initializing git..."
  git init -q
fi

echo "Verifying tracked runtime entrypoints..."
for script in forge runtime.py init.sh checkpoint.sh new_project.sh orchestrate.sh prepare_run.sh scaffold.sh upgrade.sh; do
  if [ ! -e ".forge/scripts/$script" ]; then
    echo "Error: .forge/scripts/$script not found. This project must keep tracked Forge sources." >&2
    exit 1
  fi
done

if [ ! -e "forge" ]; then
  ln -sf ".forge/scripts/forge" "forge"
fi

echo "Verifying tracked templates..."
for tmpl in "$FORGE_DIR/templates"/*.template; do
  if [ ! -e "$tmpl" ]; then
    echo "Error: required template missing: $tmpl" >&2
    exit 1
  fi
done

echo "Verifying chat-native skill entrypoints..."
for skill in forge-init forge-open forge-close; do
  if [ ! -f ".claude/skills/$skill/SKILL.md" ]; then
    echo "Error: .claude/skills/$skill/SKILL.md not found. This project must keep the tracked skill directories." >&2
    exit 1
  fi
  ln -sf "../../.claude/skills/$skill" ".agents/skills/$skill"
done

echo "Creating project docs placeholders..."
if [ ! -f "docs/plans.md" ]; then
  cat > docs/plans.md <<'EOF'
# Plans

No active milestone. Run `/forge-open` or `$forge-open` to open the next phase.
EOF
fi

if [ ! -f "docs/documentation.md" ]; then
  cat > docs/documentation.md <<'EOF'
# Documentation

<!-- forge:status:start -->
_No machine status yet._
<!-- forge:status:end -->

## Session Notes
- Add short session summaries here.

## Decisions
- Record durable decisions and why they were made.

## How To Run
- Keep quick start and demo commands here.

## Known Issues
- Capture follow-ups that should survive agent sessions.
EOF
fi

if [ ! -f "docs/user_scenarios.md" ]; then
  cat > docs/user_scenarios.md <<'EOF'
# User Scenarios

Document the primary flow, edge cases, and resolved unknowns here.
EOF
fi

echo "Generating runtime hooks from docs/prompt.md..."
python3 "$SCRIPT_DIR/runtime.py" render-hook validate_static > .forge/scripts/validate_static.sh
python3 "$SCRIPT_DIR/runtime.py" render-hook validate_surface > .forge/scripts/validate_surface.sh
python3 "$SCRIPT_DIR/runtime.py" render-hook prepare_runtime > .forge/scripts/prepare_runtime.sh

chmod +x forge .forge/scripts/forge .forge/scripts/*.sh .forge/scripts/runtime.py

echo "Writing .gitignore entries..."
python3 - <<'PY'
from pathlib import Path

path = Path(".gitignore")
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
filtered = [line for line in lines if line.strip() != "docs/projects/current/"]
required = [
    "# Forge v2 runtime state",
    ".forge/state/current/",
    ".forge/runs/",
    ".forge/sessions/",
    ".forge/worktrees/",
    ".forge/run-context.json",
]
for item in required:
    if item not in filtered:
        filtered.append(item)
if "docs/projects/current/" in filtered:
    filtered.remove("docs/projects/current/")
path.write_text("\n".join(filtered).rstrip() + "\n", encoding="utf-8")
PY

echo "Running initial sync..."
python3 "$SCRIPT_DIR/runtime.py" sync >/dev/null

echo ""
echo "=== Verification ==="
PASS=true

[ -x "forge" ] && echo "  ✓ ./forge" || { echo "  ✗ ./forge"; PASS=false; }
[ -x ".forge/scripts/forge" ] && echo "  ✓ .forge/scripts/forge" || { echo "  ✗ .forge/scripts/forge"; PASS=false; }
[ -x ".forge/scripts/runtime.py" ] && echo "  ✓ .forge/scripts/runtime.py" || { echo "  ✗ .forge/scripts/runtime.py"; PASS=false; }
[ -f ".claude/skills/forge-init/SKILL.md" ] && echo "  ✓ .claude/skills/forge-init" || { echo "  ✗ .claude/skills/forge-init"; PASS=false; }
[ -f ".claude/skills/forge-open/SKILL.md" ] && echo "  ✓ .claude/skills/forge-open" || { echo "  ✗ .claude/skills/forge-open"; PASS=false; }
[ -f ".claude/skills/forge-close/SKILL.md" ] && echo "  ✓ .claude/skills/forge-close" || { echo "  ✗ .claude/skills/forge-close"; PASS=false; }
[ -L ".agents/skills/forge-init" ] && echo "  ✓ .agents/skills/forge-init" || { echo "  ✗ .agents/skills/forge-init"; PASS=false; }
[ -L ".agents/skills/forge-open" ] && echo "  ✓ .agents/skills/forge-open" || { echo "  ✗ .agents/skills/forge-open"; PASS=false; }
[ -L ".agents/skills/forge-close" ] && echo "  ✓ .agents/skills/forge-close" || { echo "  ✗ .agents/skills/forge-close"; PASS=false; }
[ -f "docs/prompt.md" ] && echo "  ✓ docs/prompt.md" || { echo "  ✗ docs/prompt.md"; PASS=false; }
[ -f "docs/plans.md" ] && echo "  ✓ docs/plans.md" || { echo "  ✗ docs/plans.md"; PASS=false; }
[ -f "docs/implement.md" ] && echo "  ✓ docs/implement.md" || { echo "  ✗ docs/implement.md"; PASS=false; }
[ -f "docs/documentation.md" ] && echo "  ✓ docs/documentation.md" || { echo "  ✗ docs/documentation.md"; PASS=false; }
[ -f "docs/user_scenarios.md" ] && echo "  ✓ docs/user_scenarios.md" || { echo "  ✗ docs/user_scenarios.md"; PASS=false; }
grep -q ".forge/state/current/" .gitignore && echo "  ✓ runtime state ignored" || { echo "  ✗ runtime state ignore missing"; PASS=false; }

if ./forge status >/dev/null 2>&1; then
  echo "  ✓ ./forge status"
else
  echo "  ✗ ./forge status"
  PASS=false
fi

if ./forge doctor >/dev/null 2>&1; then
  echo "  ✓ ./forge doctor"
else
  echo "  ✗ ./forge doctor"
  PASS=false
fi

if ! git rev-parse --verify HEAD >/dev/null 2>&1; then
  git add -A
  git commit -m "Initial forge v2 scaffold" >/dev/null
  echo "  ✓ initial git commit"
fi

echo ""
if $PASS; then
  echo "=== Forge V2 Scaffold Complete ==="
  echo "Next: run /forge-open or \$forge-open, then start with ./forge run."
else
  echo "=== Forge V2 Scaffold failed verification ==="
  echo "Check docs/prompt.md command blocks and validation hooks."
  exit 1
fi
