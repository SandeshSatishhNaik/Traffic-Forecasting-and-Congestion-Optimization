# Alternative roads (for real route choice)

**Status: built and checked, not collected yet.** `segments.csv` and `loop.sh` are unchanged, so the live
collection is exactly as before.

## Why

The route planner (`modeling/routing.py`) compares the Outer Ring Road with an assumed alternative.
A real choice needs real parallel roads with their own measured speeds: Sarjapur Road, Whitefield /
ITPL Road and Old Madras Road. Their stretches are tier `alt`.

## What was done

1. `python3 collector/build_network.py --alt` (workflow *Build road network*, tick **alt**) walks the
   new roads with TomTom, adds OpenStreetMap features, and prints `VERIFY OK/CHECK` per stretch:
   does the OpenStreetMap road under the stretch have the name we expected? A `CHECK` means a wrong
   seed point; fix the seed in `ROUTES_ALT` and run again. Output files carry the suffix `_alt`.
2. `python3 collector/quota_plan.py N` checks the monthly TomTom requests. The free tier is 20,000.
   The live schedule uses 18,476, so there is room for **at most 12 alt stretches** only if the
   schedule is trimmed (below). 16 stretches would be 21,080: over.

## Proposed schedule (what `quota_plan.py` checks)

| Tier | Stretches | Readings/day | Requests/day |
|---|---|---|---|
| core (ORR) | 17 | 28 (drops 00:07, 04:07, 14:07, 20:37) | 476 |
| context | 4 | 11 (drops 14:07, 22:07) | 44 |
| alt | up to 12 | 10 (08:07 08:37 09:07 09:37 12:07 17:37 18:07 18:37 19:07 02:07) | 120 |
| total | | | 640 -> 19,840 a month |

The night reference speed is still measured at 22:07, 02:07 and 06:07, so the free-flow reference is
unaffected.

## To switch on (after the Phase 2 presentation)

1. Append the verified rows (`OK` only, at most 12) of `segments_alt.csv` to `segments.csv`.
2. In `loop.sh` replace `CORE_TIMES` and `CONTEXT_TIMES` by the trimmed lists and add
   `ALT_TIMES`, plus an `alt` line in `due_tiers`. In `run_local.py` do the same.
3. Run `python3 collector/quota_plan.py <N>` and the loop self-test; push.
4. The default branch is the working branch, so the chain picks this up at its next restart.

## What this does not give you yet

Collection can start, but route choice between these roads can only be **evaluated** after a few weeks
of history (the current models needed about a month). Until then the planner still uses the assumed link.
