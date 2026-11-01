# Pretraining on METR-LA, then fine-tuning on the Bengaluru corridor (2026-11-01)

Code: `modeling/pretrain.py` (uses `refmodels.STID`, `refbengaluru.py`, `metrla.py`).

## Setup
- METR-LA (207 Los Angeles freeway sensors, 5-minute speeds) is turned into the same form as our data: speed divided by the road's fixed reference speed (95th percentile of night speed), 15-minute steps (three offsets of the 5-minute series), 6 past steps in, +15/+30/+60 minutes out.
- STID is pretrained for 15 epochs on METR-LA (best validation error 4.72% of normal speed). Road-specific node embeddings cannot transfer (207 vs 21 roads) and start from scratch; the input layer, time-of-day and day-type embeddings, the MLP trunk and the output layer are transferred.
- On Bengaluru, same rows and 5 seeds as every other model: test week 25-31 Oct 2026.

## Result (MAE km/h, mean +- std over 5 seeds, lower is better)

| Horizon | Our graph net | STID from scratch | STID from scratch, fine-tuning settings (control) | STID pretrained, all weights fine-tuned | STID pretrained, trunk frozen |
|---|---|---|---|---|---|
| 15 min | 2.99 +- 0.02 | 2.98 +- 0.01 | 3.01 +- 0.02 | **2.92 +- 0.01** | 2.96 +- 0.01 |
| 30 min | 3.33 +- 0.03 | 3.34 +- 0.02 | 3.37 +- 0.04 | **3.27 +- 0.02** | 3.35 +- 0.02 |
| 60 min | 3.46 +- 0.03 | 3.41 +- 0.04 | 3.43 +- 0.04 | **3.33 +- 0.04** | 3.41 +- 0.02 |

The fine-tuned runs used a lower learning rate (1e-3) and shorter patience than the default from-scratch runs (2e-3). To make sure that was not the cause, the control trains from scratch with the same fine-tuning settings: it is no better than the default, so the gain is not a learning-rate effect.

## Reading
- Pretraining on METR-LA and fine-tuning all weights lowers the error by about 0.07 km/h (2%) against STID from scratch and by about 0.1 km/h (3%) against the control, at all three horizons. The gap is larger than the seed-to-seed spread (0.01-0.04).
- Freezing the trunk gives no gain: the transferred layers need to adapt.
- For scale: removing the road graph from our net costs 8-9%. Pretraining is a smaller effect.

## Limits (state these if asked)
- One pretraining run (one seed); the five seeds vary only the Bengaluru fine-tuning. Pretraining variance is not measured.
- One test week and one corridor. A 3% gain on one week is encouraging, not proof.
- The two datasets differ (Los Angeles 2012 versus Bengaluru 2026); why it helps is not tested. A plausible reason is that the trunk learns general time-of-day and neighbouring-speed patterns, but that is a guess.
- Only STID was pretrained. Our own graph net and Graph WaveNet were not.
