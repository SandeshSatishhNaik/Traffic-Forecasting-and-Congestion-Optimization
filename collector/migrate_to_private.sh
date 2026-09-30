#!/usr/bin/env bash
# One-off: copy the data collected on the public bengaluru-data branch into the
# private data repository (under data/legacy/), check the row counts match, and
# optionally delete the public branch.
#
# Run by .github/workflows/migrate-data.yml. Run it only after the collection
# chain writes to the private repository (nothing new arrives on the public
# branch any more): deleting the branch earlier would lose the readings that
# are still being added to it.
#
# Env: DATA_REPO_TOKEN (required), DATA_REPO (default SandeshSatishhNaik/traffic-data-private),
#      PUBLIC_DATA_DIR (checkout of the bengaluru-data branch, default public-data),
#      DELETE_PUBLIC_BRANCH (true = delete it after the copy is verified),
#      STATUS_ONLY (true = only list what the private repository holds),
#      MIN_AGE_MINUTES (default 20: refuse to delete a branch written to more recently),
#      DATA_REPO_URL (override, for tests), DATA_BRANCH (default bengaluru-data).
set -euo pipefail

: "${DATA_REPO_TOKEN:?The DATA_REPO_TOKEN secret is not set.}"
DATA_REPO=${DATA_REPO:-SandeshSatishhNaik/traffic-data-private}
DATA_REPO_URL=${DATA_REPO_URL:-https://x-access-token:${DATA_REPO_TOKEN}@github.com/${DATA_REPO}.git}
PUBLIC_DATA_DIR=${PUBLIC_DATA_DIR:-public-data}
DATA_BRANCH=${DATA_BRANCH:-bengaluru-data}
export GIT_TERMINAL_PROMPT=0

redact() { sed -E 's#(https://)[^@/ ]+@#\1***@#g'; }

if [[ "${STATUS_ONLY:-false}" == "true" ]]; then
  # Health check: what is in the private repository (names and line counts, no values).
  rm -rf private-data
  git clone -q "$DATA_REPO_URL" private-data 2>&1 | redact
  echo "Latest commits in the private repository:"
  git -C private-data log --format='  %h %cd %s' --date=iso -5
  echo "Files:"
  (cd private-data && find data network -type f 2>/dev/null | sort | while read -r f; do echo "  $f: $(wc -l < "$f") lines"; done)
  exit 0
fi

[[ -d "$PUBLIC_DATA_DIR/data" ]] || { echo "No data folder in $PUBLIC_DATA_DIR."; exit 1; }
last_public=$(git -C "$PUBLIC_DATA_DIR" log -1 --format=%ct)
age_min=$(( ($(date +%s) - last_public) / 60 ))
echo "Newest reading on the public branch is $age_min minutes old."

rm -rf private-data
git clone -q --depth=1 "$DATA_REPO_URL" private-data 2>&1 | redact
git -C private-data config user.name "traffic-collector"
git -C private-data config user.email "41898282+github-actions[bot]@users.noreply.github.com"

mkdir -p private-data/data/legacy
cp -r "$PUBLIC_DATA_DIR"/data/. private-data/data/legacy/

bad=0
while IFS= read -r f; do
  rel=${f#"$PUBLIC_DATA_DIR"/data/}
  a=$(wc -l < "$f"); b=$(wc -l < "private-data/data/legacy/$rel")
  echo "  $rel: $a lines public, $b lines private"
  [[ "$a" == "$b" ]] || bad=1
done < <(find "$PUBLIC_DATA_DIR/data" -name '*.csv' | sort)
[[ $bad == 0 ]] || { echo "Row counts differ; nothing pushed."; exit 1; }

branch=$(git -C private-data symbolic-ref --short HEAD 2>/dev/null || echo main)
git -C private-data add -A
if git -C private-data diff --cached --quiet; then
  echo "Private repository already holds this data."
else
  git -C private-data commit -q -m "Copy the legacy data from the public branch ($(date -u +%Y-%m-%dT%H:%MZ))"
  { git -C private-data push -q origin "HEAD:$branch" 2>&1; } | redact
fi

# Verify from a fresh clone that the private copy is complete.
rm -rf verify-data
git clone -q --depth=1 "$DATA_REPO_URL" verify-data 2>&1 | redact
while IFS= read -r f; do
  rel=${f#"$PUBLIC_DATA_DIR"/data/}
  [[ "$(wc -l < "$f")" == "$(wc -l < "verify-data/data/legacy/$rel")" ]] || { echo "Verification failed for $rel"; exit 1; }
done < <(find "$PUBLIC_DATA_DIR/data" -name '*.csv' | sort)
echo "Verified: the private repository holds every public row."

if [[ "${DELETE_PUBLIC_BRANCH:-false}" == "true" ]]; then
  if (( age_min < ${MIN_AGE_MINUTES:-20} )); then
    echo "Not deleting the public branch: it was written to $age_min minutes ago, so the collection chain"
    echo "may still be using it. Switch the chain to the private repository first, wait, and run again."
    exit 1
  fi
  git push origin --delete "$DATA_BRANCH"
  echo "Deleted the public $DATA_BRANCH branch."
fi
