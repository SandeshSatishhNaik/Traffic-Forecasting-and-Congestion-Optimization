#!/usr/bin/env bash
# Keeps collection running without GitHub's cron scheduler, which does not
# reliably start scheduled runs on new repositories.
#
# One workflow run wakes at every 15-minute slot (:07, :22, :37, :52 past the
# hour, IST) for up to LOOP_MINUTES and collects when due_now says so. Before
# it ends it starts the next run of the same workflow, so the chain continues
# around the clock.
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

# 24/7 schedule, denser when traffic changes fastest (IST):
#   07:07-11:07 and 16:07-21:07   every 15 min (rush hours)
#   11:37-15:37                   every 30 min (midday)
#   21:37-06:52                   every hour, at :07 (night and early morning)
# = 56 readings a day; x 10 roads x 31 days = 17,360 TomTom requests a month,
# inside the 20,000 free tier. Every 15 min around the clock would need 29,760.
due_now() {
  local hm m
  hm=$(TZ=Asia/Kolkata date +%H%M)
  m=${hm:2:2}
  hm=$((10#$hm))
  if (( (hm >= 707 && hm <= 1107) || (hm >= 1607 && hm <= 2107) )); then return 0; fi
  if (( hm > 1107 && hm < 1607 )); then [[ $m == 07 || $m == 37 ]]; return; fi
  [[ $m == 07 ]]
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
  if due_now; then collect_once; else echo "$(TZ=Asia/Kolkata date +%H:%M) IST: not a collection slot, skipped"; fi
done

if [[ "${NO_CHAIN:-false}" == "true" ]]; then
  echo "NO_CHAIN set: not starting the next run."
else
  gh workflow run "$WORKFLOW_FILE" --ref "${GITHUB_REF_NAME:?}" -f chained=true
  echo "Started the next run of $WORKFLOW_FILE."
fi
