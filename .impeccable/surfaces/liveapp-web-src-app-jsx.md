---
version: 1
slug: "liveapp-web-src-app-jsx"
primary_target: "liveapp/web/src/App.jsx"
related_targets: []
---

Scope: main live screen of the ORR traffic app (React, replaces `/`; old page kept at `/classic`). Mode: Operate.
Audience/job: presenter on a projector and judges clicking on the laptop; see live data arrive, the prediction being made, where congestion is coming, and honest results.

## Direction contract
THESIS: The screen is the ORR's own roadside message sign turned into a control surface; it refuses the generic dark dashboard of card tiles and neon glows.
OWN-WORLD: Matte black sign housings with a faint dot-pitch; LED amber (#FFB000 family) as the single interface accent; traffic state only from the congestion ramp (red/orange/amber/lime/green) and always paired with numbers; Doto dot-matrix numerals for headline values, Barlow / Barlow Condensed (highway-sign lineage) for all text and labels; thin aluminium frame lines, no glass, no gradients on text.
STORY: The viewer reads one sign line per hotspot ("BELLANDUR - JAM IN 30 MIN"), watches a light pulse run TomTom -> cache -> 15 networks -> forecast whenever new readings land or the moment changes, switches NOW/+15/+30/+60 and sees the map change, and opens PROOF to see test-week errors with limits.
FIRST VIEWPORT: Top: sign-frame header (title, LIVE/REPLAY switch, clock, freshness). Under it the pipeline sign strip across full width. Left two thirds: map owning the field, roads coloured by the chosen horizon, four horizon sign tiles over its top edge. Right third: the message board of hotspots (re-ranking rows), then the corridor forecast chart. Replay scrubber docks at the bottom in REPLAY.
FORM: Roadside variable message sign, own grounded list position 6, seed key f7ba1620. Raises: departure board (rows re-rank in place, changed rows hold amber until seen); botanical folio (four horizon tiles at identical scale); catalog sleeve (one map owns the field, quiet around it). Signature interaction: the pipeline pulse plus LED digit roll on every recompute.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
