#!/usr/bin/env bash
# Keeps collection running without GitHub's cron scheduler, which does not
# reliably start scheduled runs on new repositories.
#
# One workflow run collects at every 15-minute slot (:07, :22, :37, :52 UTC)
# inside the daily window 06:37-21:22 IST, for up to LOOP_MINUTES. Before it
# ends it starts the next run of the same workflow, so the chain continues.
#
# Env: TOMTOM_API_KEY (required), GH_TOKEN (to start the next run),
#      LOOP_MINUTES (default 330), COLLECT_NOW (true = collect immediately),
#      DATA_BRANCH (default bengaluru-data), COLLECT_ARGS (extra collector args),
#      NO_CHAIN (true = do not start the next run; for testing).
set -euo pipefail

LOOP_MINUTES=${LOOP_MINUTES:-330}
DATA_BRANCH=${DATA_BRANCH:-bengaluru-data}
WORKFLOW_FILE=${WORKFLOW_FILE:-collect-bengaluru.yml}
END=$(( $(date -u +%s) + LOOP_MINUTES * 60 ))

setup_data_branch() {
  if git ls-remote --exit-code --heads origin "$DATA_BRANCH" > /dev/null; then
    git fetch -q --depth=1 origin "$DATA_BRANCH"
    git worktree add -q -B "$DATA_BRANCH" data-branch FETCH_HEAD
  else
    git worktree add -q --detach data-branch
    (cd data-branch && git checkout -q --orphan "$DATA_BRANCH" && { git rm -rfq . || true; })
  fi
  git -C data-branch config user.name "traffic-collector"
  git -C data-branch config user.email "41898282+github-actions[bot]@users.noreply.github.com"
}

# 01:07-15:52 UTC = 06:37-21:22 IST
in_window() {
  local hm
  hm=$(date -u +%H%M)
  (( 10#$hm >= 107 && 10#$hm <= 1552 ))
}

next_slot() {
  local t
  t=$(( $(date -u +%s) / 60 * 60 + 60 ))
  while :; do
    case $(date -u -d "@$t" +%M) in
      07|22|37|52) echo "$t"; return ;;
    esac
    t=$(( t + 60 ))
  done
}

collect_once() {
  # A failed collection must not stop the chain; the next slot tries again.
  python3 collector/collect.py --segments collector/segments.csv --out data-branch/data ${COLLECT_ARGS:-} || true
  (
    cd data-branch
    git add -A
    git diff --cached --quiet && exit 0
    git commit -q -m "Collect $(date -u +%Y-%m-%dT%H:%MZ)"
    git push -q origin "HEAD:$DATA_BRANCH" || {
      git pull -q --rebase origin "$DATA_BRANCH" && git push -q origin "HEAD:$DATA_BRANCH"
    } || echo "Push failed; rows stay in this run and go out with the next push."
  )
}

setup_data_branch

if [[ "${COLLECT_NOW:-false}" == "true" ]]; then
  collect_once
fi

while :; do
  slot=$(next_slot)
  (( slot > END )) && break
  wait_s=$(( slot - $(date -u +%s) ))
  (( wait_s > 0 )) && sleep "$wait_s"
  if in_window; then collect_once; else echo "$(date -u +%H:%M) UTC: outside 06:37-21:22 IST, skipped"; fi
done

if [[ "${NO_CHAIN:-false}" == "true" ]]; then
  echo "NO_CHAIN set: not starting the next run."
else
  gh workflow run "$WORKFLOW_FILE" --ref "${GITHUB_REF_NAME:?}" -f chained=true
  echo "Started the next run of $WORKFLOW_FILE."
fi
