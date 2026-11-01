#!/usr/bin/env python3
"""Check that a collection schedule stays inside the TomTom free tier (20,000 flow requests a month).

Compares the live schedule (collector/loop.sh) with the proposed one that adds the alternative roads
(collector/ALT_ROADS.md). Usage: python3 collector/quota_plan.py [number of alt stretches, default 12]
"""
import sys

FREE = 20000
DAYS = 31

LIVE = dict(
    core=(17, "0707 0737 0807 0822 0837 0852 0907 0922 0937 0952 1007 1037 1207 1407 1637 1707 1737 1807 1822 1837 "
              "1852 1907 1922 1937 1952 2007 2037 2207 0007 0207 0407 0607"),
    context=(4, "0707 0807 0907 1007 1207 1407 1707 1807 1907 2007 2207 0207 0607"),
)


def plan(alt_stretches):
    """Proposed schedule: drop the two midnight readings and two quiet daytime readings of the core roads
    and two of the context roads, and read the alternative roads at the rush hours plus three quiet times."""
    core = [t for t in LIVE["core"][1].split() if t not in ("0007", "0407", "1407", "2037")]
    context = [t for t in LIVE["context"][1].split() if t not in ("1407", "2207")]
    alt = "0807 0837 0907 0937 1207 1737 1807 1837 1907 0207".split()
    return dict(core=(17, " ".join(core)), context=(4, " ".join(context)), alt=(alt_stretches, " ".join(alt)))


def show(title, p):
    print(title)
    day = 0
    for tier, (n, times) in p.items():
        k = len(times.split())
        print(f"  {tier:8s} {n:3d} stretches x {k:2d} readings = {n * k:4d} requests/day")
        day += n * k
    print(f"  total {day} per day, {day * DAYS:,} per {DAYS}-day month, free tier {FREE:,}: "
          f"{'OK' if day * DAYS <= FREE else 'OVER'} ({FREE - day * DAYS:+,})")
    return day * DAYS <= FREE


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    show("live schedule", LIVE)
    ok = show(f"proposed schedule with {n} alternative stretches", plan(n))
    sys.exit(0 if ok else 1)
