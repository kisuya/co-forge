#!/bin/bash
# One-time harness scaffold — installs runtime infrastructure into .forge/
# Run AFTER forge-define completes (AGENTS.md and docs/ must exist).
#
# Usage: bash /path/to/forge-define/scripts/scaffold.sh
#
# The script finds its sibling files using its own directory location.
# All harness files go into .forge/ (gitignored). Product code stays in root.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Forge Scaffold ==="

# --- Step 0: Guard against pushing to template repo ---
TEMPLATE_REPO="kisuya/co-forge"
ORIGIN_URL=$(git remote get-url origin 2>/dev/null || echo "")

if echo "$ORIGIN_URL" | grep -qi "$TEMPLATE_REPO"; then
  echo ""
  echo "⚠  Warning: origin이 템플릿 저장소($TEMPLATE_REPO)를 가리키고 있습니다."
  echo "   이대로 push하면 원본 템플릿 저장소를 덮어씁니다."
  echo ""
  read -rp "origin remote를 제거할까요? (Y/n): " ANSWER
  ANSWER=${ANSWER:-Y}
  if [[ "$ANSWER" =~ ^[Yy]$ ]]; then
    git remote remove origin
    echo "  ✓ origin remote를 제거했습니다."
    echo "  → 새 저장소 연결: git remote add origin https://github.com/YOU/YOUR-PROJECT.git"
  else
    echo "  ⚠  origin이 유지됩니다. push 전에 반드시 변경하세요:"
    echo "     git remote set-url origin https://github.com/YOU/YOUR-PROJECT.git"
  fi
  echo ""
fi

# --- Prerequisites ---
if [ ! -f "AGENTS.md" ]; then
  echo "Error: AGENTS.md not found. Run /forge-define first."
  exit 1
fi

if [ ! -d "docs" ]; then
  echo "Error: docs/ not found. Run /forge-define first."
  exit 1
fi

# --- Step 1: Create .forge/ structure ---
echo "Creating .forge/ directory structure..."
mkdir -p .forge/scripts .forge/templates .forge/projects/current tests

# --- Step 2: Install runtime scripts ---
echo "Installing runtime scripts..."

# Backup existing .forge/scripts if re-running
if [ -d ".forge/scripts" ] && [ "$(ls -A .forge/scripts/ 2>/dev/null)" ]; then
  BACKUP=".forge/scripts.backup.$(date +%Y%m%d%H%M%S)"
  echo "  Existing .forge/scripts/ found. Backing up to $BACKUP/"
  cp -r .forge/scripts "$BACKUP"
fi

for script in init.sh checkpoint.sh new_project.sh orchestrate.sh; do
  if [ -f "$SCRIPT_DIR/$script" ]; then
    cp "$SCRIPT_DIR/$script" ".forge/scripts/$script"
  else
    echo "  Warning: $script not found in $SCRIPT_DIR"
  fi
done

# --- Step 3: Generate test_fast.sh (tech-stack detection) ---
echo "Generating test_fast.sh..."
if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "setup.py" ]; then
  cat > .forge/scripts/test_fast.sh << 'EOF'
#!/bin/bash
pytest tests/ -x --timeout=10 -q "$@"
EOF
elif [ -f "package.json" ]; then
  cat > .forge/scripts/test_fast.sh << 'EOF'
#!/bin/bash
npx jest --bail --silent "$@"
EOF
elif [ -f "go.mod" ]; then
  cat > .forge/scripts/test_fast.sh << 'EOF'
#!/bin/bash
go test ./... -short -count=1 "$@"
EOF
elif [ -f "Cargo.toml" ]; then
  cat > .forge/scripts/test_fast.sh << 'EOF'
#!/bin/bash
cargo test -- --test-threads=1 "$@"
EOF
else
  echo "  Warning: Could not detect tech stack. Creating placeholder test_fast.sh."
  cat > .forge/scripts/test_fast.sh << 'EOF'
#!/bin/bash
echo "Edit .forge/scripts/test_fast.sh for your test framework."
exit 0
EOF
fi

chmod +x .forge/scripts/*.sh

# --- Step 4: Install templates ---
echo "Installing templates..."
TEMPLATE_SRC="$SKILL_DIR/templates"
if [ -d "$TEMPLATE_SRC" ]; then
  cp "$TEMPLATE_SRC"/*.template .forge/templates/ 2>/dev/null
  echo "  $(ls .forge/templates/*.template 2>/dev/null | wc -l | tr -d ' ') templates installed"
else
  echo "  Warning: Template source not found at $TEMPLATE_SRC"
fi

# --- Step 5: Create project placeholders ---
echo "Creating project placeholders..."
echo "# New Project" > .forge/projects/current/spec.md
echo '{"project":"","goal":"","agent":"","features":[]}' > .forge/projects/current/features.json
echo "No progress yet." > .forge/projects/current/progress.txt

# --- Step 6: Create docs/backlog.md ---
echo "Creating backlog..."
if [ ! -f "docs/backlog.md" ]; then
  cat > docs/backlog.md << 'BLEOF'
# Backlog

Items discovered during development or brainstormed outside coding sessions.
Reviewed at the start of each /forge-project.

<!-- Format: - [source] description -->
BLEOF
  echo "  Created docs/backlog.md"
else
  echo "  docs/backlog.md already exists, skipping"
fi

# --- Step 7: Create smoke test ---
echo "Creating smoke test..."
if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "setup.py" ]; then
  cat > tests/test_smoke.py << 'PYEOF'
import os
import json

def test_agents_md_exists():
    assert os.path.exists("AGENTS.md")

def test_features_json_valid():
    with open(".forge/projects/current/features.json") as f:
        data = json.load(f)
    assert "features" in data
PYEOF
elif [ -f "package.json" ]; then
  cat > tests/smoke.test.js << 'JSEOF'
const fs = require('fs');
test('AGENTS.md exists', () => {
  expect(fs.existsSync('AGENTS.md')).toBe(true);
});
test('features.json is valid', () => {
  const data = JSON.parse(fs.readFileSync('.forge/projects/current/features.json'));
  expect(data).toHaveProperty('features');
});
JSEOF
else
  cat > tests/test_smoke.sh << 'SHEOF'
#!/bin/bash
[ -f "AGENTS.md" ] || { echo "FAIL: AGENTS.md missing"; exit 1; }
python3 -c "import json; json.load(open('.forge/projects/current/features.json'))" \
  || { echo "FAIL: features.json invalid"; exit 1; }
echo "Smoke test passed."
SHEOF
  chmod +x tests/test_smoke.sh
fi

# --- Step 8: Git init ---
if [ ! -d ".git" ]; then
  echo "Initializing git..."
  git init -q
  cat > .gitignore << 'GITEOF'
# Forge: active project state (ephemeral, per-developer)
.forge/projects/current/

# Common ignores
node_modules/
__pycache__/
*.pyc
.env
.DS_Store
target/
dist/
build/
GITEOF
  git add -A
  git commit -q -m "Initial harness setup (forge scaffold)"
  echo "  Git initialized with initial commit."
else
  # Ensure .forge/projects/current/ is gitignored even on existing repos
  if ! grep -q "\.forge/projects/current/" .gitignore 2>/dev/null; then
    echo "" >> .gitignore
    echo "# Forge: active project state (ephemeral, per-developer)" >> .gitignore
    echo ".forge/projects/current/" >> .gitignore
    echo "  Added .forge/projects/current/ to .gitignore"
  fi
  echo "  Git already initialized."
fi

# --- Step 9: Verify ---
echo ""
echo "=== Verification ==="
PASS=true

[ -f "AGENTS.md" ]                          && echo "  ✓ AGENTS.md"                    || { echo "  ✗ AGENTS.md"; PASS=false; }
[ -f ".forge/scripts/init.sh" ]              && echo "  ✓ .forge/scripts/init.sh"        || { echo "  ✗ .forge/scripts/init.sh"; PASS=false; }
[ -f ".forge/scripts/checkpoint.sh" ]        && echo "  ✓ .forge/scripts/checkpoint.sh"  || { echo "  ✗ .forge/scripts/checkpoint.sh"; PASS=false; }
[ -f ".forge/scripts/orchestrate.sh" ]       && echo "  ✓ .forge/scripts/orchestrate.sh" || { echo "  ✗ .forge/scripts/orchestrate.sh"; PASS=false; }
[ -f ".forge/scripts/test_fast.sh" ]         && echo "  ✓ .forge/scripts/test_fast.sh"   || { echo "  ✗ .forge/scripts/test_fast.sh"; PASS=false; }
[ -d ".forge/templates" ]                    && echo "  ✓ .forge/templates/"              || { echo "  ✗ .forge/templates/"; PASS=false; }
[ -f ".forge/projects/current/features.json" ] && echo "  ✓ .forge/projects/current/"    || { echo "  ✗ .forge/projects/current/"; PASS=false; }
[ -d "tests" ]                               && echo "  ✓ tests/"                        || { echo "  ✗ tests/"; PASS=false; }
[ -f "docs/backlog.md" ]                     && echo "  ✓ docs/backlog.md"               || { echo "  ✗ docs/backlog.md"; PASS=false; }
grep -q "\.forge/projects/current/" .gitignore 2>/dev/null && echo "  ✓ .forge/projects/current/ in .gitignore" || { echo "  ✗ .forge/projects/current/ not in .gitignore"; PASS=false; }

echo ""
if $PASS; then
  echo "=== Scaffold Complete ==="
  echo "Run /forge-project to create your first project."
else
  echo "=== Scaffold had issues. Review above. ==="
  exit 1
fi
