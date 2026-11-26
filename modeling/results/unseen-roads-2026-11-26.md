# Unseen roads (2026-11-26)

What can the graph model say about a road it never saw? For each of the road stretches below, the GCN was trained with that road hidden completely (no readings in training or validation) and given the mean road embedding. Test week 2026-11-19 to 2026-11-25 (one week, one corridor), 2 seeds per road and horizon, mean forecast of the seeds. Error = mean absolute error in **percentage points of the road's normal speed** (lower is better), identical rows within each case. Script: `liveapp/train_unseen.py`.

- **New sensor**: the road has just started sending readings (its own last readings are inputs; normal speed from one week of nights).
- **No sensor**: the road is never measured; the forecast comes only from the connected roads through the graph (virtual sensor). *GCN virtual sensor*: the hidden model's own forecast for the blank road (trained with one random known road blanked per extra sample). *Neighbours' GCN forecast*: average of the same model's forecasts for the road's graph neighbours. Baseline *neighbours now*: their current speed ratio.

## Average over the roads

| Horizon | No sensor: GCN virtual sensor | No sensor: neighbours' GCN forecast | No sensor: neighbours now | New sensor: GCN | New sensor: same as now | Normal model (saw the road) |
|---|---|---|---|---|---|---|
| +15 min (20 roads) | 14.3 | 13.2 | 14.4 | 8.9 | 8.1 | 7.6 |
| +30 min (20 roads) | 13.3 | 12.6 | 14.0 | 10.3 | 9.8 | 8.4 |
| +60 min (21 roads) | 13.2 | 12.0 | 14.2 | 10.8 | 10.6 | 8.2 |

## Per road (+60 min)

| Road | No sensor: GCN | Neighbours' forecast | Neighbours now | New sensor: GCN | Same as now | Normal model | Rows (new / none) |
|---|---|---|---|---|---|---|---|
| hosur_02 | 10.1 | 10.3 | 13.7 | 7.7 | 7.3 | 4.5 | 49 / 49 |
| hosur_bommanahalli | 14.4 | 13.1 | 13.9 | 13.3 | 13.6 | 12.4 | 49 / 49 |
| old_airport_konena | 8.2 | 6.7 | 10.8 | 6.8 | 5.2 | 2.3 | 49 / 49 |
| orr_bellandur | 15.6 | 13.3 | 15.5 | 13.8 | 16.9 | 12.4 | 126 / 126 |
| orr_ccw_01 | 7.7 | 8.2 | 11.0 | 6.9 | 8.1 | 5.3 | 126 / 126 |
| orr_ccw_02 | 17.2 | 20.2 | 17.7 | 13.4 | 5.4 | 12.2 | 126 / 126 |
| orr_ccw_03 | 21.1 | 18.1 | 21.0 | 15.3 | 16.3 | 11.1 | 126 / 126 |
| orr_ccw_04 | 16.4 | 10.5 | 12.2 | 13.4 | 12.2 | 8.7 | 126 / 126 |
| orr_ccw_07 | 11.0 | 9.8 | 10.3 | 8.2 | 9.3 | 7.4 | 126 / 126 |
| orr_cw_03 | 15.5 | 13.2 | 14.4 | 12.1 | 14.5 | 9.7 | 126 / 126 |
| orr_cw_04 | 16.9 | 14.9 | 13.3 | 15.3 | 12.5 | 9.8 | 126 / 126 |
| orr_cw_05 | 10.7 | 10.3 | 11.1 | 8.7 | 8.1 | 5.8 | 126 / 126 |
| orr_cw_06 | 14.1 | 15.2 | 17.3 | 11.1 | 12.1 | 11.0 | 126 / 126 |
| orr_cw_07 | 12.8 | 13.3 | 14.4 | 11.6 | 9.6 | 8.6 | 126 / 126 |
| orr_cw_09 | 9.9 | 11.6 | 17.9 | 9.3 | 11.6 | 9.2 | 126 / 126 |
| orr_doddanekundi | 6.2 | 5.5 | 9.4 | 5.5 | 6.5 | 5.5 | 126 / 126 |
| orr_hsr | 16.7 | 12.6 | 15.8 | 13.8 | 13.0 | 9.7 | 126 / 126 |
| orr_iblur | 17.5 | 12.8 | 16.3 | 12.3 | 12.6 | 8.1 | 126 / 126 |
| orr_mahadevapura | 10.9 | 11.9 | 16.9 | 8.8 | 9.9 | 7.1 | 126 / 126 |
| orr_marathahalli | 18.0 | 14.6 | 16.2 | 14.1 | 13.6 | 9.3 | 126 / 126 |
| varthur_kundalahalli | 5.6 | 6.0 | 9.3 | 4.6 | 4.3 | 2.5 | 49 / 49 |

## Reading (written after the run)

- **No sensor:** both graph methods beat the simple guess "the road is like its neighbours right now" on average:
  neighbours' GCN forecast 12.0 vs 14.2 points at +60 min (13.2 vs 14.4 at +15), GCN virtual sensor 13.2 vs 14.2 at
  +60 min (tie at +15). Per road it is mixed (e.g. orr_ccw_04, orr_iblur: virtual sensor clearly worse).
- **New sensor:** the unseen GCN ties "same as now" (10.8 vs 10.6 at +60 min). A road with live readings but no
  training history gains nothing yet; after training on its own data (normal model) the error drops to 8.2.
- **Normal model** (saw the road) is best everywhere: real readings plus training history matter most.
- Limits: one test week, one corridor, 2 seeds; the method shown first in the app was chosen before seeing these
  numbers, the neighbours' forecast column was added after (so its lead is measured on the same week it was picked on).
