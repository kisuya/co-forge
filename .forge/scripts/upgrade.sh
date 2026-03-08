#!/bin/bash
set -euo pipefail

{
TEMPLATE_REMOTE="template"
TEMPLATE_URL="https://github.com/kisuya/co-forge.git"

echo "=== Forge V2 Upgrade ==="

if ! git remote get-url "$TEMPLATE_REMOTE" >/dev/null 2>&1; then
  git remote add "$TEMPLATE_REMOTE" "$TEMPLATE_URL"
  echo "Added remote '$TEMPLATE_REMOTE' -> $TEMPLATE_URL"
else
  echo "Using remote '$TEMPLATE_REMOTE' -> $(git remote get-url "$TEMPLATE_REMOTE")"
fi

echo "Fetching latest template..."
git fetch "$TEMPLATE_REMOTE" --quiet

DIFF_FILES="$(git diff --name-only HEAD "$TEMPLATE_REMOTE/main" -- .forge/ .claude/skills/ .agents/skills/ forge README.md .gitignore 2>/dev/null || true)"
if [ -z "$DIFF_FILES" ]; then
  echo "Already up to date."
  exit 0
fi

echo "Updating tracked harness sources..."
git checkout "$TEMPLATE_REMOTE/main" -- .forge/ .claude/skills/ .agents/skills/ forge README.md .gitignore

chmod +x forge .forge/scripts/*.sh .forge/scripts/runtime.py 2>/dev/null || true

echo ""
echo "Upgrade complete. Review with:"
echo "  git diff"
echo "  ./forge doctor"
echo "  ./forge status"
}
