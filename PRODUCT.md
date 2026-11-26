# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Live app: FastAPI backend (`liveapp/main.py`) serving static files and a JSON API. Main screen: React, built with
Vite into static files served by FastAPI (works offline, no CDN at run time). Earlier plain-JS pages stay as
fallbacks (`/classic`, `/static/3d.html`).

## Users

Two audiences, equally: (1) the student team presenting to an academic panel on a college projector, driving the
screen while explaining; (2) judges who then take the laptop and click around on their own. Neither audience knows
the code; judges know traffic and machine learning only in general terms.

## Product Purpose

"AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic Forecasting and Congestion Optimization"
(GM University PBL). It forecasts road speed 15, 30 and 60 minutes ahead on 21 connected road stretches of
Bengaluru's Outer Ring Road from real TomTom readings collected by the team's own pipeline, with a Graph
Convolutional Network over the road graph, and turns forecasts into congestion alerts, trip-time estimates and
route recommendations. Success on the screen: a viewer sees live data arriving, sees the prediction being made,
sees where congestion is coming, and sees honest results.

## Positioning

Own data pipeline (TomTom readings since 27 Sep 2026) plus a road-graph model running live on a laptop, with every
forecast checkable against what actually happened, and an honest account of limits.

## Operating Context

Live mode (newest reading, at most 15 min old in rush hours, up to 2 h at night) and Time-lapse/replay of recorded
days. The presentation day (27 Nov 2026) is a public holiday, so live traffic is light and the demo leads with a
recorded weekday rush (Tue 24 Nov). May run without internet (`--source off`): map tiles then unavailable.

## Capabilities and Constraints

- API: `/api/status`, `/api/network`, `/api/days`, `/api/timeline`, `/api/snapshot`, `/api/series`, `/api/route`,
  `/api/results`, `/api/unseen`, `POST /api/live/refresh`, `/api/stream` (server-sent events), `/docs`.
- 15 networks (3 horizons x 5 seeds), 2-7 ms per moment. Speeds shown as % of each road's normal speed.
- Thresholds: congested < 60%, slow < 75%. Early warning = fine now, forecast to congest.
- TomTom licence: readings must not be published or committed; the UI may show them locally.

## Evidence on Hand

- Test week 19-25 Nov 2026: model MAE 2.89 / 3.24 / 3.28 km/h vs "same as now" 3.14 / 3.81 / 4.32 (`/api/status`).
- Phase 2 comparison of 11 model versions (`/api/results`); STID (no graph) ties the GCN.
- Unseen roads: `modeling/results/unseen-roads-2026-11-26.md` (virtual sensor 12.0 vs neighbours 14.2 points at +60).
- No testimonials, users or deployments exist; do not invent any.

## Product Principles

1. Show, then claim: every number on screen is computed live or comes from a result file.
2. Honest by default: limits (one test week, one corridor) sit next to results.
3. One glance for the panel, depth on click for the judges.
4. Live and replay are the same system, so every forecast can be checked against reality.

## Accessibility & Inclusion

Readable on a washed-out projector from the back of a room: large type, strong contrast, meaning never carried by
colour alone (labels and numbers next to colours). Respect reduced-motion preferences.
