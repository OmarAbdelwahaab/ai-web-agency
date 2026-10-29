#!/usr/bin/env bash
# Optional installer for the agent skills/tools evaluated in docs/SKILLS_AND_TOOLS.md.
# Nothing here is required to run the project. Every command is printed before it runs.
#
#   bash scripts/setup_skills.sh --core            # playwright-cli + Impeccable (recommended)
#   bash scripts/setup_skills.sh --taste           # taste-skill (one-time template polish; heavy)
#   bash scripts/setup_skills.sh --agents          # a small subset of agency-agents personas
#   bash scripts/setup_skills.sh --core --yes      # skip confirmation prompts
#   bash scripts/setup_skills.sh --agents --dry-run
set -euo pipefail

CORE=0; TASTE=0; AGENTS=0; YES=0; DRY=0
for a in "$@"; do
  case "$a" in
    --core) CORE=1 ;; --taste) TASTE=1 ;; --agents) AGENTS=1 ;;
    --yes) YES=1 ;; --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown option: $a"; exit 1 ;;
  esac
done
if [ $((CORE + TASTE + AGENTS)) -eq 0 ]; then sed -n '2,11p' "$0"; exit 0; fi

command -v node >/dev/null || { echo "Node.js is required (Node 22+ recommended)."; exit 1; }
echo "Node: $(node --version)"
NODE_MAJOR=$(node -p "process.versions.node.split('.')[0]")
if [ "$NODE_MAJOR" -lt 22 ]; then echo "Warning: taste-skill needs Node 22+; playwright-cli needs 18+."; fi

run() {
  echo; echo "+ $*"
  if [ "$DRY" -eq 1 ]; then return 0; fi
  if [ "$YES" -ne 1 ]; then read -r -p "Run this? [y/N] " ans; [ "$ans" = "y" ] || { echo "skipped"; return 0; }; fi
  "$@"
}

if [ "$CORE" -eq 1 ]; then
  echo "== playwright-cli (Microsoft): browser screenshots/tests driven from the command line =="
  run npm install -g @playwright/cli@latest
  run playwright-cli install --skills || true
  echo
  echo "== Impeccable: design skill + deterministic design detector =="
  echo "When asked, choose Google Antigravity and 'current project'. Then run /impeccable init inside Antigravity."
  run npx impeccable install
  echo "Turning off Impeccable's anonymous design-roll telemetry (re-enable with: npx impeccable telemetry on)"
  run npx impeccable telemetry off || true
fi

if [ "$TASTE" -eq 1 ]; then
  echo "== taste-skill (design-taste-frontend) =="
  echo "Heavy: a full build takes roughly 30-45 minutes and a few hundred thousand tokens. Use it ONCE to polish"
  echo "the site template, not per client. Do not run it at the same time as another design skill."
  run npx skills add https://github.com/Leonxlnx/taste-skill --skill "design-taste-frontend"
fi

if [ "$AGENTS" -eq 1 ]; then
  echo "== agency-agents: install only a small subset into Antigravity =="
  command -v git >/dev/null || { echo "git is required"; exit 1; }
  AGENT_LIST="design-ui-finish-gate-reviewer,testing-accessibility-auditor,testing-reality-checker,testing-evidence-collector,sales-discovery-coach"
  if [ "$DRY" -eq 1 ]; then
    echo "+ git clone --depth 1 https://github.com/msitarzewski/agency-agents.git <tmpdir>"
    echo "+ (cd <tmpdir> && ./scripts/install.sh --tool antigravity --agent $AGENT_LIST --dry-run)"
  else
    TMP="$(mktemp -d)"
    run git clone --depth 1 https://github.com/msitarzewski/agency-agents.git "$TMP/agency-agents"
    if [ -d "$TMP/agency-agents" ]; then
      cd "$TMP/agency-agents"
      run ./scripts/install.sh --tool antigravity --agent "$AGENT_LIST"
    fi
  fi
fi

echo; echo "Done. Restart Antigravity so new skills are picked up."
