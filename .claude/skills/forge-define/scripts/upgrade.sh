#!/bin/bash
# Upgrade forge harness from the template repository.
# Run from your project root after initial scaffold.
#
# Usage: ./.forge/scripts/upgrade.sh
#
# What it does:
#   1. Adds co-forge template as a git remote (if not already)
#   2. Fetches latest changes
#   3. Updates .claude/skills/ and .agents/skills/ (skill definitions)
#   4. Ensures .forge/scripts/ are symlinks to skill source (migrates copies)
#   5. Ensures .forge/templates/ are symlinks to skill source (migrates copies)
#
# What it does NOT touch:
#   - AGENTS.md, docs/, src/, tests/ (project-specific)
#   - docs/projects/ (project state)
#   - .forge/scripts/test_fast.sh (generated per tech stack, real file)

set -e

# Wrap in { ... exit; } so bash reads the entire script into memory before
# executing.  Step 4 (git checkout) overwrites this file (or its symlink target),
# which would corrupt a streaming read.
{

TEMPLATE_REMOTE="template"
TEMPLATE_URL="https://github.com/kisuya/co-forge.git"

echo "=== Forge Upgrade ==="

# --- Step 1: Ensure template remote exists ---
if ! git remote get-url "$TEMPLATE_REMOTE" &>/dev/null; then
  echo "Adding template remote..."
  git remote add "$TEMPLATE_REMOTE" "$TEMPLATE_URL"
  echo "  ✓ Remote '$TEMPLATE_REMOTE' → $TEMPLATE_URL"
else
  CURRENT_URL=$(git remote get-url "$TEMPLATE_REMOTE")
  echo "  Template remote exists: $CURRENT_URL"
fi

# --- Step 2: Fetch latest ---
echo "Fetching template updates..."
git fetch "$TEMPLATE_REMOTE" --quiet
echo "  ✓ Fetched"

# --- Step 3: Check for changes in harness files ---
DIFF_FILES=$(git diff --name-only HEAD "$TEMPLATE_REMOTE/main" -- \
  .claude/skills/ \
  .agents/skills/ \
  2>/dev/null || true)

if [ -z "$DIFF_FILES" ]; then
  echo ""
  echo "=== Already up to date ==="
  exit 0
fi

echo ""
echo "Changed files:"
echo "$DIFF_FILES" | sed 's/^/  /'
echo ""

# --- Step 4: Update skills (source of truth) ---
echo "Updating .claude/skills/..."
git checkout "$TEMPLATE_REMOTE/main" -- .claude/skills/
echo "  ✓ Skills updated"

echo "Updating .agents/skills/..."
git checkout "$TEMPLATE_REMOTE/main" -- .agents/skills/
echo "  ✓ Symlinks updated"

# --- Step 5: Ensure runtime scripts are symlinks ---
echo "Updating .forge/scripts/..."

for script in init.sh checkpoint.sh new_project.sh orchestrate.sh upgrade.sh; do
  target=".forge/scripts/$script"
  link="../../.claude/skills/forge-define/scripts/$script"
  if [ -L "$target" ]; then
    continue  # already a symlink
  fi
  rm -f "$target"
  ln -sf "$link" "$target"
done
echo "  ✓ Runtime scripts symlinked (test_fast.sh preserved)"

# --- Step 6: Ensure templates are symlinks ---
echo "Updating .forge/templates/..."
TEMPLATE_SRC=".claude/skills/forge-define/templates"
if [ -d "$TEMPLATE_SRC" ]; then
  for tmpl in "$TEMPLATE_SRC"/*.template; do
    target=".forge/templates/$(basename "$tmpl")"
    link="../../.claude/skills/forge-define/templates/$(basename "$tmpl")"
    if [ -L "$target" ]; then
      continue
    fi
    rm -f "$target"
    ln -sf "$link" "$target"
  done
  echo "  ✓ Templates symlinked"
fi

# --- Step 7: Summary ---
echo ""
echo "=== Upgrade Complete ==="
echo ""
echo "Updated from template: $(git log "$TEMPLATE_REMOTE/main" --oneline -1)"
echo ""
echo "Review changes:"
echo "  git diff --cached    (staged changes)"
echo "  git diff             (unstaged changes)"
echo ""
echo "If everything looks good:"
echo "  git add -A && git commit -m 'Upgrade forge harness'"

exit
}
