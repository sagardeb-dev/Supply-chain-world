#!/usr/bin/env bash
# Deterministic paper checks — zero tokens. Run before any share/submit.
# Usage: ./check.sh [paper.tex]   (also scans intro.md/draft prose)
set -u
cd "$(dirname "$0")"
TEX="${1:-paper.tex}"
FAIL=0

echo "== 1. Build =="
if ~/.local/bin/tectonic "$TEX" >/tmp/tectonic.log 2>&1; then
  echo "OK: $TEX builds ($(ls -la "${TEX%.tex}.pdf" | awk '{print $5}') bytes)"
else
  echo "FAIL: build broke"; tail -15 /tmp/tectonic.log; FAIL=1
fi

echo "== 2. Slop greplist (WRITING.md D3) =="
SLOP='delve|delves|delved|delving|intricate|intricac|underscor|showcas|surpass\w|boasts|garner|groundbreaking|advancement|meticulous|pivotal|moreover|furthermore|leverag'
if grep -inE "$SLOP" "$TEX" intro.md 2>/dev/null | grep -v '^\s*%'; then
  echo "FAIL: slop words above — rewrite them"; FAIL=1
else
  echo "OK: greplist clean"
fi

echo "== 3. Unresolved placeholders =="
if grep -n "PENDING\|SLOT\|TODO\|XXX\|\[N\]" "$TEX" | grep -v '^\s*%'; then
  echo "WARN: placeholders remain (fine mid-draft, FAIL at submit time)"
else
  echo "OK: no placeholders"
fi

echo "== 4. Forbidden numbers (retired 9-seed story) =="
# Old EASY/MED/HARD tier means must never appear; no skill-vs-stress gradient claims.
if grep -nE '0\.95.?/.?0\.78|EASY|MED/|HARD' "$TEX"; then
  echo "FAIL: retired 9-seed tier means or EASY/MED/HARD labels found"; FAIL=1
else
  echo "OK: no retired numbers"
fi

echo "== 5. Seed-99 guard =="
# ponytail: crude grep; drop once the trace is read and the cell is cleared
if grep -n "1\.85" "$TEX"; then
  echo "WARN: deepseek seed-99 (1.85) cited — trace still unread, verify first"
fi

echo "== 6. Em-dash density =="
D=$(grep -o '—' "$TEX" | wc -l); W=$(wc -w < "$TEX")
echo "info: $D em dashes / $W words $( [ "$D" -gt $((W/300+3)) ] && echo '(high — thin them out)' )"

[ $FAIL -eq 0 ] && echo "== ALL HARD CHECKS PASSED ==" || echo "== FAILURES ABOVE =="
exit $FAIL
