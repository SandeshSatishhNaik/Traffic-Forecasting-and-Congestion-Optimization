"""Turn the collector's CSV files into a regular 15-minute table of speeds.

Input : a folder with tomtom_flow/*.csv (and optionally weather/*.csv), as written by
        collector/collect.py (the bengaluru-data branch or the private data repository).
Output: pandas objects used by baselines.py.

Nothing here is written to the repository: the readings are TomTom results and stay out of it.
"""
import glob
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SEGMENTS_CSV = os.path.join(HERE, "..", "collector", "segments.csv")
LINKS_CSV = os.path.join(HERE, "..", "collector", "network", "links.csv")
LEGACY_IDS = {"sarjapur_agara": "orr_ccw_03"}   # see collector/network/legacy_ids.csv
FIRST_READING = "2026-09-30 10:40"              # first reading of the 21-stretch network
HOLIDAYS = {"2026-10-02"}                       # Gandhi Jayanti (a Friday)
SLOT_MIN = 15
SLOT_OFFSET_MIN = 7                             # the collector wakes at :07, :22, :37, :52 (IST)


def load_flow(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, "tomtom_flow", "*.csv")))
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df[df["status"] == "ok"].copy()
    df["segment_id"] = df["segment_id"].replace(LEGACY_IDS)
    df["t"] = pd.to_datetime(df["timestamp_ist"])
    df = df[df["t"] >= pd.Timestamp(FIRST_READING)]
    ids = pd.read_csv(SEGMENTS_CSV)["segment_id"].tolist()
    return df[df["segment_id"].isin(ids)], ids


def to_slot(t):
    """Snap a reading time to the 15-minute collection grid (:07, :22, :37, :52)."""
    minutes = (t - t.dt.normalize()).dt.total_seconds() / 60 - SLOT_OFFSET_MIN
    k = np.round(minutes / SLOT_MIN)
    return t.dt.normalize() + pd.to_timedelta(k * SLOT_MIN + SLOT_OFFSET_MIN, unit="m")


def speed_grid(df, ids):
    """Rows = every 15-minute slot, columns = segments, value = speed in km/h (NaN where no reading)."""
    df = df.copy()
    df["slot"] = to_slot(df["t"])
    wide = df.groupby(["slot", "segment_id"])["current_speed_kmph"].last().unstack()
    full = pd.date_range(wide.index.min(), wide.index.max(), freq=f"{SLOT_MIN}min")
    return wide.reindex(full)[ids].astype(float)


def free_flow_reference(grid, train_end):
    """Fixed reference speed per road: 95th percentile of its night-time speeds in the training period."""
    g = grid[grid.index < train_end]
    night = g[(g.index.hour >= 22) | (g.index.hour < 6)]
    return night.quantile(0.95)


def day_type(index):
    d = index.strftime("%Y-%m-%d")
    weekend = (index.dayofweek >= 5) | d.isin(HOLIDAYS)
    return np.where(weekend, "weekend/holiday", "weekday")


def adjacency(ids, kind=("flow",)):
    """Directed 0/1 adjacency matrix from collector/network/links.csv (crossings made symmetric)."""
    links = pd.read_csv(LINKS_CSV)
    pos = {s: i for i, s in enumerate(ids)}
    A = np.zeros((len(ids), len(ids)))
    for _, r in links.iterrows():
        if r["kind"] in kind:
            A[pos[r["from_id"]], pos[r["to_id"]]] = 1
            if r["kind"] == "crossing":
                A[pos[r["to_id"]], pos[r["from_id"]]] = 1
    return A
