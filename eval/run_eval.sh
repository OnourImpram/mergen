#!/usr/bin/env bash
# eval/run_eval.sh
#
# Evaluation harness skeleton for mergen vs vanilla spec-kit.
# Reads result files written by the two toolchain runs and prints a summary table.
#
# STATUS: procedure skeleton only. All result files are expected to contain
# real measured values written by the evaluator following eval/methodology.md.
# This script does NOT run Claude Code, spec-kit, or any LLM. It aggregates
# result files that the evaluator must populate first.
#
# USAGE:
#   bash eval/run_eval.sh [--results-dir <path>]
#
# OPTIONS:
#   --results-dir <path>   Directory containing result files (default: eval/results)
#   --help                 Print this help and exit
#
# REQUIRED result files (all written by the evaluator during the two runs):
#   speckit-phantom.txt          one line: speckit_phantom_rate=<float 0-1>
#   speckit-adversarial.txt      one line: speckit_adversarial_catch=<integer>
#   speckit-start.txt            one line: Unix epoch seconds (from `date +%s`)
#   speckit-end.txt              one line: Unix epoch seconds
#   mergen-phantom.txt        one line: mergen_phantom_rate=<float 0-1>
#   mergen-adversarial.txt    one line: mergen_adversarial_catch=<integer>
#   mergen-speedup.txt        one line: mergen_speedup=<float>
#   speckit-overbuild.txt        one line: speckit_overbuild_rate=<float 0-1>
#   mergen-overbuild.txt      one line: mergen_overbuild_rate=<float 0-1>
#   mergen-start.txt          one line: Unix epoch seconds
#   mergen-end.txt            one line: Unix epoch seconds
#
# OPTIONAL result files (used when present):
#   mergen-tasks-dag.json     tasks-dag.json emitted by /mergen.tasks
#   mergen-verify-report.md   verification-report.md from /mergen.verify
#   speckit-tasks.md             tasks.md from the spec-kit run
#   mergen-tasks.md           tasks.md from the mergen run
#
# DEPENDENCIES: bash 4+, jq (optional, for DAG summary), awk, grep
#
# LICENSE: Apache-2.0
# AFFILIATION: Not affiliated with GitHub, Inc. or Anthropic, PBC.
#   Spec Kit is a GitHub, Inc. project (MIT License).
#   Claude and Claude Code are trademarks of Anthropic, PBC.

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

RESULTS_DIR="eval/results"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --results-dir)
      RESULTS_DIR="$2"
      shift 2
      ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Read a key=value line from a file and echo the value.
# Usage: read_kv <file> <key>
read_kv() {
  local file="$1"
  local key="$2"
  if [[ ! -f "$file" ]]; then
    echo "MISSING"
    return
  fi
  local val
  val=$(grep "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-)
  if [[ -z "$val" ]]; then
    echo "MISSING"
  else
    echo "$val"
  fi
}

# Read a single-line file (e.g. a Unix timestamp).
read_line() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "MISSING"
    return
  fi
  head -1 "$file"
}

# Compute elapsed seconds from two epoch files. Prints MISSING if either is absent.
elapsed_seconds() {
  local start_file="$1"
  local end_file="$2"
  local start end
  start=$(read_line "$start_file")
  end=$(read_line "$end_file")
  if [[ "$start" == "MISSING" || "$end" == "MISSING" ]]; then
    echo "MISSING"
    return
  fi
  echo $(( end - start ))
}

# Count [X] tasks in a tasks.md file.
count_completed_tasks() {
  local file="$1"
  if [[ ! -f "$file" ]]; then
    echo "MISSING"
    return
  fi
  grep -ic '^\- \[x\]' "$file" || echo "0"
}

# ---------------------------------------------------------------------------
# Check results directory
# ---------------------------------------------------------------------------

if [[ ! -d "$RESULTS_DIR" ]]; then
  echo "ERROR: results directory does not exist: $RESULTS_DIR" >&2
  echo ""
  echo "TODO: Complete both toolchain runs per eval/methodology.md before running" \
       "this script."
  echo "      The runs must write result files into $RESULTS_DIR."
  exit 1
fi

# ---------------------------------------------------------------------------
# Read values
# ---------------------------------------------------------------------------

SK_PHANTOM=$(read_kv   "$RESULTS_DIR/speckit-phantom.txt"     "speckit_phantom_rate")
SK_CATCH=$(read_kv     "$RESULTS_DIR/speckit-adversarial.txt" "speckit_adversarial_catch")
SK_ELAPSED=$(elapsed_seconds \
               "$RESULTS_DIR/speckit-start.txt" \
               "$RESULTS_DIR/speckit-end.txt")

HC_PHANTOM=$(read_kv   "$RESULTS_DIR/mergen-phantom.txt"     "mergen_phantom_rate")
HC_CATCH=$(read_kv     "$RESULTS_DIR/mergen-adversarial.txt" "mergen_adversarial_catch")
HC_SPEEDUP=$(read_kv   "$RESULTS_DIR/mergen-speedup.txt"     "mergen_speedup")
HC_ELAPSED=$(elapsed_seconds \
               "$RESULTS_DIR/mergen-start.txt" \
               "$RESULTS_DIR/mergen-end.txt")

SK_OVERBUILD=$(read_kv "$RESULTS_DIR/speckit-overbuild.txt"   "speckit_overbuild_rate")
HC_OVERBUILD=$(read_kv "$RESULTS_DIR/mergen-overbuild.txt" "mergen_overbuild_rate")

SK_TASKS=$(count_completed_tasks "$RESULTS_DIR/speckit-tasks.md")
HC_TASKS=$(count_completed_tasks "$RESULTS_DIR/mergen-tasks.md")

# ---------------------------------------------------------------------------
# DAG summary (optional, requires jq)
# ---------------------------------------------------------------------------

DAG_SUMMARY=""
DAG_FILE="$RESULTS_DIR/mergen-tasks-dag.json"
if [[ -f "$DAG_FILE" ]]; then
  if command -v jq &>/dev/null; then
    WAVE_COUNT=$(jq 'length' "$DAG_FILE" 2>/dev/null || echo "parse error")
    MAX_WAVE=$(jq '[.[] | length] | max' "$DAG_FILE" 2>/dev/null || echo "parse error")
    DAG_SUMMARY="  Waves: $WAVE_COUNT   Max tasks/wave: $MAX_WAVE"
  else
    DAG_SUMMARY="  (jq not available; install jq to show DAG summary)"
  fi
fi

# ---------------------------------------------------------------------------
# Verify report summary (optional)
# ---------------------------------------------------------------------------

VERIFY_SUMMARY=""
VERIFY_FILE="$RESULTS_DIR/mergen-verify-report.md"
if [[ -f "$VERIFY_FILE" ]]; then
  REVERTED=$(grep -c 'REVERTED'     "$VERIFY_FILE" 2>/dev/null || echo "0")
  MISSING_F=$(grep -c 'MISSING FILE' "$VERIFY_FILE" 2>/dev/null || echo "0")
  TEST_FAIL=$(grep -c 'TEST FAIL'    "$VERIFY_FILE" 2>/dev/null || echo "0")
  SPEC_GAP=$(grep -c 'SPEC GAP'     "$VERIFY_FILE" 2>/dev/null || echo "0")
  VERIFY_SUMMARY=$(printf \
    "  Reverted: %s   Missing file: %s   Test fail: %s   Spec gap: %s" \
    "$REVERTED" "$MISSING_F" "$TEST_FAIL" "$SPEC_GAP")
fi

# ---------------------------------------------------------------------------
# Check for missing required values
# ---------------------------------------------------------------------------

MISSING_COUNT=0
for label_val in \
    "speckit_phantom_rate:$SK_PHANTOM" \
    "speckit_adversarial_catch:$SK_CATCH" \
    "speckit_elapsed:$SK_ELAPSED" \
    "mergen_phantom_rate:$HC_PHANTOM" \
    "mergen_adversarial_catch:$HC_CATCH" \
    "mergen_speedup:$HC_SPEEDUP" \
    "mergen_elapsed:$HC_ELAPSED"; do
  key="${label_val%%:*}"
  val="${label_val##*:}"
  if [[ "$val" == "MISSING" ]]; then
    echo "WARNING: $key not found. Complete the corresponding run and write the result file."
    MISSING_COUNT=$(( MISSING_COUNT + 1 ))
  fi
done

if [[ "$MISSING_COUNT" -gt 0 ]]; then
  echo ""
  echo "TODO: $MISSING_COUNT required value(s) are missing."
  echo "      Follow eval/methodology.md to complete both runs, then re-run this script."
  echo ""
fi

# ---------------------------------------------------------------------------
# Print summary table
# ---------------------------------------------------------------------------

echo ""
echo "======================================================================="
echo " mergen vs spec-kit: evaluation summary"
echo "======================================================================="
echo ""
printf "%-34s  %-18s  %-18s\n" "Metric" "spec-kit" "mergen"
printf "%-34s  %-18s  %-18s\n" "$(printf '%.0s-' {1..34})" \
       "$(printf '%.0s-' {1..18})" "$(printf '%.0s-' {1..18})"
printf "%-34s  %-18s  %-18s\n" \
  "Phantom-completion rate (Metric 1)" \
  "$SK_PHANTOM" \
  "$HC_PHANTOM"
printf "%-34s  %-18s  %-18s\n" \
  "Adversarial catch (Metric 3)" \
  "$SK_CATCH" \
  "$HC_CATCH"
printf "%-34s  %-18s  %-18s\n" \
  "Parallel speedup (Metric 2)" \
  "1.0x (serial only)" \
  "$HC_SPEEDUP"
printf "%-34s  %-18s  %-18s\n" \
  "Over-build rate (Metric 4)" \
  "$SK_OVERBUILD" \
  "$HC_OVERBUILD"
printf "%-34s  %-18s  %-18s\n" \
  "Wall-clock elapsed (seconds)" \
  "$SK_ELAPSED" \
  "$HC_ELAPSED"
printf "%-34s  %-18s  %-18s\n" \
  "Completed [X] tasks" \
  "$SK_TASKS" \
  "$HC_TASKS"
echo ""

if [[ -n "$DAG_SUMMARY" ]]; then
  echo "DAG structure (from mergen-tasks-dag.json):"
  echo "$DAG_SUMMARY"
  echo ""
fi

if [[ -n "$VERIFY_SUMMARY" ]]; then
  echo "Verify report lens counts (raw, before dedup; from verification-report.md):"
  echo "$VERIFY_SUMMARY"
  echo ""
fi

echo "======================================================================="
echo ""
echo "IMPORTANT: All values above come from result files written by the evaluator."
echo "This script does not run Claude Code, spec-kit, or any LLM."
echo "Any value shown as MISSING means the corresponding run has not been completed"
echo "or the result file was not written. Follow eval/methodology.md."
echo ""
echo "Replace SYNTHETIC placeholders in eval/methodology.md with the real values"
echo "shown above before publishing any claim."
echo "======================================================================="
