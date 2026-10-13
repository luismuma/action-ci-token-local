#!/usr/bin/env bash
# =============================================================================
# local-test.sh — Local scenario runner for action-ci-token
#
# Loads scenarios from test/scenarios/*.env, runs each against the get-token
# entrypoint, and asserts the outcome matches the scenario's EXPECT.
#
# Prerequisites:
#   - AWS credentials configured (aws sso login / AWS_PROFILE)
#   - Python 3 (system python3/pip3 or a .venv/ at repo root)
#
# Usage:
#   bash test/local-test.sh                    # run all scenarios
#   bash test/local-test.sh 02                 # run scenario matching '02'
#   bash test/local-test.sh 02 04              # run several by pattern
#   bash test/local-test.sh --list             # list available scenarios
#   bash test/local-test.sh --full             # after scenarios, also run the
#                                              # legacy end-to-end steps
#                                              # (refresh passphrase + Zeus)
#
# Exit codes:
#   0  all matched scenarios passed
#   1  one or more scenarios failed the assertion
#   2  usage / configuration error
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCENARIOS_DIR="$SCRIPT_DIR/scenarios"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/.venv/bin/python"
  PIP="$REPO_ROOT/.venv/bin/pip"
elif [[ -x "$REPO_ROOT/.venv/Scripts/python.exe" ]]; then
  PY="$REPO_ROOT/.venv/Scripts/python.exe"
  PIP="$REPO_ROOT/.venv/Scripts/pip.exe"
else
  PY="$(command -v python3 || command -v python || true)"
  PIP="$(command -v pip3 || command -v pip || true)"
  [[ -z "$PY" || -z "$PIP" ]] && { echo "ERROR: python3/pip3 not found in PATH. Install Python 3 or create a venv at $REPO_ROOT/.venv" >&2; exit 2; }
fi

RUN_FULL=false
PATTERNS=()
for arg in "$@"; do
  case "$arg" in
    --list) ls -1 "$SCENARIOS_DIR"/*.env 2>/dev/null | xargs -n1 basename | sed 's/\.env$//'; exit 0 ;;
    --full) RUN_FULL=true ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    -*) echo "ERROR: unknown flag '$arg'" >&2; exit 2 ;;
    *) PATTERNS+=("$arg") ;;
  esac
done

mapfile -t ALL_SCENARIOS < <(ls -1 "$SCENARIOS_DIR"/*.env 2>/dev/null | sort)
if [[ ${#ALL_SCENARIOS[@]} -eq 0 ]]; then
  echo "ERROR: no scenarios found in $SCENARIOS_DIR" >&2; exit 2
fi

if [[ ${#PATTERNS[@]} -eq 0 ]]; then
  SELECTED=("${ALL_SCENARIOS[@]}")
else
  SELECTED=()
  for s in "${ALL_SCENARIOS[@]}"; do
    for p in "${PATTERNS[@]}"; do
      if [[ "$(basename "$s")" == *"$p"* ]]; then SELECTED+=("$s"); break; fi
    done
  done
  if [[ ${#SELECTED[@]} -eq 0 ]]; then
    echo "ERROR: no scenarios match: ${PATTERNS[*]}" >&2; exit 2
  fi
fi

# ─── One-time setup: python deps + config ────────────────────────────────────
echo "▶ Setup — install Python dependencies"
$PIP install --require-hashes -r "$REPO_ROOT/internal/get-token/requirements.txt" --quiet
echo "  ✓ Dependencies installed"

echo "▶ Setup — load platform apps config"
SETUP_OUT=$(mktemp)
export GITHUB_OUTPUT="$SETUP_OUT"
export GITHUB_ENV=$(mktemp)
export GITHUB_STEP_SUMMARY=$(mktemp)
export CONFIG_PATH="$REPO_ROOT/internal/get-config/config"
export INCLUDE_CAP_REPOS="${INCLUDE_CAP_REPOS:-false}"
export PLATFORM_REPO_INPUT="${PLATFORM_REPO_INPUT:-}"
$PY "$REPO_ROOT/internal/get-config/get-config.py" > /dev/null
PLATFORM_REPOSITORIES_DEFAULT=$(grep "^repos=" "$SETUP_OUT" | head -1 | cut -d= -f2- || true)
rm -f "$SETUP_OUT" "$GITHUB_ENV" "$GITHUB_STEP_SUMMARY"
echo "  ✓ Config loaded"

# ─── Scenario runner ─────────────────────────────────────────────────────────
run_scenario() {
  local file="$1"
  local name
  name=$(basename "$file" .env)

  # shellcheck disable=SC1090
  ( set +u
    DESCRIPTION=""; PROFILE=""; CALLER_REPO=""; REPOSITORIES=""; GITHUB_ACTOR=""
    EXPECT=""; EXPECT_LOG=""; PLATFORM_REPOSITORIES=""; GITHUB_ORG="mapfre-tech"; AWS_REGION="eu-west-1"
    . "$file"

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Scenario: $name"
    echo "  $DESCRIPTION"
    echo "───────────────────────────────────────────────────────────────"
    echo "  Actor:        $GITHUB_ACTOR"
    echo "  Profile:      $PROFILE"
    echo "  Caller repo:  $CALLER_REPO"
    echo "  Scope repos:  $REPOSITORIES"
    echo "  Expect:       $EXPECT${EXPECT_LOG:+  (log must contain: '$EXPECT_LOG')}"
    echo "═══════════════════════════════════════════════════════════════"

    local out log
    out=$(mktemp); log=$(mktemp)
    export GITHUB_OUTPUT="$out"
    export GITHUB_ENV=$(mktemp)
    export GITHUB_STEP_SUMMARY=$(mktemp)
    export GH_TOKEN_ENCRYPTION_PASSPHRASE=$(openssl rand -hex 16)
    export PROFILE REPOSITORIES CALLER_REPO GITHUB_ORG AWS_REGION
    export CALLER_ACTOR="$GITHUB_ACTOR"
    export PLATFORM_REPOSITORIES="${PLATFORM_REPOSITORIES:-}"

    local rc=0
    $PY "$REPO_ROOT/internal/get-token/get-token.py" >"$log" 2>&1 || rc=$?
    cat "$log"

    local verdict="FAIL"
    if [[ "$EXPECT" == "pass" ]]; then
      if [[ $rc -eq 0 ]] && grep -q "encoded_token=" "$out"; then
        if [[ -n "$EXPECT_LOG" ]] && ! grep -q -- "$EXPECT_LOG" "$log"; then
          echo ""; echo "  ✗ Expected log fragment not found: '$EXPECT_LOG'"
        else
          verdict="PASS"
        fi
      else
        echo ""; echo "  ✗ Expected token generation to succeed (rc=$rc, encoded_token absent)"
      fi
    elif [[ "$EXPECT" == "fail" ]]; then
      if [[ $rc -ne 0 ]] && ! grep -q "encoded_token=" "$out"; then
        if [[ -n "$EXPECT_LOG" ]] && ! grep -q -- "$EXPECT_LOG" "$log"; then
          echo ""; echo "  ✗ Denial happened but expected log fragment not found: '$EXPECT_LOG'"
        else
          verdict="PASS"
        fi
      else
        echo ""; echo "  ✗ Expected token generation to fail (rc=$rc, encoded_token present=$(grep -c encoded_token= "$out"))"
      fi
    else
      echo "  ✗ Unknown EXPECT value: '$EXPECT' (must be pass|fail)"
    fi

    rm -f "$out" "$log" "$GITHUB_ENV" "$GITHUB_STEP_SUMMARY"

    echo ""
    if [[ "$verdict" == "PASS" ]]; then
      echo "  ✓ Scenario '$name' PASSED"
      exit 0
    else
      echo "  ✗ Scenario '$name' FAILED"
      exit 1
    fi
  )
}

PASS_COUNT=0
FAIL_COUNT=0
FAILED_NAMES=()
for s in "${SELECTED[@]}"; do
  if run_scenario "$s"; then
    PASS_COUNT=$((PASS_COUNT+1))
  else
    FAIL_COUNT=$((FAIL_COUNT+1))
    FAILED_NAMES+=("$(basename "$s" .env)")
  fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Summary: $PASS_COUNT passed, $FAIL_COUNT failed (of ${#SELECTED[@]} run)"
if [[ $FAIL_COUNT -gt 0 ]]; then
  echo "  Failed scenarios:"
  for n in "${FAILED_NAMES[@]}"; do echo "    - $n"; done
fi
echo "═══════════════════════════════════════════════════════════════"

# ─── Optional: legacy end-to-end steps ───────────────────────────────────────
if [[ "$RUN_FULL" == "true" ]]; then
  echo ""
  echo "▶ Extended — Refresh GH_TOKEN_ENCRYPTION_PASSPHRASE (secrets profile)"
  EXT_OUT=$(mktemp)
  export GITHUB_OUTPUT="$EXT_OUT"
  export GITHUB_ENV=$(mktemp)
  export GITHUB_STEP_SUMMARY=$(mktemp)
  export GH_TOKEN_ENCRYPTION_PASSPHRASE=$(openssl rand -hex 16)
  export PROFILE="secrets"
  export REPOSITORIES="mapfre-tech/arch-ram-java-container-test"
  export CALLER_REPO="mapfre-tech/arch-ram-java-container-test"
  export CALLER_ACTOR="FHALEJ5_mapfre"
  export GITHUB_ORG="mapfre-tech"
  export AWS_REGION="eu-west-1"
  export PLATFORM_REPOSITORIES=""
  $PY "$REPO_ROOT/internal/get-token/get-token.py" || echo "  (secrets step returned non-zero — inspect output above)"
  rm -f "$EXT_OUT" "$GITHUB_ENV" "$GITHUB_STEP_SUMMARY"

  echo ""
  echo "▶ Extended — Zeus actor resolution (PTIZ-4582)"
  ZEUS_OUT=$(mktemp)
  export GITHUB_OUTPUT="$ZEUS_OUT"
  export GITHUB_ENV=$(mktemp)
  export GITHUB_STEP_SUMMARY=$(mktemp)
  export GH_TOKEN_ENCRYPTION_PASSPHRASE=$(openssl rand -hex 16)
  export REPOSITORIES="mapfre-tech/arch-plat-binding"
  export PROFILE="reader"
  export GITHUB_RUN_ID="00000000001"
  export CALLER_REPO="${REPOSITORIES}"
  export CALLER_ACTOR="APP-GITHUBOPS_mapfre"
  export TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
  REF_NAME="refs/registry/run/${CALLER_REPO}/${GITHUB_RUN_ID}/FHALEJ5_mapfre/${TIMESTAMP}"
  SHA="7ccaa626dfcff9b4c53895094b20756554954c0f"
  echo "Publishing ${REF_NAME} → ${SHA}"
  gh api -X POST "/repos/mapfre-tech/arch-plat-zeus-actor-registry/git/refs" \
    -f ref="${REF_NAME}" -f sha="${SHA}" || true
  $PY "$REPO_ROOT/internal/get-token/get-token.py" || echo "  (Zeus step returned non-zero — inspect output above)"
  rm -f "$ZEUS_OUT" "$GITHUB_ENV" "$GITHUB_STEP_SUMMARY"
fi

exit $FAIL_COUNT
