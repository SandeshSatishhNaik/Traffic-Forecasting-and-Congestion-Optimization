#!/usr/bin/env bash
# Start the live app (Mac / Linux). Add --source off when there is no internet.
cd "$(dirname "$0")/.." && exec python3 liveapp/main.py "$@"
