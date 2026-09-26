# Local Data: Bengaluru / Karnataka

Question: can the project use Bengaluru data instead of (or alongside) California benchmarks, so evaluators and mentors can relate to it? What data and which factors are needed?

Researched 2026-09-26. Re-check access terms before relying on any source.

---

## Short answer

- **There is no public, ready-to-download Bengaluru dataset like METR-LA** (fixed sensors, speed every 5 min, many locations, months long). Anything local has to be requested or collected.
- **A model trained on Los Angeles freeways cannot make predictions for Bengaluru roads.** Bengaluru traffic is different: mixed vehicles (two-wheelers, autos, buses), signal-controlled urban junctions, weak lane discipline, rain-driven waterlogging. For Bengaluru predictions you must train on Bengaluru data.
- **Recommended: two tracks.**
  1. **Benchmark track (METR-LA / PEMS-BAY):** proves the model is built correctly, because results can be compared with published papers.
  2. **Bengaluru pilot track:** your own collected data on one corridor, the same model retrained, and the dashboard and route recommendation shown on a Bengaluru map. This is the part evaluators will relate to.

## What the California data does and does not tell you

| Available in METR-LA / PEMS-BAY | Not available |
|---|---|
| Speed every 5 min per sensor | Road type, lanes, speed limit (PeMS raw metadata has lanes/direction; the benchmark files do not) |
| Sensor latitude/longitude | Vehicle mix (cars vs trucks vs two-wheelers) |
| Road distance between sensors | Signals, junction layout |
| | Weather, events, incidents, holidays (you add these yourself) |

So even with California data, the "factors" have to be joined in from other sources.

---

## Source inventory (Bengaluru)

| Source | What it gives | Time resolution | Access | Verdict |
|---|---|---|---|---|
| **Your own collection via TomTom Traffic Flow API** (Flow Segment Data) | `currentSpeed`, `freeFlowSpeed`, `currentTravelTime`, `confidence` for the road segment at a lat/lon | Whatever you poll (15–30 min) | Free tier: 20,000 Flow Segment requests/month (TomTom pricing page, Sept 2026). Read TomTom's terms on storing responses before building a dataset. | **Best practical route to real, multi-location, time-stamped Bengaluru data.** Only collects from the day you start, so start early. |
| **Bengaluru Mobility Challenge 2024** (BTP + IISc CDPG, on IEEE DataPort) | ~450 GB of video from 23 Safe City cameras around IISc, plus camera locations; task was 30-min-ahead vehicle-count forecasting by vehicle type | Continuous video | **Restricted to competition use and not to be made public.** Only possible by asking the organisers (hackathon.cdpg@fsid-iisc.in) for academic use. | Ideal fit if granted. Ask, but don't depend on it. |
| **BMD-45** (IISc AIM, CVPR Findings 2026) | 45,986 annotated CCTV frames from 3,679 Bengaluru cameras, 14 Indian vehicle classes; pretrained detectors | Still images (Feb 2025, daytime) | Public on Hugging Face, CC BY 4.0; models Apache 2.0 | Not a time series. Use its models to **count vehicles in videos you record**. |
| **UVH-26** (IISc AIM) | 26,646 annotated frames from ~2,800 Safe City cameras | Still images | Public on Hugging Face | Same use as BMD-45. |
| **Uber Movement archive** (Bangalore wards) | Ward-to-ward average travel times | Aggregated (hour of day / weekly), up to early 2020 | Uber Movement is no longer running; old CSVs survive in Kaggle notebooks/tutorials | Real but old and zone-level. Only for exploring zone-to-zone patterns. |
| **Kaggle "Bangalore's Traffic Pulse"** | Volume, speed, congestion per road per day; ~16 roads in 8 areas | **Daily**, 2022-01 to 2024-08 | CC0; no stated provenance | **Do not use as main data.** Daily values cannot show rush hours, and many columns pile up at hard caps (travel-time index 1.5 on ~58% of rows, capacity 100% on ~77%), which suggests synthetic or clipped data. An evaluator who checks will notice. |
| **OpenCity (data.opencity.in)** | BTP signal timing sheets for some junctions (PDF), traffic police jurisdictions, station locations | Static | Public | Road/junction context factors. |
| **OpenStreetMap (OSMnx)** | Full Bengaluru road network: roads, lengths, lanes (where tagged), speed limits, one-ways, points of interest | Static | Public (ODbL) | **Required** for the graph and routing. |
| **Open-Meteo** | Hourly rain and temperature, historical and forecast | Hourly | Free | **Required.** Rain is the biggest non-calendar factor in Bengaluru. |
| **TomTom Traffic Index** | City-level stats: 2025 average 36 min 9 s per 10 km, 74.4% congestion, 168 h lost per year | Yearly | Public | Use for the **problem motivation slide**, not training. |
| **Bengaluru Traffic Police / DULT / BBMP** | Junction counts, signal data, congestion reports | Varies | By request: college letter or RTI | Slow, but high credibility if it arrives. |

Other Karnataka cities (Mysuru, Hubballi-Dharwad, Mangaluru) have even fewer sources. Bengaluru is the realistic choice.

---

## Collection plan for the Bengaluru pilot

1. **Pick one corridor evaluators know.** Examples: Outer Ring Road (Silk Board → Marathahalli → KR Puram), Hosur Road (Silk Board → Electronic City), or the roads around your college. One corridor with side roads gives a connected graph, which the spatio-temporal model needs.
2. **Choose 12–14 road segments** along it and its alternatives (so routing has real choices).
3. **Poll TomTom Flow Segment Data every 30 minutes.** Budget: 13 segments × 48 polls/day × 30 days ≈ 18,700 requests, inside the 20,000/month free tier. Polling every 15 min halves the segments you can afford (about 6).
4. **Log each poll to a file:** `timestamp, segment_id, lat, lon, current_speed, free_flow_speed, travel_time, confidence, road_closure`.
5. **Log hourly weather** for the same area from Open-Meteo.
6. **Run for at least 4–6 weeks.** Each week is one more weekly cycle. Starting now also captures heavy-rain days and the Dasara/Deepavali festival season.
7. **Optional ground truth:** record 1–2 hours of peak traffic at one junction on a phone and count vehicles by class with a BMD-45 pretrained detector. Useful as a vehicle-mix factor and good demo material.
8. **In parallel, send data requests** to IISc CDPG (Mobility Challenge data) and BTP. A template is below.

---

## Data checklist

### Must have (minimum viable Bengaluru pilot)
- [ ] Traffic state time series per road segment (speed or travel time), fixed interval, 4+ weeks
- [ ] Segment locations (lat/lon) and segment IDs
- [ ] Road graph: which segments connect, and the distance between them (from OSM)
- [ ] Calendar: time of day, day of week, Karnataka public holidays
- [ ] Hourly rainfall
- [ ] Road network for routing (OSM via OSMnx)

### Should have (improves accuracy and gives evaluators better answers)
- [ ] Road attributes per segment: road class, lanes, speed limit, one-way, flyover/underpass
- [ ] Junction type and signal cycle where known (OpenCity / BTP)
- [ ] Events calendar: cricket matches at Chinnaswamy, big concerts, rallies at Freedom Park, festivals
- [ ] Incidents and closures (TomTom Incidents API or BTP advisories)

### Nice to have
- [ ] Vehicle mix at one or two junctions (video counts)
- [ ] Points of interest near each segment: tech parks, malls, schools, metro stations (OSM)
- [ ] Construction and diversion periods (metro works, road widening)
- [ ] Metro line opening dates (they cause before/after shifts in traffic)

---

## Factors that affect Bengaluru traffic, and how to feed them to the model

| Factor | Why it matters in Bengaluru | How to encode | Source |
|---|---|---|---|
| Time of day | Morning and evening peaks; the evening peak is usually the slowest | sin/cos of minute of day | Timestamp |
| Day of week | IT office days differ from weekends | one-hot or embedding | Timestamp |
| Public holidays, festivals | Traffic drops or shifts; shopping streets spike before festivals | 0/1 flags, days-to-festival | Karnataka holiday list |
| Rain | Waterlogging collapses speeds on specific roads | mm in the last hour, 0/1 heavy-rain flag | Open-Meteo |
| Neighbouring roads | Jams spread along corridors and into side roads | Road graph (adjacency matrix) | OSM + segment list |
| Road class, lanes, speed limit | Sets capacity and normal speed | categorical + numeric per node | OSM |
| Signals and junction type | Signal cycles create stop-go patterns | static node features | OpenCity / BTP |
| Events | Stadium and venue traffic | 0/1 flag with distance to venue | Event calendars |
| Incidents, closures | Sudden unpredictable drops | 0/1 flag per segment | TomTom Incidents / BTP |
| Construction | Long-term capacity loss | date-range flag per segment | News, BMRCL/BBMP notices |
| Vehicle mix | Two-wheelers and autos behave differently from cars | share per class | Video counts |
| Land use nearby | Tech parks, schools, markets set peak shapes | counts of points of interest within 500 m | OSM |

Start with **time, day, holidays, rain and the road graph**. Add the others one at a time and keep only those that measurably reduce error.

---

## Data request email template

> Subject: Request for traffic data access for an academic project (<College name>)
>
> Dear <CDPG team / Sir or Madam>,
>
> We are <year> students at <College>, <Department>, working on an academic project titled "AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic Forecasting and Congestion Optimization", guided by <Guide name, designation>.
>
> We would like to request access to <the Bengaluru Mobility Challenge 2024 camera videos / junction-level vehicle count data for <area>> for non-commercial academic use only. We will not publish the raw data, will not attempt to identify individuals, and will acknowledge <organisation> in our report and any publication.
>
> A letter from our Head of Department is attached. We would be glad to share our results with you.
>
> Regards,
> <Names, roll numbers, contact>

Send from the guide's or department's official email where possible; requests from faculty get answered more often.
