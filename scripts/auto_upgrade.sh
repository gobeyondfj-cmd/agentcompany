#!/usr/bin/env bash
# Auto-upgrade agent-company-ai via Claude Code (non-interactive)
# Scheduled by launchd — Wed + Sat 3AM UTC (11AM CST)
set -euo pipefail

PROJECT_DIR="/Users/coins/Desktop/AI/AgentCompany"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
LOG_FILE="$LOG_DIR/upgrade_${TIMESTAMP}.log"

# Source environment variables if .env exists
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

echo "=== Auto-upgrade started at $(date -u '+%Y-%m-%d %H:%M:%S UTC') ===" | tee "$LOG_FILE"

cd "$PROJECT_DIR"

/opt/homebrew/bin/claude -p --max-turns 50 "$(cat <<'PROMPT'
You are running a scheduled bi-weekly auto-upgrade for the agent-company-ai package (published on PyPI and GitHub).

Your job:

1. RESEARCH — Search the web for current AI agent trends, new business automation tools, and popular Python agent framework features in 2026. Identify gaps in the current toolset.

2. AUDIT — Read src/agent_company_ai/tools/__init__.py and the tools/ directory to see all existing tools. Read pyproject.toml for the current version.

3. PICK ONE IMPROVEMENT — Choose a single, high-impact, low-risk improvement. Prefer:
   - A new tool in src/agent_company_ai/tools/ (using the existing @tool decorator pattern from registry.py)
   - Or a new role YAML in src/agent_company_ai/roles/
   - Keep it small: one file, under 300 lines

4. IMPLEMENT — Write the code following existing patterns exactly. Look at web_search.py or prospect_tool.py as references for the @tool pattern.

5. SAFETY RULES — You MUST follow these:
   - ONLY create/modify files in: src/agent_company_ai/tools/, src/agent_company_ai/roles/, README.md, pyproject.toml
   - NEVER touch: src/agent_company_ai/core/, src/agent_company_ai/cli/, src/agent_company_ai/storage/, .github/
   - No new pip dependencies — only use what's already in pyproject.toml
   - Every new .py tool file must pass: python -c "import ast; ast.parse(open('FILE').read())"

6. VALIDATE — Run these checks:
   - python -c "from agent_company_ai.tools.registry import ToolRegistry; import agent_company_ai.tools; print('Tools:', ToolRegistry.get().list_names())"
   - Verify your new tool appears in the list

7. VERSION BUMP — Bump the patch version in pyproject.toml (e.g. 0.4.0 → 0.4.1)

8. UPDATE README — Add your new tool/feature to the appropriate section in README.md

9. PUBLISH:
   - git add the changed files (be specific, don't use git add -A)
   - git commit with a descriptive message
   - git push origin main
   - rm -rf dist/ && python -m build
   - python -m twine upload dist/*

10. REPORT — Print a summary: what you added, the new version number, and confirmation of PyPI upload.

If ANY step fails, stop and report the error. Do NOT force-push or revert other people's work. Keep changes minimal and focused.
PROMPT
)" 2>&1 | tee -a "$LOG_FILE"

echo "=== Auto-upgrade finished at $(date -u '+%Y-%m-%d %H:%M:%S UTC') ===" | tee -a "$LOG_FILE"
