# Alternative roads (for real route choice)

**Status: first build run, result NEGATIVE. Not ready to collect.** `segments.csv` and `loop.sh` are
unchanged, so the live collection is exactly as before.

## First verification run (GitHub Actions, 64 TomTom requests)

5 of 13 stretches matched the expected road name; the rest were wrong seeds or unnamed side roads.
The ones that matched are almost all far too long for route choice:

| Stretch | OpenStreetMap road | Length | Usable? |
|---|---|---|---|
| sarjapur_w_02 | Sarjapura Road | 16.2 km | coarse; one number for the whole road |
| whitefield_03 | Whitefield Road | 13.9 km | too coarse |
| old_madras_03 / _05 | Old Madras Road | 19.6 / 23.1 km | too coarse |
| old_madras_04 | Old Madras Road | 0.1 km | too short to matter |
| sarjapur_w_03/04, whitefield_01 | Outer Ring Road | 0.2-1.0 km | the walk strayed back onto the ORR |
| sarjapur_e_*, whitefield_02, old_madras_01 | no OSM name | | wrong seed or a side street |

Why: TomTom cuts a road into its own traffic segments. Highways and main roads come back as one long
segment, and we cannot cut them shorter. So seeds picked from memory are not enough. Next step: pick
2-3 points per road on a **short, busy** piece (Google Maps: right-click, copy coordinates), put them in
`ROUTES_ALT`, run the build again and keep only stretches that print `VERIFY OK` and are under about 5 km.
The build also tried to save geometry in the private data repository and got HTTP 403, the same
`DATA_REPO_TOKEN` permission problem as the migration (token needs Contents read/write on that repo).


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
