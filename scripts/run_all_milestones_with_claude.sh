#!/usr/bin/env bash
set -euo pipefail

START="${1:-0}"
END="${2:-14}"

TEMPLATE="docs/prompts/run-one-milestone-template.md"

if [ ! -f "$TEMPLATE" ]; then
  echo "ERROR: missing $TEMPLATE"
  exit 1
fi

echo "Running milestones $START..$END with Claude Code"
echo "One claude -p run per milestone"
echo "The script stops if Claude fails, no commit is created, or the working tree is dirty"
echo

for MILESTONE in $(seq "$START" "$END"); do
  echo "======================================================================"
  echo "Milestone $MILESTONE"
  echo "======================================================================"

  BEFORE_COMMIT="$(git rev-parse HEAD)"

  claude -p "Use docs/prompts/run-one-milestone-template.md. Implement Milestone ${MILESTONE} only. Do not implement later milestones. Do not push. Commit locally when the milestone is complete. Stop after exactly this one milestone."

  AFTER_COMMIT="$(git rev-parse HEAD)"

  if [ "$BEFORE_COMMIT" = "$AFTER_COMMIT" ]; then
    echo "ERROR: Milestone $MILESTONE did not create a new commit."
    echo "Stopping so you can inspect."
    git status
    exit 1
  fi

  if [ -n "$(git status --porcelain)" ]; then
    echo "ERROR: working tree is not clean after Milestone $MILESTONE."
    echo "Stopping so you can inspect."
    git status
    exit 1
  fi

  echo
  echo "Milestone $MILESTONE completed."
  echo "Commit: $AFTER_COMMIT"
  echo

  if [ -f pyproject.toml ]; then
    echo "Running smoke validation after Milestone $MILESTONE..."
    python -m pytest -q || {
      echo "ERROR: pytest failed after Milestone $MILESTONE."
      echo "Stopping so you can inspect."
      exit 1
    }
  fi

  echo
done

echo "======================================================================"
echo "All requested milestones completed: $START..$END"
echo "======================================================================"
git log --oneline -20
