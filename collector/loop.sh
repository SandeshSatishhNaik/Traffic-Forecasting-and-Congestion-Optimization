#!/usr/bin/env bash
# Keeps collection running without GitHub's cron scheduler, which does not
# reliably start scheduled runs on new repositories.
#
# One workflow run wakes at every 15-minute slot (:07, :22, :37, :52 past the
# hour, UTC) for up to LOOP_MINUTES and collects when due_tiers says so. Before
# it ends it starts the next run of the same workflow, so the chain continues
# around the clock.
#
# Where the readings go:
#   DATA_REPO_TOKEN set   -> a private data repository (DATA_REPO, a fine-grained
#                            token with Contents read/write on that repository only).
#                            TomTom's terms do not allow publishing the results.
#   DATA_REPO_TOKEN unset -> the public bengaluru-data branch of this repository
#                            (the old behaviour, kept so collection never stops).
#
# Env: TOMTOM_API_KEY (required), GH_TOKEN (to start the next run),
#      LOOP_MINUTES (default 330), COLLECT_NOW (true = collect immediately),
#      DATA_REPO_TOKEN, DATA_REPO (default SandeshSatishhNaik/traffic-data-private),
#      DATA_BRANCH (public branch, default bengaluru-data),
#      COLLECT_ARGS (extra collector args), COLLECT_INCIDENTS (default true),
#      NO_CHAIN (true = do not start the next run; for testing).
set -euo pipefail

LOOP_MINUTES=${LOOP_MINUTES:-330}
DATA_BRANCH=${DATA_BRANCH:-bengaluru-data}
WORKFLOW_FILE=${WORKFLOW_FILE:-collect-bengaluru.yml}
END=$(( $(date -u +%s) + LOOP_MINUTES * 60 ))

# Hide credentials if git ever prints a remote URL.
redact() { sed -E 's#(https://)[^@/ ]+@#\1***@#g'; }

setup_public_branch() {
  if git ls-remote --exit-code --heads origin "$DATA_BRANCH" > /dev/null; then
    git fetch -q --depth=1 origin "$DATA_BRANCH"
    git worktree add -q -B "$DATA_BRANCH" data-branch FETCH_HEAD
  else
    git worktree add -q --detach data-branch
    (cd data-branch && git checkout -q --orphan "$DATA_BRANCH" && { git rm -rfq . || true; })
  fi
}

setup_private_repo() {
  export GIT_TERMINAL_PROMPT=0
  DATA_REPO_URL=${DATA_REPO_URL:-https://x-access-token:${DATA_REPO_TOKEN}@github.com/${DATA_REPO}.git}
  # An empty repository (created without a README) clones fine but has no commits yet.
  local try cloned=false
  for try in 1 2 3; do
    if git clone -q --depth=1 "$DATA_REPO_URL" data-branch 2>&1 | redact; then cloned=true; break; fi
    rm -rf data-branch
    (( try < 3 )) && sleep $(( try * 15 ))
  done
  if [[ $cloned != true ]]; then
    echo "WARNING: cannot reach the private data repository. Check the DATA_REPO_TOKEN secret and that" \
         "the repository $DATA_REPO exists. Readings stay in this run and are pushed once it works."
    git init -q -b main data-branch
    git -C data-branch remote add origin "$DATA_REPO_URL"
  fi
  DATA_BRANCH=$(git -C data-branch symbolic-ref --short HEAD 2>/dev/null || echo main)
}

setup_data_dir() {
  if [[ -n "${DATA_REPO_TOKEN:-}" ]]; then
    DATA_REPO=${DATA_REPO:-SandeshSatishhNaik/traffic-data-private}
    setup_private_repo
    echo "Data goes to the private repository (branch $DATA_BRANCH)."
  else
    setup_public_branch
    echo "No DATA_REPO_TOKEN: data goes to the public $DATA_BRANCH branch."
  fi
  git -C data-branch config user.name "traffic-collector"
  git -C data-branch config user.email "41898282+github-actions[bot]@users.noreply.github.com"
}

# Schedule (IST). The core stretches (the Outer Ring Road, both directions) are read at the times
# below: every 15 min in the two rush-hour windows, every 30 min around them, every 2 hours at
# night. The context stretches (roads around it, and the two long ones) at fewer times.
# segments.csv says which stretch belongs to which tier. All times are on the 15-minute slot grid.
# 32 core readings x 17 stretches + 13 context readings x 4 stretches = 596 TomTom requests a day,
# 18,476 in a 31-day month, inside the free 20,000 (collector/README.md has the table).
CORE_TIMES=" 0707 0737 0807 0822 0837 0852 0907 0922 0937 0952 1007 1037 1207 1407 \
1637 1707 1737 1807 1822 1837 1852 1907 1922 1937 1952 2007 2037 2207 0007 0207 0407 0607 "
CONTEXT_TIMES=" 0707 0807 0907 1007 1207 1407 1707 1807 1907 2007 2207 0207 0607 "

# Which tiers are due at this slot (HHMM, IST; default now), as a comma list ("" = none).
due_tiers() {
  local hm tiers=""
  hm=${1:-$(TZ=Asia/Kolkata date +%H%M)}
  [[ "$CORE_TIMES" == *" $hm "* ]] && tiers="core"
  [[ "$CONTEXT_TIMES" == *" $hm "* ]] && tiers="${tiers:+$tiers,}context"
  echo "$tiers"
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

# Incidents are polled every half hour (IST :07 and :37) and on a manual start, private mode only.
incidents_due() {
  [[ "${COLLECT_INCIDENTS:-true}" == "true" ]] || return 1
  # Incident data is only stored in the private repository, never on the public branch.
  [[ -n "${DATA_REPO_TOKEN:-}" ]] || return 1
  [[ ${1:-} == "force" ]] && return 0
  local m
  m=$(TZ=Asia/Kolkata date +%M)
  [[ $m == 07 || $m == 37 ]]
}

collect_once() {
  local inc="" tiers=""
  incidents_due "${1:-}" && inc="--incidents"
  [[ -n "${2:-}" ]] && tiers="--tiers $2"
  # A failed collection must not stop the chain; the next slot tries again.
  python3 collector/collect.py --segments collector/segments.csv --out data-branch/data $inc $tiers ${COLLECT_ARGS:-} || true
  (
    cd data-branch
    git add -A
    git diff --cached --quiet && exit 0
    git commit -q -m "Collect $(date -u +%Y-%m-%dT%H:%MZ)"
    { git push -q origin "HEAD:$DATA_BRANCH" 2>&1 || {
        git pull -q --rebase origin "$DATA_BRANCH" 2>&1 && git push -q origin "HEAD:$DATA_BRANCH" 2>&1
      }; } | redact || echo "Push failed; rows stay in this run and go out with the next push."
  )
}

setup_data_dir

if [[ "${COLLECT_NOW:-false}" == "true" ]]; then
  collect_once force
fi

while :; do
  slot=$(next_slot)
  (( slot > END )) && break
  wait_s=$(( slot - $(date -u +%s) ))
  (( wait_s > 0 )) && sleep "$wait_s"
  tiers=$(due_tiers)
  if [[ -n "$tiers" ]]; then collect_once "" "$tiers"; else echo "$(TZ=Asia/Kolkata date +%H:%M) IST: not a collection slot, skipped"; fi
done

if [[ "${NO_CHAIN:-false}" == "true" ]]; then
  echo "NO_CHAIN set: not starting the next run."
else
  gh workflow run "$WORKFLOW_FILE" --ref "${GITHUB_REF_NAME:?}" -f chained=true
  echo "Started the next run of $WORKFLOW_FILE."
fi
