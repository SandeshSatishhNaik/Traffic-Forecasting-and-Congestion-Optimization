#!/usr/bin/env python3
"""Run the collector on your own computer, around the clock, with no GitHub and no git.

Same schedule as collector/loop.sh (times in IST). Readings are written to a folder on this machine
(default ./local-data) in the same layout as the data branch, so modeling/ reads it unchanged.

  python collector/run_local.py --out local-data          # needs TOMTOM_API_KEY in the environment
  python collector/run_local.py --out /tmp/x --dry-run    # fake readings, no key, no network

Keep the computer awake and online: readings missed while it sleeps cannot be recovered.
Do not run this and the GitHub collector at the same time (they share TomTom's monthly free limit).
Standard library only. Stop with Ctrl+C.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
IST = timezone(timedelta(hours=5, minutes=30))
# Keep in sync with CORE_TIMES / CONTEXT_TIMES in loop.sh.
CORE_TIMES = set("0707 0737 0807 0822 0837 0852 0907 0922 0937 0952 1007 1037 1207 1407 1637 1707 1737 1807 1822 1837 1852 1907 1922 1937 1952 2007 2037 2207 0007 0207 0407 0607".split())
CONTEXT_TIMES = set("0707 0807 0907 1007 1207 1407 1707 1807 1907 2007 2207 0207 0607".split())


def due(hhmm):
    tiers = []
    if hhmm in CORE_TIMES:
        tiers.append("core")
    if hhmm in CONTEXT_TIMES:
        tiers.append("context")
    return ",".join(tiers)


def next_slot(now):
    """Next :07, :22, :37 or :52 past the hour (the 15-minute grid the schedule uses), strictly after now."""
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while t.minute not in (7, 22, 37, 52):
        t += timedelta(minutes=1)
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="local-data")
    ap.add_argument("--dry-run", action="store_true", help="fake readings, no network")
    ap.add_argument("--no-incidents", action="store_true")
    ap.add_argument("--once", action="store_true", help="collect everything once now and exit")
    ap.add_argument("--max-slots", type=int, default=0, help="stop after this many slots (for tests)")
    a = ap.parse_args()
    if not a.dry_run and not os.environ.get("TOMTOM_API_KEY"):
        sys.exit("Set the TOMTOM_API_KEY environment variable first.")
    os.makedirs(a.out, exist_ok=True)

    def collect(tiers, with_incidents):
        cmd = [sys.executable, os.path.join(HERE, "collect.py"), "--segments", os.path.join(HERE, "segments.csv"), "--out", a.out]
        if tiers:
            cmd += ["--tiers", tiers]
        if with_incidents:
            cmd.append("--incidents")
        if a.dry_run:
            cmd.append("--dry-run")
        r = subprocess.run(cmd)   # a failed collection must not stop the loop; the next slot tries again
        if r.returncode != 0:
            print("collection failed (exit %d); will try again at the next slot" % r.returncode, flush=True)

    if a.once:
        collect("", not a.no_incidents)
        return
    slots = 0
    print("Local collector running. Ctrl+C to stop.", flush=True)
    while True:
        now = datetime.now(IST)
        t = next_slot(now)
        time.sleep(max(0, (t - datetime.now(IST)).total_seconds()))
        tiers = due(t.strftime("%H%M"))
        if tiers:
            # incidents at the :07 and :37 readings, as in the GitHub version
            collect(tiers, (not a.no_incidents) and t.minute in (7, 37))
        else:
            print(t.strftime("%H:%M IST: not a collection slot, skipped"), flush=True)
        slots += 1
        if a.max_slots and slots >= a.max_slots:
            return


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
