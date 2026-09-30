# Road Network, Connections and Extra Factors

Question from the team: the collector gathers spatio-temporal data, but how are the roads, junctions and traffic signals connected, and what should improve in the collection?

Analysis date: 2026-09-29. Data used: 141 collection runs (27 Sep 12:01 IST to 29 Sep 22:07 IST), 10 road stretches, ~1,400 readings, plus one diagnostic run on 29 Sep (section 8).

This note holds summary numbers only, not raw TomTom results (see section 4 for why that matters).

---

## 1. What the first 10 "roads" really were

Each collected road is one **TomTom road stretch**: the piece of road TomTom's Flow Segment service matched to the point we asked about. TomTom returns the stretch's shape, so its length is the length of that polyline (section 8).

| Segment | Length | Heading | Note |
|---|---|---|---|
| orr_hsr | 0.7 km | west | ORR toward Silk Board |
| orr_iblur | 2.0 km | north-east | ORR eastbound |
| orr_bellandur | 0.7 km | north-east | starts exactly where orr_iblur ends |
| orr_marathahalli | 3.9 km | south | ORR, toward Silk Board |
| orr_doddanekundi | 7.4 km | north | ORR northbound, runs beside the two southbound segments |
| orr_mahadevapura | 4.3 km | south-east | ends exactly where orr_marathahalli starts |
| hosur_bommanahalli | 0.65 km | north-west | |
| sarjapur_agara | 1.0 km | north-east | **not Sarjapur Road**: TomTom matched the ORR eastbound near Agara (correction of 30 Sep, section 9); starts about 10 m from where orr_hsr starts, so the two are the two carriageways of the ORR at one junction |
| old_airport_konena | 14.7 km | west | Varthur Rd / Old Airport Rd, inbound |
| varthur_kundalahalli | 14.6 km | east | the same 15 km road, outbound |

(Estimating length as free-flow speed times free-flow travel time comes out 2% to 21% too short, because the free-flow speed is noisy; the polyline length is the reliable one.)

Findings from the stored data:

- **Lengths differ about 22 times** (0.65 km to 14.65 km). One number for a 14 km stretch averages many junctions and signals together: OpenStreetMap shows 64 traffic signals along the westbound one and 63 along the eastbound one.
- **Two of the ten are the same road in opposite directions** (Old Airport Rd and Varthur Rd).
- **The ORR points alternate direction.** Iblur, Bellandur and Doddanekundi are outbound; HSR, Marathahalli and Mahadevapura are inbound. A road divided into two carriageways is two separate roads for traffic purposes and must be two graph nodes.
- **Six islands** (groups of stretches that touch each other; the two directions of the 15 km road are counted as one): (1) HSR + "Sarjapur" (the two ORR carriageways at one junction), (2) Iblur to Bellandur, (3) Mahadevapura to Marathahalli, (4) Doddanekundi, which runs beside island 3 the other way, (5) Hosur Rd, (6) Old Airport + Varthur.
- **Only three real links exist in the data:** Iblur to Bellandur, Mahadevapura to Marathahalli, and HSR + "Sarjapur" at one junction (opposite carriageways of the ORR).
- **Gaps where nobody measures anything.** Straight-line distances between neighbouring islands: 0.16 km (Doddanekundi end to Mahadevapura start), 0.55 km (Marathahalli end to Doddanekundi start), 0.9 km (Bellandur end to Marathahalli end), 1.2 km (HSR end to Hosur Rd end), 2.7 km (HSR start to Iblur start).
- The collector stores only start and end coordinates per stretch, not the road's shape, and nothing about junctions, signals, lanes or road type.

## 2. Are the roads connected in the data? No

Nothing in the stored files says which stretch leads into which. In the physical world they are connected (they meet at Silk Board, Agara, Marathahalli and so on). The connections have to be added from a road map.

Weak evidence that structure exists: the jam reaches the roads in the same order on both weekdays observed (Mon 28, Tue 29 Sep). First slot below 50% of normal speed, morning:

| Road | Mon | Tue |
|---|---|---|
| Iblur | 08:07 | 07:37 |
| Sarjapur Rd | 07:52 | 07:52 |
| Bellandur | 08:07 | 08:07 |
| Mahadevapura | 08:37 | 08:22 |
| Hosur Rd | 08:52 | 08:37 |
| Marathahalli | 08:52 | 09:07 |
| HSR | not below 50% | 09:52 |

Correlation between roads does **not** yet reveal reliable links: raw correlations mostly reflect that everything slows at rush hour (correlation vs distance apart is only -0.29 after two weekdays). Links must come from the map first; statistics can refine them after several weeks.

## 3. How roads, junctions and traffic signals get connected

Use the standard construction from the traffic-forecasting literature (DCRNN uses thresholded road-network distance; Graph WaveNet adds a learned adjacency and found it performs similarly to the distance-based one).

1. **Nodes = road stretches** (what we measure). A two-way road is two nodes.
2. **Match each stretch to the OpenStreetMap road graph.** Use the stretch's stored shape, or its OpenLR code (TomTom returns one for free with `openLr=true`; it came back in 80 of 80 test responses), to find the OSM roads it covers. OSM supplies the junction nodes at the two ends of every stretch and the roads between them.
3. **Link A to B if a car can drive from A into B**, within a chosen driving distance. Link weight = `exp(-(distance/sigma)^2)`, dropped below 0.1. Links are directed. Gaps between measured stretches get their real road distance, so islands connect through the unmeasured road.
4. **Junction notes on each link and node** (not extra nodes): number of legs at the junction, whether it is signalised, roundabout or flyover/underpass.
5. **Signals as features:** number of OSM `highway=traffic_signals` nodes on the stretch, signals per km, distance from the stretch end to the next signal. Signal timing plans are not public for this corridor (BTP publishes PDF timings for a few other junctions on OpenCity), so the model learns their effect from the speeds.
6. **Learned adjacency** (Graph WaveNet style) as a supplement, to catch links the map does not show.

Caveat: with only 10 nodes the graph matters less than data volume. STID (CIKM 2022) showed that node identity embeddings plus time of day rival graph models.

## 4. TomTom licence: read this first

This is a reading of the terms, not legal advice. TomTom's Maps API terms (https://docs.tomtom.com/legal/terms-and-conditions), quoted:

- **11.4** "The caching or storing of any Results shall be prohibited except that you may cache Results ... only in clients where the control headers are present ... must not be cached ... longer than the maximum age period indicated in such cache control headers."
- **11.6.1** You shall not "use the Licensed Products ... to create any derivative work, product or service ... or use the content ... for the creation of any secondary or derived database populated wholly or partially with your data".
- **11.6.4** No use "in connection with any machine learning, AI algorithm ... where the Licensed Products or any information contained ... would be stored or retained in any Public Reference Data Set", defined as "any data set from which a machine learning, AI algorithm ... may generate results ... for delivery to queries made by parties other than the You."
- **Definitions:** "Evaluation Use" means "internal evaluation and testing by you of the Licensed Products." No exception for academic or student use was found in the terms page.

What this means for the project:

- The `bengaluru-data` branch stores TomTom results, and the repository is **public**. That conflicts with 11.4 and 11.6.1 as written, and a dashboard that serves predictions to other people trained on stored data is what 11.6.4 describes.
- Earlier advice in this project to keep the repository public (to keep GitHub Actions minutes free) was given before this wording was read. It should be reversed for the data.
- Practical risk to a student project is likely low; public redistribution is the part that is visible.
- Keeping the data private limits exposure but is still storing. Only TomTom's written permission removes the conflict with 11.4.

Options, roughly from least to most work:

1. **Get the data out of public view and ask TomTom in writing for permission** to store results for academic research. Keep collecting meanwhile (missing weeks cannot be recovered). Two ways to do the first half:
   - Keep this repository public for the code and the free Actions minutes, and have the collector push the data to a separate **private** repository (needs one fine-grained access token from the repository owner, stored as a secret). The public run logs only print counts such as "22:07 IST: 10/10 segments ok", never speeds.
   - Make this repository private and run the collector somewhere else (see the constraint below).
2. Publish code, models and METR-LA / PEMS-BAY results; keep the Bengaluru TomTom dataset private and report only aggregate results, with the source and licence limits stated in the report.
3. Replace the Bengaluru data source: own video counts (BMD-45 detectors), or a partner dataset from Bengaluru Traffic Police / IISc under an agreement.

Constraint discovered: GitHub's cron scheduler is unreliable on this repository (over three days it started about 5 of the 8 expected 3-hourly runs, delayed by up to 2.5 hours), so collection cannot simply move to short scheduled jobs. The self-chaining run works but needs public-repository free minutes (about 43,000 minutes a month; a free private repository gets 2,000). A private repository therefore needs the collector to run somewhere else (for example a Cloudflare Worker cron trigger, or a small always-on machine).

## 5. Data-quality findings from the collected data

- **Free-flow speed is not constant.** Per-reading "free-flow" speed for the same stretch ranges up to 30% (Iblur 37 to 47 km/h, Sarjapur 33 to 43), with almost no relation to time of day. Dividing current speed by the reported free-flow speed therefore adds noise. **Use a fixed reference per road** (for example the 95th percentile of its night-time speed) when computing congestion.
- **Current speed is capped at free-flow** when the road is empty, so speeds above normal are never seen.
- **`confidence` was 1.0 in every reading**, so it carries no information here.
- **Rain feature is weak so far:** maximum 0.9 mm/hour, only 4 readings at or above 0.5 mm, 74 of 141 readings show 0.1 to 0.3 mm of drizzle from the model. Use thresholds (for example at least 1 mm per hour) rather than "any rain".
- **Coverage is continuous:** 141 runs with no unexpected gap; the only long gaps are the one-off schedule changes.

## 6. Improvements, ranked

1. **Turn the 10 points into one connected network.** Walk the road: request a stretch, take its end coordinate, step about 30 m ahead along the road, request again. Repeat from Silk Board to KR Puram in both directions. The stretches then tile the road with no gaps, and each one's end is the next one's start, so the links come for free. Stretch lengths cannot be chosen (0.65 to 14.65 km today), so expect uneven pieces.
2. **Do not expect finer stretches from `zoom`.** A higher zoom returns the same stretch (section 8.1). Where a stretch is too long (Old Airport Rd: 14.7 km with 64 signals), the only finer source seen so far is the vector flow tiles (item 7).
3. **Store each stretch's shape and OpenLR code once** (a small static file, not with every reading). That is what lets us match it to OSM and draw it on a map.
4. **Use a fixed reference speed per road** in preprocessing (section 5).
5. **Add static road features from OpenStreetMap** (free): road class, lanes, speed limit, one-way, signals on the stretch and per km, distance to the next signal, junction type, flyover/underpass.
6. **Add incidents** as event flags. TomTom reports them for Bengaluru (section 8.4). Every 30 minutes is about 1,500 requests a month (the collector polls at 24 of its readings a day, about 750 a month).
7. **Vector flow tiles for coverage**, if the licence question is settled: 12 requests returned 688 connected road pieces with speeds (section 8.3), against 10 roads for 10 requests today.
8. **Weather with thresholds** (at least 1 mm per hour counts as rain), at more than one point. Rain in Bengaluru is patchy, and one point in the middle of the corridor cannot tell Silk Board from KR Puram.

Status on 30 Sep 2026: 1 done (section 9), 2 confirmed, 3 done as far as possible (shape and OpenLR code are saved in the private repository once the token exists), 4 not yet (preprocessing step), 5 done, 6 done (incidents are polled and stored only in the private repository), 7 and 8 not done.

## 7. Extra factors to record

| Factor | Type | Why it matters here | Source | Status |
|---|---|---|---|---|
| Speed, travel time | dynamic | the target | TomTom | collected |
| Rain amount | dynamic | flooding and waterlogging slow specific roads | Open-Meteo | collected, needs thresholds |
| Incidents, closures | dynamic | sudden unpredictable drops | TomTom incidents | not yet |
| Time of day, weekday | calendar | rush hour shape | timestamp | derive |
| Karnataka public holidays, festivals, school holidays | calendar | changes commute patterns | holiday list | not yet |
| Metro construction, lane closures, diversions | event | Namma Metro Blue Line (Silk Board to KR Puram) is under construction along the ORR, opening planned between Dec 2026 and Jun 2027; expect a traffic regime change at opening | news, BMRCL notices | note dates by hand |
| Special events, bandhs, strikes | event | one-off jams | news, event calendars | by hand |
| Road class, lanes, speed limit, one-way | static | capacity and normal speed | OSM | not yet |
| Traffic signals on the stretch, distance to next signal | static | stop-go delay | OSM | not yet |
| Junction type (legs, roundabout, flyover) | static | conflict points | OSM | not yet |
| Nearby land use: tech parks, schools, malls, metro stations | static | shapes peaks | OSM points of interest | not yet |
| Upstream and downstream speeds | derived | jams move along roads | from the graph | derive |
| Signal timing plans | dynamic | Bengaluru has 405 signalised junctions, 169 on adaptive control (BATCS, April 2025) | not public | unavailable |

A forecaster may only use inputs that will be known at forecast time: calendar, scheduled works and events, and the weather *forecast*. Incidents and neighbours' current speeds are known only for the past window, so they help the first minutes of a forecast, not the next hours.

Bengaluru context: 405 signalised junctions in the city, 32 with camera-based adaptive signals and 28 under DULT's MODERATO project; BATCS was deployed at 169 junctions by April 2025 (news reports). The Bengaluru police chief has inspected traffic-prone ORR junctions at Bellandur, Devarabeesanahalli, Marathahalli and KR Puram.

## 8. Diagnostic results

One workflow run (`collector/diagnose.py`, `.github/workflows/diagnose-network.yml`) on 29 Sep 2026, about 22:52 to 22:55 IST, using about 100 TomTom requests. Tiles and incidents are a single late-evening snapshot.

### 8.1 Does a higher `zoom` return shorter road stretches? No

The matched stretch was identical at zoom 8, 10, 12, 14, 16, 18, 20 and 22 for nine of the ten segments (lengths in section 1). The tenth, `sarjapur_agara`, is a warning: at zoom 8 and 10 it matched the 1.02 km main-road stretch (FRC1), but from zoom 12 up it snapped to a different 4.01 km minor road (FRC5, (12.9295, 77.6150) to (12.9245, 77.6501)). Keep `zoom=10`.

The OpenLR code came back in 80 of 80 responses, so matching stretches to OSM is possible without extra cost.

### 8.2 Traffic signals in OpenStreetMap

Corridor box 12.899 to 13.010 N, 77.609 to 77.755 E: 389 nodes tagged `highway=traffic_signals`, plus 183 separate pedestrian-crossing signals. Signals within 30 m of each stretch:

| Segment | Length | Signals | Per km | Nearest signal from start / end |
|---|---|---|---|---|
| orr_hsr | 0.71 km | 4 | 5.6 | 314 m / 261 m |
| orr_iblur | 1.97 km | 7 | 3.5 | 15 m / 317 m |
| orr_bellandur | 0.71 km | 2 | 2.8 | 317 m / 296 m |
| orr_marathahalli | 3.88 km | 4 | 1.0 | 1,216 m / 294 m |
| orr_doddanekundi | 7.38 km | 4 | 0.5 | 215 m / 379 m |
| orr_mahadevapura | 4.25 km | 0 | 0.0 | 218 m / 1,216 m |
| hosur_bommanahalli | 0.65 km | 0 | 0.0 | 266 m / 342 m |
| sarjapur_agara | 1.02 km | 6 | 5.9 | 306 m / 295 m |
| old_airport_konena | 14.65 km | 64 | 4.4 | 558 m / 13 m |
| varthur_kundalahalli | 14.62 km | 63 | 4.3 | 7 m / 536 m |

- Six of the ten stretches have about 3 to 6 signals per km, so signals are a real feature of these roads.
- Only 3 of the 20 stretch ends sit within 20 m of a signal. Stretch boundaries are **not** junctions: for most stretches the nearest signal is 200 to 1,200 m from the start or end. Junction and signal information has to come from OSM, not from TomTom.
- Caveats: OSM may miss signals (0 on a 4.25 km stretch of the ORR could be a gap in the map or a signal-free road), and on divided roads a signal on the opposite carriageway can fall inside the 30 m band, so per-km values are upper estimates.

### 8.3 Vector flow tiles: what one request contains

- Zoom 13: 4 by 3 = 12 tiles cover the whole corridor box (zoom 14 needs 42).
- Those 12 tiles hold 688 road pieces (31 to 79 per tile), all in one layer, "Traffic flow".
- Each piece carries `traffic_level`, `road_type`, `road_closure`, `traffic_road_coverage` and `left_hand_traffic`.
- Road categories: 350 local roads (major local, minor local, local), 132 connecting, 105 major, 52 international, 49 secondary.
- In the absolute style `traffic_level` is a speed in km/h (0 to 65, median 25, 15 distinct values); in the relative style it is a 0 to 1 fraction (median 0.76).
- Not tested: whether the piece geometries share end points, which would give the road connections directly.

### 8.4 Incidents

53 incidents in the corridor at test time: 32 road closed, 20 jam, 1 road works. Delay magnitude: 32 undefined (closures), 8 major, 11 moderate, 1 minor, 1 unknown. TomTom does report incidents for Bengaluru, but a call returns only the current snapshot, so a history exists only if we poll.

## 9. The connected corridor (built 30 Sep 2026)

`collector/build_network.py` (workflow "Build road network") walked the road with TomTom Flow Segment requests: ask for the stretch under a seed point, step 30 m past its far end along the road, ask again. About 50 requests gave a gap-free chain in each direction of the ORR. The result is in `collector/segments.csv` (the stretches to collect), `collector/network/links.csv` (which stretch leads into which), `collector/network/features.csv` (OpenStreetMap features) and `collector/network/legacy_ids.csv`.

| Route | Stretches | Length | What it is |
|---|---|---|---|
| orr_ccw | 8 | 19.4 km | ORR counter-clockwise (Silk Board, HSR, Agara, Iblur, Bellandur, Doddanekundi, Marathahalli, Mahadevapura to KR Puram); the first stretch runs 2.6 km west of the Silk Board junction |
| orr_cw | 9 | 16.6 km | ORR clockwise, the same road the other way, KR Puram to Silk Board |
| hosur | 2 | 8.6 km | Hosur Road: the old 0.65 km stretch and the 7.9 km stretch north of Silk Board |
| old_airport, varthur | 1 each | 14.6 km each | the two long stretches of Old Airport / Varthur Road, kept as alternatives to the ORR |

- **Links:** 16 directed `flow` links (7 + 8 along the ORR, 1 on Hosur Road) and 5 `crossing` records (Hosur Road crosses the ORR at Silk Board; Old Airport and Varthur Road each cross two ORR stretches at Marathahalli). Two ends do not match exactly (45 m at orr_ccw_04 to orr_iblur, 18 m at orr_cw_05 to orr_cw_06): small geometry mismatches, not missing road.
- **The two ORR directions are two separate chains.** No link joins them. If the model should see that both carriageways share weather and events, add a link between stretches that run side by side in opposite directions.
- **Correction of the first list:** `sarjapur_agara` was not Sarjapur Road. The walk shows it is the ORR eastbound near Agara (`orr_ccw_03`); OpenStreetMap's Sarjapur Road there (way 631197942, a one-way dual carriageway) is a different road. Its history is now `orr_ccw_03` (`legacy_ids.csv`). Sarjapur Road is not covered yet; it needs a seed point on it, away from the ORR.
- **Dropped:** a 20 km stretch the Sarjapur walk found (FRC3) and the two Hosur Road stretches south of Bommanahalli (14.5 km and 8.8 km): too long and too far from the ORR.
- **Stretch lengths are still uneven:** 0.65 km to 14.6 km. The ORR pieces are 0.7 to 7.4 km.

OpenStreetMap features, in the corridor box (`features.csv` has all columns):

- The corridor box holds 816 traffic-signal nodes and 4,024 points of interest (schools, hospitals, malls, offices, bus stops, metro).
- The ORR has 3 lanes per direction and mostly a 60 km/h limit (40 km/h near Marathahalli and Mahadevapura, 30 km/h on one short stretch), and is tagged one-way on both carriageways.
- **Signals are concentrated between Silk Board and Agara:** 5 to 10 per km on orr_ccw_01, orr_ccw_02, orr_cw_06, orr_cw_07 and orr_hsr. North of Marathahalli the ORR has none (orr_mahadevapura 0, orr_doddanekundi 0.5 per km); orr_cw_03 also has none. Hosur Road north of Silk Board has 7.9 per km, Old Airport and Varthur Road 4.3 to 4.4. Counts include signals on the opposite carriageway and pedestrian-crossing signals, so per-km values are upper estimates.
- Intersections (nodes where 3 or more roads meet) run 5 to 13 per km on every stretch.
- Offices are the most common point of interest along the ORR (up to 64 within 300 m of orr_ccw_01), which fits its use by commuters to the tech parks.

Schedule and budget: the ORR stretches are read at 32 times a day (every 15 minutes in the windows 08:07 to 10:07 and 17:37 to 20:07, every 30 minutes around them, every 2 hours at night) and the four context stretches at 13 times: 596 requests a day, 18,476 in a 31-day month against the free 20,000. Incidents are polled at the readings that fall on :07 and :37 (24 times a day, about 744 requests a month against the free 2,500) into an event log, in the private repository only. TomTom's incident request accepted the fields the collector asks for (checked 30 Sep; 229 incidents were active in the corridor box at 10:08 IST).

Open items: store each stretch's shape and OpenLR code in the private repository (needs the token), Sarjapur Road, and a script that turns `links.csv` into the adjacency matrix for the models.

