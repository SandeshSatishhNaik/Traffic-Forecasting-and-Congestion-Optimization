# Hidden-road test (2026-11-26)

Can the graph model forecast a road it never saw in training? Each road below was hidden from training and validation, given the mean road embedding and a reference speed from one week of nights, then forecast on the test week from its own live readings. MAE in km/h, lower is better; same rows in each column. Hidden and seen models: mean forecast of the seeds.

Data: 33,849 readings, 21 stretches. Test week 2026-11-19 to 2026-11-25 (one week, one corridor). Seeds: 3. Script: `modeling/hidden_road.py`.

| Road | Horizon | Hidden (never seen) | Seen (normal model) | Same as now | Rows |
|---|---|---|---|---|---|
| orr_ccw_01 | +15 min | 1.68 (runs 1.86 ± 0.10) | 1.49 | 1.70 | 112 |
| orr_ccw_01 | +30 min | 1.93 (runs 2.00 ± 0.03) | 1.57 | 1.85 | 147 |
| orr_ccw_01 | +60 min | 2.05 (runs 2.13 ± 0.24) | 1.50 | 2.28 | 126 |
| orr_bellandur | +15 min | 5.74 (runs 5.76 ± 0.03) | 5.46 | 5.87 | 112 |
| orr_bellandur | +30 min | 6.61 (runs 6.63 ± 0.04) | 6.14 | 7.44 | 147 |
| orr_bellandur | +60 min | 6.94 (runs 6.97 ± 0.03) | 6.10 | 8.28 | 126 |
| orr_marathahalli | +15 min | 2.70 (runs 2.79 ± 0.30) | 2.13 | 2.55 | 112 |
| orr_marathahalli | +30 min | 4.65 (runs 4.67 ± 0.25) | 3.02 | 3.66 | 147 |
| orr_marathahalli | +60 min | 5.57 (runs 5.62 ± 0.04) | 3.74 | 5.44 | 126 |
| orr_cw_05 | +15 min | 2.49 (runs 2.53 ± 0.19) | 1.72 | 1.81 | 112 |
| orr_cw_05 | +30 min | 3.28 (runs 3.36 ± 0.11) | 2.31 | 2.77 | 147 |
| orr_cw_05 | +60 min | 3.85 (runs 3.88 ± 0.37) | 2.43 | 3.39 | 126 |
| hosur_bommanahalli | +15 min | nan (runs nan ± nan) | nan | nan | 0 |
| hosur_bommanahalli | +30 min | nan (runs nan ± nan) | nan | nan | 0 |
| hosur_bommanahalli | +60 min | 4.90 (runs 5.10 ± 0.33) | 4.93 | 5.43 | 49 |
| varthur_kundalahalli | +15 min | nan (runs nan ± nan) | nan | nan | 0 |
| varthur_kundalahalli | +30 min | nan (runs nan ± nan) | nan | nan | 0 |
| varthur_kundalahalli | +60 min | 1.24 (runs 1.44 ± 0.23) | 0.91 | 1.49 | 49 |

Average over the hidden roads:

| Horizon | Hidden | Seen | Same as now |
|---|---|---|---|
| +15 min | 3.15 | 2.70 | 2.98 |
| +30 min | 4.12 | 3.26 | 3.93 |
| +60 min | 4.09 | 3.27 | 4.38 |

Run time 544 s.

Notes:
- The two context roads (hosur_bommanahalli, varthur_kundalahalli) are read 13 times a day, so they have no
  +15/+30 min test rows; the +15/+30 averages cover the 4 ORR roads, the +60 average all 6.
- Reading: a never-seen road is worse than the same road in the normal model in 13 of 14 cases (gap 0.2-1.8 km/h, larger
  than the run spread; hosur_bommanahalli +60 min is a tie, 4.90 vs 4.93). Against "same as now" it is mixed: better on Bellandur (all horizons), Silk Board and both
  context roads at +60 min; worse on Marathahalli and orr_cw_05. So the method partly transfers, but a new road
  still needs its own data and a retrain before its forecasts can be trusted. One test week, one corridor.
