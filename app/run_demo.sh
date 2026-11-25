#!/usr/bin/env bash
# Start the offline traffic app (Mac / Linux). Needs Python 3 and app/data/bundle.json.
cd "$(dirname "$0")/.." && exec python3 app/server.py "$@"
