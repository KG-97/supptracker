# Contributing to SuppTracker

Thank you for helping improve SuppTracker! This guide explains how to set up your environment, follow the preferred workflow, and keep pull requests easy to review and merge.

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+
- npm and pip

### Backend Setup
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the backend test suite:
   ```bash
   pytest
   ```

### Frontend Setup
1. Install dependencies:
   ```bash
   npm install
   ```
2. Run checks locally:
   ```bash
   npm test
   npm run typecheck
   npm run build
   ```

## Branch & PR Workflow
- Keep branches short-lived (<1 week) and rebase frequently against `main`.
- Use descriptive branch names (e.g., `feature/improve-search-ui`, `fix/api-schema-mismatch`).
- Aim for atomic PRs under 500 lines of changes. Split large efforts into multiple PRs.
- Delete feature branches after merging to keep the history tidy.

### PR Preparation Checklist
Before opening or marking a PR ready for review:
1. Ensure all automated checks are passing locally (`pytest`, `npm test`, `npm run typecheck`).
2. Remove debug code, temporary logging, and commented-out blocks.
3. Confirm backend and frontend contracts are aligned (pay special attention to API response shapes and TypeScript types).
4. Fill out the pull request template completely, including testing notes and schema alignment.
5. Resolve or respond to all outstanding review comments before requesting re-review.

### Review Expectations
- Target review response within 48 hours. If a PR is on hold, clearly document the reason.
- Prefer small, self-contained PRs to keep review cycles quick.
- Use GitHub's "Review changes" to batch feedback and approvals.

## Automation & Labels
- **PR size labels** (`size/XS`–`size/XL`) are applied automatically based on diff size to highlight review effort.
- **Type labels** (`type: feature`, `type: fix`, `type: docs`, `type: chore`) are auto-applied based on touched files to speed up triage.
- **Stale handling**: Inactive PRs are marked stale after 30 days and auto-closed a week later. Update or comment to keep them active.
- **Dependabot** keeps npm, pip, and GitHub Actions dependencies current; please keep its PRs small and merge-ready.

## Code of Conduct
Be respectful, collaborative, and inclusive. Assume good intent, communicate clearly, and help reviewers by providing context for your changes.
