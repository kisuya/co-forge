#!/bin/bash
# Archive the current project and prepare a clean slate.
# Usage: ./.forge/scripts/new_project.sh <project-name>

[ -z "$1" ] && echo "Usage: ./.forge/scripts/new_project.sh <project-name>" && exit 1

PROJECT_NAME="$1"

if [ -d ".forge/projects/$PROJECT_NAME" ]; then
  echo "Error: .forge/projects/$PROJECT_NAME already exists."
  exit 1
fi

mv .forge/projects/current ".forge/projects/$PROJECT_NAME"
mkdir -p .forge/projects/current
echo "# New Project" > .forge/projects/current/spec.md
echo '{"project":"","goal":"","agent":"","features":[]}' > .forge/projects/current/features.json
echo "No progress yet." > .forge/projects/current/progress.txt

echo "Archived as .forge/projects/$PROJECT_NAME"
echo "Run /forge-project to set up the next phase."
