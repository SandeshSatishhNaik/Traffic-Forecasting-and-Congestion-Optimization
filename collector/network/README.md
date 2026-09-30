# Road network of the collected stretches

Written by `collector/build_network.py` (workflow **Build road network**, run on 30 Sep 2026). It describes how the stretches in `collector/segments.csv` connect. It holds no traffic readings and no TomTom shapes: the shape and OpenLR code of each stretch are TomTom results and are kept only in the private data repository (`network/stretches.json`).

| File | Content |
|---|---|
| `links.csv` | `flow` = a vehicle can drive from the end of `from_id` into the start of `to_id` (the graph edges, directed); `crossing` = the two stretches cross at that point (a junction between two roads). `gap_m` is the distance between the two ends (flow) or the closest approach (crossing); `lat`, `lon` place the link. |
| `features.csv` | OpenStreetMap features per stretch (© OpenStreetMap contributors, ODbL): road class, lanes, speed limit, one-way, bridge and tunnel share, traffic signals (count, per km, distance from each end to the nearest signal), intersections (nodes where 3 or more roads meet), counts of schools, hospitals, malls, offices, bus stops and metro stations within 300 m. |
| `legacy_ids.csv` | Ids of the first ten segments that changed. `sarjapur_agara` was labelled Sarjapur Road, but TomTom matched the Outer Ring Road eastbound, so it is `orr_ccw_03` now. |

Notes for using them:

- Signal counts include signals on the opposite carriageway and pedestrian-crossing signals within 30 m of a stretch, so per-km values are upper estimates. OpenStreetMap may miss signals.
- A `flow` link with a `gap_m` above 0 (a few tens of metres) is a small mismatch between neighbouring stretch ends, not a missing road.
- `crossing` rows join a long stretch to every ORR stretch it crosses at a junction (for example Old Airport Road and Varthur Road at Marathahalli); they are not directed and do not say which turns are allowed.
- Sarjapur Road itself is not in the network yet.
