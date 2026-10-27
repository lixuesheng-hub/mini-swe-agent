#!/usr/bin/env bash
# Pull all swebench eval images for verified-mini, skip ones already present locally.
# Log: experiments/verified_mini_baseline/pull.log ; failures: pull_failed.txt
set -u
cd "$(dirname "$0")"
LOG=pull.log
FAIL=pull_failed.txt
: > "$FAIL"

pull_one() {
  local img="$1"
  if docker image inspect "$img" >/dev/null 2>&1; then
    echo "[SKIP] $img already present"
    return 0
  fi
  echo "[PULL START] $img $(date -Is)"
  if docker pull "$img" >/dev/null 2>&1; then
    echo "[PULL OK]    $img $(date -Is)"
  else
    echo "[PULL FAIL]  $img $(date -Is)"
    echo "$img" >> "$FAIL"
  fi
}
export -f pull_one
export FAIL

cat images.txt | xargs -P 2 -I {} bash -c 'pull_one "$@"' _ {}
echo "[ALL DONE] $(date -Is); failures: $(wc -l < "$FAIL")"
