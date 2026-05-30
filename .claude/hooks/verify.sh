#!/usr/bin/env bash
# Routing Copilot verification hook.
#
# Wire this into Claude Code as a Stop hook (runs at the end of a response, not
# on every edit, so it doesn't slow down mid-task). In .claude/settings.json:
#
#   {
#     "hooks": {
#       "Stop": [
#         { "hooks": [ { "type": "command", "command": ".claude/hooks/verify.sh" } ] }
#       ]
#     }
#   }
#
# Confirm the exact hooks schema against the current docs
# (https://docs.claude.com/en/docs/claude-code) — the event names and shape can
# change. The script itself is the durable part.
#
# Exits non-zero on failure so Claude sees the regression and fixes it.
set -uo pipefail
fail=0

echo "[verify] frontend typecheck"
if [ -d frontend ]; then
  npm --prefix frontend run typecheck || fail=1
fi

echo "[verify] load-bearing tests"
pytest tests/product_api tests/product_copilot tests/system_d_final \
       tests/test_evaluation.py tests/test_llm_adapter.py -q || fail=1

echo "[verify] reproduction paths resolve"
python -m product.evaluation.verify_reports >/dev/null 2>&1
case $? in
  0) : ;;                       # ran clean
  *) echo "[verify] verify_reports exited non-zero (ok if dependency/key missing; NOT ok if reports missing)";;
esac

if [ "$fail" -ne 0 ]; then
  echo "[verify] FAILED — fix before finishing."
  exit 1
fi
echo "[verify] OK"