# Vehicle Counts: How to Handle Them

The Bengaluru collector records **speed and travel time**, not the number of vehicles. TomTom's Flow Segment service does not return counts.

## 1. The core project does not need counts

- Congestion = current speed ÷ free-flow speed. Both come from TomTom.
- Route recommendation needs travel time per road. It comes from TomTom.
- METR-LA and PEMS-BAY, the main benchmarks, are speed-only too.

So the main forecasting target is **speed**. Say this explicitly in the report.

## 2. Where counts come from, if you want them

| Source | What it gives | Cost | Use for |
|---|---|---|---|
| **PEMS04 / PEMS08** (benchmark) | Real vehicle **flow** per 5 min, plus occupancy and speed, 307 / 170 sensors | Free download | Show the model also forecasts vehicle counts |
| **Estimated flow from speed** (Bengaluru) | Vehicles/hour per road, calculated, not measured | Free, a few lines of code | A "vehicles per hour" figure on the Bengaluru dashboard, labelled as an estimate |
| **Short phone video + AI counting** (optional) | Real counts by vehicle type at one spot for the recorded time | 1–2 hours of recording from a footbridge | Checking the estimate, and vehicle mix (two-wheelers, autos, cars, buses) |
| TomTom Historical Traffic Volumes | Model-estimated volumes | Paid (contact sales) | Not needed |
| Bengaluru Traffic Police / IISc Mobility Challenge | Real junction counts / videos | Permission needed | Only if a request succeeds |

## 3. Estimating flow from speed (Greenshields model)

Classic traffic-flow theory relates speed, density and flow on a road:

```
density  k = kj × (1 − v / vf)          vehicles per km per lane
flow     q = k × v = kj × v × (1 − v / vf)   vehicles per hour per lane
total    Q = q × lanes
```

- `v` = current speed (TomTom `current_speed_kmph`)
- `vf` = free-flow speed (TomTom `free_flow_speed_kmph`)
- `kj` = jam density, the density at which traffic stops. Assume about 140 passenger-car units per km per lane for Indian urban roads, then calibrate it.
- `lanes` = lanes per direction, from the OpenStreetMap `lanes` tag

Example: free-flow 42 km/h, rush-hour speed 20 km/h, 3 lanes →
k = 140 × (1 − 20/42) ≈ 73 per km per lane, q ≈ 73 × 20 ≈ 1,470 per hour per lane, Q ≈ 4,400 per hour.

Limits:
- It is a model, not a measurement. Signal-controlled urban roads and mixed Indian traffic fit it only roughly.
- Units are passenger-car units (a bus counts as more than one car, a two-wheeler as less), not raw vehicle numbers.
- The value of `kj` changes the result proportionally. One short counted video on a road lets you fit `kj` for that road.

Always label these numbers "estimated vehicles/hour".

## 4. Optional: counting from a phone video

1. Record 30–60 minutes of a road from a footbridge or building, phone held still, during a rush hour.
2. Run a vehicle detector on the video. IISc's BMD-45 models were trained on Bengaluru CCTV with 14 Indian vehicle classes (Apache 2.0 licence). Add a tracker and a counting line across the road.
3. Output: vehicles per 5 minutes, by type.
4. Compare with the Greenshields estimate for the same road and time, and adjust `kj`.

Nobody counts by hand; the detector does the counting.
