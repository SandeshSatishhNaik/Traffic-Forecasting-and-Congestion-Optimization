---
name: ORR Traffic Intelligence
description: The Bengaluru ORR's roadside message sign turned into a control surface; matte black, LED amber, congestion colour only from the ramp.
colors:
  sign-housing: "#08090b"
  sign-face: "#101216"
  raised-face: "#161920"
  aluminium-rim: "#2a2e36"
  aluminium-rim-hi: "#3b414c"
  ink: "#eef0f3"
  ink-secondary: "#aab1bd"
  ink-tertiary: "#7d8593"
  led-amber: "#ffb000"
  jam: "#f24834"
  slow: "#ffa800"
  free: "#1fbfb8"
  virtual-cyan: "#3fd0e0"
typography:
  led-numeral:
    fontFamily: "Doto, monospace"
    fontSize: "3.4rem"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "0.02em"
  headline:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "0.01em"
  title:
    fontFamily: "Barlow Condensed, Barlow, sans-serif"
    fontSize: "1.1rem"
    fontWeight: 600
    lineHeight: 1.45
  body:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "0.82rem"
    fontWeight: 500
    lineHeight: 1.4
rounded:
  sm: "3px"
  md: "4px"
  lg: "6px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "22px"
components:
  mode-switch-on:
    backgroundColor: "{colors.led-amber}"
    textColor: "#111111"
    rounded: "{rounded.md}"
    padding: "8px 18px"
  tab-on:
    textColor: "{colors.led-amber}"
    padding: "12px 6px 11px"
  horizon-tile:
    backgroundColor: "#08090be6"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "9px 12px 8px"
  sign-row:
    backgroundColor: "#000000"
    rounded: "{rounded.lg}"
    padding: "9px 11px"
  ghost-button:
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.lg}"
    padding: "5px 13px"
  play-button:
    backgroundColor: "{colors.led-amber}"
    textColor: "#111111"
    size: "42px"
    rounded: "50%"
---

# Design System: ORR Traffic Intelligence

## Overview

**Creative North Star: "The Roadside Message Sign"**

The interface is the ORR's own variable message sign repurposed as a control surface. Housings are matte black with a faint dot-pitch texture, frames are thin aluminium lines, and one LED amber carries every interactive and "this just changed" signal. Traffic state never borrows the amber accent's job: it comes only from the congestion ramp and is always paired with a number.

Density is operator-grade: a header sign, a four-stage pipeline strip, a map that owns the field, and a 450px message board on the right. It is built for a projector and for judges clicking on a laptop, so contrast and scale beat subtlety. It rejects the generic dark dashboard of card tiles and neon glows.

**Key Characteristics:**
- Dark only (`color-scheme: dark`); no glass, no gradients on text.
- Amber is the single interface accent; red/orange/lime/green appear only as traffic state.
- Dot-matrix (Doto) for headline values and sign messages; Barlow family for everything else.
- Flat frames; glow is reserved for "just changed" and LED text.
- Motion explains data flow (pulse along the pipeline, digit roll, row re-rank) and honours reduced motion.

## Colors

Near-black neutrals, one amber, and a five-stop congestion ramp.

### Primary
- **LED Amber** (#ffb000): selected mode, active tab and tile, LED numerals, forecast line, "fresh/changed" row rim, LIVE tag, focus ring, play button. Dim wash `rgba(255,176,0,.16)` marks the model actually in use.

### Secondary
- **Virtual Cyan** (#3fd0e0): only for the "unseen road" virtual sensor (dashed road, chart line, note). Marks estimated, not measured.

### Tertiary (traffic state, from the ramp only)
- **Jam** (#f24834), **Slow** (#ffa800), **Free** (#1fbfb8, teal so it stays distinct from red for red-green colour-blind viewers): level colours for sign messages and cells. Map roads and speed cells interpolate the full ramp in `lib.js` (STOPS): #be1830 at 35% of reference speed, #f24834 at 60%, #ffa800 at 75%, #96d678 at 90%, #1fbfb8 at 100%; no reading is grey (#5c626e). The legend `.ramp` repeats the same stops.

### Neutral
- **Sign Housing** (#08090b): page and map-overlay base. **Sign Face** (#101216): header, side panel, replay bar. **Raised Face** (#161920): hover and selected-segment fill. **Aluminium Rim** (#2a2e36) / **Rim Hi** (#3b414c): all frame lines and dividers. Pure black (#000) is the inner sign-board face under the dot-pitch.
- **Ink** (#eef0f3), **Ink Secondary** (#aab1bd, at least 4.5:1 on Sign Face), **Ink Tertiary** (#7d8593, small supporting text only).

### Named Rules
**The Ramp-Only Rule.** Congestion colour comes from the ramp and always sits beside a number or word. Amber never means "slow traffic" beyond the ramp's own amber stop; interface amber stays on controls and change signals.
**The One Voice Rule.** Amber is the only interface accent. Anything new that wants a second accent is a data state and belongs on the ramp or the virtual-cyan channel.

## Typography

**Display Font:** Doto 700/900 (LED dot-matrix), monospace fallback.
**Body Font:** Barlow 400/500/600, system-ui fallback.
**Label/Heading Font:** Barlow Condensed 500-700 (highway-sign lineage).

**Character:** Dot-matrix numerals read as lit LEDs; condensed Barlow gives headings and tabs sign-painter economy; plain Barlow keeps prose legible.

### Hierarchy
- **LED numeral** (Doto 900, 1.35rem / 2.3rem / 3.4rem, line-height 1, amber with 4px glow): headline values, stage counters, replay cursor time.
- **Sign message** (Doto 900, 1.12rem, uppercase, .03em): one line per hotspot, coloured by tone (jam #ff5a46, early amber, slow #ffd166, calm green).
- **Headline** (Barlow Condensed 600, 1.5-1.6rem, 1.1): app title and road name.
- **Title** (Barlow Condensed 600, 1.1-1.15rem): tabs, panel headings, tile keys.
- **Body** (Barlow 400, 15px, 1.45; panel prose .9rem / 1.5, keep lines to the 450px panel): explanations and proof text.
- **Label** (Barlow 500-600, .78-.9rem): units, sources, axis text (13px), table cells; tabular numerals for all figures.

### Named Rules
**The LED Scarcity Rule.** Doto appears only on numerals and sign messages. Never set a paragraph, button label, or heading in it.

## Layout

Fixed-viewport app grid at desktop: header, pipeline strip, then a main row of map (fluid) and side panel (450px; 400px at 1280px and below), with the replay bar docking at the bottom in Replay. The map owns the field; overlays (four horizon tiles top-left, clock tag top-right, legend bottom-right) are small and hug its edges. Spacing is a compact 6/8/12/18/22px rhythm; panels pad 16px 18px.

At 900px and below the page scrolls: header wraps, pipeline goes 2-up (wires hidden), map takes 70vh, side panel stacks below, clock tag and legend are hidden, and tiles go 2-up.

## Elevation & Depth

Flat by default. Depth is carried by tonal layering (housing, face, raised face) and 1px aluminium frames, not shadows. Light is reserved for state: an amber 1px ring plus soft glow on a changed row, a fired pipeline stage, or the selected tile; map tooltip and toast get a single dark drop shadow so they lift off the map.

### Named Rules
**The Glow-Means-Change Rule.** Amber glow marks something that just updated or is selected. It never decorates resting surfaces.

## Shapes

Small, engineered corners: 6px on frames, tiles, rows, inputs; 4px on segmented-control inner buttons and cells; 3px on the ramp and bars; circles only for the play button, the live dot and the pulse spark. Borders are 1px aluminium; no outlines other than the 2px amber focus ring (offset 2px). Sign boards use the dot-pitch (radial dots on a 5px grid at 8% white) as texture.

## Components

### Mode switch and tabs
- **Mode switch:** black inset track, condensed 1.05rem labels; selected = amber fill with #111 text, plus a pulsing red-dot beat when LIVE.
- **Tabs:** condensed 1.1rem, secondary ink; selected = amber text and 2px amber underline.
- **Segmented control:** black track, selected = raised face with amber text and inset amber ring.

### Horizon tiles
- Four equal tiles (NOW, +15, +30, +60) at identical scale, 90% housing fill, 1px rim; selected = amber border and ring, amber key. Hover lifts 1px.

### Message board (signature)
- One black sign row per hotspot: Doto message line, road name, and up to four speed cells coloured from the ramp (dark text on ramp fill). Rows re-rank in place and a changed row holds an amber rim until seen; selected row takes a secondary-ink rim. Calm state is one green sign line.

### Pipeline strip (signature)
- Four stage signs (TomTom, cache, 15 networks, forecast) on a dot-pitch strip, joined by wires; on new data a light spark runs each wire and each stage briefly rings amber. Numbers roll via LED digit animation.

### Chart
- Recent speed in near-white, forecast in dashed amber with a translucent amber band, "now" line in amber, virtual estimate in cyan, measured actuals as hollow circles. Draws in on mount.

### Buttons and fields
- **Ghost / link:** 1px rim-hi outline, secondary ink (ghost) or amber (link); hover raises contrast or adds amber wash.
- **Play:** 42px amber disc, #111 glyph. **Select:** black fill, rim-hi border. **Scrubber:** black dot-pitch strip with white 3px cursor and amber LED time.
- **Proof table:** hairline rows, right-aligned tabular numerals; model in use gets the amber wash and an amber "used" chip.

## Do's and Don'ts

### Do:
- **Do** colour traffic state only from the ramp in `lib.js` and the `.ramp` gradient, and print the number or word next to it.
- **Do** keep amber (#ffb000) as the sole interface accent, and dark text (#111) on amber fills.
- **Do** set secondary text at Ink Secondary (#aab1bd) or lighter; Ink Tertiary is for small supporting text only.
- **Do** show estimated values (virtual sensor) in cyan with a dashed treatment, so measured and estimated never look alike.
- **Do** keep the 2px amber focus ring and a reduced-motion fallback on any new animation.

### Don't:
- **Don't** use the generic dark dashboard look: floating glass cards, neon glows, gradient text.
- **Don't** use amber glow, spark or pulse on resting elements; it signals change.
- **Don't** colour a control with a ramp colour, or a traffic value with the interface amber.
- **Don't** use Doto outside numerals and sign messages.

Not canonized: the small uppercase tracked labels on pipeline stages (`.stage-k`) and the LIVE/REPLAY clock tag (`.moment-tag`) are kicker-style captions the build carries; future surfaces should not copy them. The older fallback pages `/classic` (`liveapp/static/index.html`) and `liveapp/static/3d.html` sit outside this system.
