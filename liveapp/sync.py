#!/usr/bin/env python3
"""Download the project's collected data into the app's local cache (liveapp/data/cache).

  python liveapp/sync.py              # all months from the bengaluru-data branch (first time: about 6 MB)
  python liveapp/sync.py --geometry   # also ask TomTom once for the exact shape of the 21 road stretches
                                      # (needs TOMTOM_API_KEY; 21 requests; writes liveapp/data/geometry.json)

After this the app starts without internet. The cache holds TomTom readings: keep it private (it is in .gitignore).
"""
import argparse
import os
import sys

import livefeed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--geometry", action="store_true")
    a = ap.parse_args()
    files, nbytes = livefeed.sync_github(all_months=True)
    print(f"data cache: {len(files)} file(s) downloaded ({nbytes / 1e6:.1f} MB) into {livefeed.CACHE}")
    if a.geometry:
        key = os.environ.get("TOMTOM_API_KEY")
        if not key:
            sys.exit("Set TOMTOM_API_KEY first (Windows PowerShell: $env:TOMTOM_API_KEY=\"...\").")
        ok, n = livefeed.fetch_tomtom(key)
        print(f"TomTom: {ok} of 21 stretches read; exact road shapes saved to {livefeed.GEOMETRY_JSON}")


if __name__ == "__main__":
    main()
