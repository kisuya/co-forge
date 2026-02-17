#!/bin/bash
# Session start briefing — run this at the beginning of every coding session.
# Shows project state so the agent knows what to work on.

if [ ! -f "docs/projects/current/features.json" ]; then
  echo "No active project. Run /forge-project (Claude) or \$forge-project (Codex) first."
  return 0 2>/dev/null || exit 0
fi

echo "=== Session Start: $(date) ==="

echo ""
echo "=== Project Goal ==="
head -5 docs/projects/current/spec.md 2>/dev/null || echo "  (no spec.md)"

echo ""
echo "=== Recent Commits ==="
git log --oneline -5 2>/dev/null || echo "  (no commits yet)"

echo ""
echo "=== Progress ==="
cat docs/projects/current/progress.txt 2>/dev/null || echo "  (no progress yet)"

echo ""
echo "=== Pending Features ==="
python3 -c "
import json, sys
try:
    with open('docs/projects/current/features.json') as f:
        data = json.load(f)
    for feat in data['features']:
        if feat['status'] != 'done':
            deps = feat.get('depends_on', [])
            blocked = any(
                f2['status'] != 'done'
                for f2 in data['features']
                if f2['id'] in deps
            )
            status = 'BLOCKED' if blocked else 'AVAILABLE'
            print(f'  [{feat[\"priority\"]}] {feat[\"id\"]}: {feat[\"name\"]} - {status}')
    done = sum(1 for f in data['features'] if f['status'] == 'done')
    total = len(data['features'])
    print(f'  --- {done}/{total} complete ---')
except Exception as e:
    print(f'  Error reading features.json: {e}', file=sys.stderr)
"

echo ""
echo "=== Quick Test ==="
./.forge/scripts/test_fast.sh || true
