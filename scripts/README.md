Grant Gemini helper
===================

This folder contains a small helper script to make a repository public and add a collaborator named "gemini".

Usage (dry run by default):

1. Review and edit the script to set `OWNER`, `REPO`, and `GEMINI` values.
2. Install the GitHub CLI (`gh`) and authenticate: `gh auth login`.
3. Run a dry run to see commands:

   RUN=0 ./scripts/grant_gemini.sh

4. To execute (careful!):

   RUN=1 GITHUB_TOKEN=ghp_xxx ./scripts/grant_gemini.sh

Security notes:
- Do not paste long-lived personal access tokens into chats.
- Prefer using `gh auth login` and an environment variable with limited-lifetime tokens.
- If `gemini` is a GitHub App rather than a user, follow the GitHub App installation flow instead of using collaborator APIs.
