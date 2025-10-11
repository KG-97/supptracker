#!/usr/bin/env bash
# Safe helper script to make a GitHub repo public and add a collaborator named "gemini" with admin permission.
# This script only prints the commands by default. To execute, set RUN=1 in the environment.

set -euo pipefail

OWNER="KG-97"    # replace with your GitHub owner/org
REPO="supptracker" # replace with your repo name if different
GEMINI="gemini"    # replace with the GitHub username or app slug for Gemini

# The script supports two modes: dry-run (default) and run (set RUN=1 to actually execute).
if [ "${RUN:-0}" != "1" ]; then
  echo "DRY RUN: commands will be printed but not executed. To run, set RUN=1 and ensure GITHUB_TOKEN is set."
fi

if [ -z "${GITHUB_TOKEN:-}" ]; then
  echo "Warning: GITHUB_TOKEN is not set. API commands will fail if you try to run them."
fi

echo "Planned actions:"
echo "  - Make repository $OWNER/$REPO public"
echo "  - Add collaborator $GEMINI with admin permission"
echo

MAKE_PUBLIC_CMD=(gh api -X PATCH /repos/${OWNER}/${REPO} -f private=false)
ADD_COLLAB_CMD=(gh api -X PUT /repos/${OWNER}/${REPO}/collaborators/${GEMINI} -f permission=admin)

echo "Command to make public (gh):"
printf '  %s\n' "${MAKE_PUBLIC_CMD[@]}"
echo
echo "Command to add collaborator (gh):"
printf '  %s\n' "${ADD_COLLAB_CMD[@]}"
echo

if [ "${RUN:-0}" = "1" ]; then
  if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "Error: GITHUB_TOKEN must be set to run. Exiting." >&2
    exit 2
  fi

  echo "Running: make repo public"
  gh api -X PATCH /repos/${OWNER}/${REPO} -f private=false

  echo "Running: add collaborator ${GEMINI} with admin permission"
  gh api -X PUT /repos/${OWNER}/${REPO}/collaborators/${GEMINI} -f permission=admin

  echo "Done. Verify on GitHub." 
else
  echo "Dry run complete. To execute the above commands, run:" 
  echo "  RUN=1 GITHUB_TOKEN=ghp_xxx ./scripts/grant_gemini.sh"
fi
