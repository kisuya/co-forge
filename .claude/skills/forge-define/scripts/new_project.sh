#!/bin/bash
# Archive the current project and prepare a clean slate.
# Usage: ./.forge/scripts/new_project.sh <project-name>

[ -z "$1" ] && echo "Usage: ./.forge/scripts/new_project.sh <project-name>" && exit 1

PROJECT_NAME="$1"

if [ -d "docs/projects/$PROJECT_NAME" ]; then
  echo "Error: docs/projects/$PROJECT_NAME already exists."
  exit 1
fi

mv docs/projects/current "docs/projects/$PROJECT_NAME"
mkdir -p docs/projects/current
echo "# New Project" > docs/projects/current/spec.md
echo '{"project":"","goal":"","agent":"","features":[]}' > docs/projects/current/features.json
echo "No progress yet." > docs/projects/current/progress.txt

echo "Archived as docs/projects/$PROJECT_NAME"
echo "Run /forge-project (Claude) or \$forge-project (Codex) to set up the next phase."
