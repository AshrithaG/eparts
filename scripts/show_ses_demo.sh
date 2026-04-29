#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# eParts SES — High-level pipeline demo for teammates (clone → run)
#
# What it does:
#   1. Verifies Python 3 + installs dependencies if needed (first run)
#   2. Reminds you about .env for live Jira/GitHub/LLM (optional)
#   3. Prints a short narrative of the Requirements pipeline
#   4. Runs demo.py — prefers examples/demo_client_review.transcript.vtt, else transcripts/*.vtt (or SES_DEMO_VTT)
#   5. Optionally opens local HTML dashboards in your browser (macOS)
#
# Usage:
#   chmod +x scripts/show_ses_demo.sh
#   ./scripts/show_ses_demo.sh              # interactive (press ENTER once)
#   ./scripts/show_ses_demo.sh --auto       # non-interactive (good for screen record)
#   ./scripts/show_ses_demo.sh --step       # press ENTER after each agent (live talk track)
#
# Env:
#   SES_DEMO_AUTO=1            same as --auto (skip ENTER prompt)
#   SES_DEMO_STEP=1            same as --step (Enter between agents)
#   SES_DEMO_OPEN_DASHBOARDS=0 skip opening browser tabs after demo
#   SES_DEMO_VTT=/abs/path/file.transcript.vtt   force which transcript
#   PYTHON                     override python binary (default: python3)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
AUTO_FLAG=0
STEP_FLAG=0
SKIP_OPEN=0

for arg in "$@"; do
  case "$arg" in
    --auto) AUTO_FLAG=1 ;;
    --step) STEP_FLAG=1 ;;
    --no-open|--skip-dashboards) SKIP_OPEN=1 ;;
    -h|--help)
      grep '^#' "$ROOT/scripts/show_ses_demo.sh" | head -30 | sed 's/^# \{0,1\}//'
      exit 0
      ;;
  esac
done

if [[ "$AUTO_FLAG" -eq 1 ]] || [[ "${SES_DEMO_AUTO:-}" =~ ^(1|true|yes)$ ]]; then
  export SES_DEMO_AUTO=1
fi

if [[ "$STEP_FLAG" -eq 1 ]] || [[ "${SES_DEMO_STEP:-}" =~ ^(1|true|yes)$ ]]; then
  export SES_DEMO_STEP=1
fi

BLUE='\033[94m'
CYAN='\033[96m'
GREEN='\033[92m'
YELLOW='\033[93m'
DIM='\033[2m'
RESET='\033[0m'
BOLD='\033[1m'

echo ""
echo -e "${CYAN}${BOLD}eParts SES — Pipeline demo (Requirements workstream)${RESET}"
echo -e "${DIM}Repo: ${ROOT}${RESET}"
echo ""

need_python() {
  if ! command -v "$PYTHON" &>/dev/null; then
    echo -e "${YELLOW}Need Python 3.12+ on PATH as '${PYTHON}'. Install from python.org or use pyenv/uv.${RESET}" >&2
    exit 1
  fi
}

ensure_deps() {
  if "$PYTHON" -c "import fastapi, chromadb" 2>/dev/null; then
    echo -e "${GREEN}Python deps OK${RESET}"
    return 0
  fi
  echo -e "${YELLOW}First run: installing dependencies from requirements.txt …${RESET}"
  "$PYTHON" -m pip install -q -r "$ROOT/requirements.txt"
  echo -e "${GREEN}Dependencies installed.${RESET}"
}

ensure_transcript() {
  if [[ -n "${SES_DEMO_VTT:-}" ]] && [[ ! -f "$SES_DEMO_VTT" ]]; then
    echo -e "${YELLOW}SES_DEMO_VTT file not found: ${SES_DEMO_VTT}${RESET}" >&2
    exit 1
  fi
  if [[ -n "${SES_DEMO_VTT:-}" ]] && [[ -f "$SES_DEMO_VTT" ]]; then
    return 0
  fi
  if [[ -f "$ROOT/examples/demo_client_review.transcript.vtt" ]]; then
    return 0
  fi
  local n
  n=$(find "$ROOT/transcripts" -maxdepth 1 -name '*.transcript.vtt' 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${n:-0}" -eq 0 ]]; then
    echo -e "${YELLOW}No suitable .transcript.vtt found.${RESET}" >&2
    echo "  Expected examples/demo_client_review.transcript.vtt (bundled) or transcripts/*.transcript.vtt" >&2
    echo "  Or: SES_DEMO_VTT=/path/to/file.transcript.vtt $0" >&2
    exit 1
  fi
}

resolve_vtt_arg() {
  if [[ -n "${SES_DEMO_VTT:-}" ]] && [[ -f "$SES_DEMO_VTT" ]]; then
    printf '%s' "$SES_DEMO_VTT"
    return 0
  fi
  if [[ -f "$ROOT/examples/demo_client_review.transcript.vtt" ]]; then
    printf '%s' "$ROOT/examples/demo_client_review.transcript.vtt"
    return 0
  fi
  printf ''
}

env_hint() {
  if [[ ! -f "$ROOT/.env" ]]; then
    echo -e "${YELLOW}Tip:${RESET} No .env file. Copy .env.example → .env for Jira, GitHub, and LLM keys."
    echo -e "     ${DIM}The pipeline still runs offline with heuristics if keys are missing.${RESET}"
    echo ""
  fi
}

story() {
  echo -e "${BOLD}What you will see (90 seconds of story)${RESET}"
  echo ""
  echo "  1. A client meeting transcript (.vtt) is the trigger."
  echo "  2. Seven agents run in sequence: parse → prioritize → extract REQs →"
  echo "     Jira tickets → Confluence-style minutes → decision log → drift check."
  echo "  3. Each step deposits into SharedMemory; significant steps emit EventBus events."
  echo "  4. Drift can fan out to the Architecture pipeline (event-driven, not a loop)."
  echo ""
  echo -e "${DIM}Implementation: demo.py runs PipelineExecutor on REQUIREMENTS_PIPELINE.${RESET}"
  echo ""
}

open_dashboards() {
  if [[ "$SKIP_OPEN" -eq 1 ]] || [[ "${SES_DEMO_OPEN_DASHBOARDS:-1}" == "0" ]]; then
    return 0
  fi
  if [[ "$(uname -s)" != "Darwin" ]]; then
    echo -e "${DIM}Open dashboards manually: dashboard/interactive_architecture.html, dashboard/wbs.html${RESET}"
    return 0
  fi
  echo -e "${GREEN}Opening dashboards in default browser…${RESET}"
  open "$ROOT/dashboard/interactive_architecture.html" 2>/dev/null || true
  open "$ROOT/dashboard/wbs.html" 2>/dev/null || true
  open "$ROOT/dashboard/event_flow.html" 2>/dev/null || true
}

# --- main --------------------------------------------------------------------
need_python
ensure_deps
ensure_transcript
env_hint
story

echo -e "${BOLD}Starting live pipeline run…${RESET}"
echo ""

EXTRA=()
if [[ "$AUTO_FLAG" -eq 1 ]]; then
  EXTRA+=(--auto)
  export SES_DEMO_AUTO=1
fi
if [[ "$STEP_FLAG" -eq 1 ]] || [[ "${SES_DEMO_STEP:-}" =~ ^(1|true|yes)$ ]]; then
  EXTRA+=(--step)
fi

VTT="$(resolve_vtt_arg)"
if [[ -n "$VTT" ]]; then
  echo -e "${DIM}Transcript:${RESET} ${VTT#$ROOT/}"
  echo ""
  "$PYTHON" "$ROOT/demo.py" "$VTT" "${EXTRA[@]}"
else
  "$PYTHON" "$ROOT/demo.py" "${EXTRA[@]}"
fi

echo ""
echo -e "${GREEN}Pipeline run finished.${RESET}"
open_dashboards

echo ""
echo -e "${DIM}More:${RESET} full walkthrough with \`$PYTHON demo_full.py\`  |  playbook: DEMO_PLAYBOOK.md"
echo ""
