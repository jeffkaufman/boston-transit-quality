"""Compact per-year history data, written by hist_extract.py to intermediates/hist/.

  hist.json         per year: feed, date, summary, rush summary, transit lines (hist_lines.py)
  curves.json       per year: rush-hour reach curves averaged over the region (reach.curve):
                    minutes 0..120, the average resident's % of jobs, the average job's % of residents
  cells-YEAR.u16    uint16 [4][NC], little-endian, one row per measure (MEASURES), per grid square:
                    rush-hour and all-day mean trip to jobs in tenths of a minute (as hist.json
                    stored them), and the rush-hour share of jobs within 45 min / of residents who
                    can get there within 45 min, in hundredths of a percent. The history page's
                    compare tool loads these same files in the browser.

These are small, and slow to regenerate (the routing takes hours), so keep them.
"""
import json
import numpy as np

MEASURES = (("rush", 10), ("day", 10), ("jobs45", 100), ("res45", 100))  # name, scale


def load(d):
    H = json.load(open(f"{d}/hist.json"))
    C = json.load(open(f"{d}/curves.json"))
    return H, {y: tuple(np.array(v) for v in C[y]) for y in C}


def cells(d, year, nc):
    a = np.fromfile(f"{d}/cells-{year}.u16", dtype="<u2").reshape(len(MEASURES), nc)
    return {name: a[i] / scale for i, (name, scale) in enumerate(MEASURES)}


def save_cells(d, year, vals):
    a = np.array([np.round(np.asarray(vals[name]) * scale) for name, scale in MEASURES])
    assert a.min() >= 0 and a.max() < 65536
    a.astype("<u2").tofile(f"{d}/cells-{year}.u16")
