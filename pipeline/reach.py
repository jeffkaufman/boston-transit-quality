"""Reachable shares from raptor's .m files (rows: see raptor.cpp).

jobsT: share of the region's jobs you can get to from a square within T minutes.
resT:  share of the region's residents who can get to a square within T minutes.
For rush hour pass the morning (am) and evening (pm) files: jobsT averages the trip
out in the morning with the trip home in the evening; resT averages the trip in to
the square in the morning with the trip out from it in the evening. With only one
file, jobsT uses trips out and resT trips in.

raptor records every 5 minutes from 5 to 120 (curve()); shares() picks 30/45/60.
"""
import numpy as np

TS = (30, 45, 60)
STEP = 5


def load(path, nc):
    return np.fromfile(path).reshape(-1, nc)


def _nt(m):
    return (m.shape[0] - 6) // 4


def curve(am, pm=None):
    """-> (minutes, jobs[NT][NC], res[NT][NC]) in %, for minutes = 5, 10, ..., 120."""
    nt = _nt(am)
    t = np.arange(nt)
    jobs = am[6 + 2 * t]                  # trips out, share of jobs
    res = am[7 + 2 * nt + 2 * t]          # trips in, share of residents
    if pm is not None:
        jobs = (jobs + pm[6 + 2 * nt + 2 * t]) / 2   # evening trip in = home
        res = (res + pm[7 + 2 * t]) / 2              # evening trip out = workers going home
    return (t + 1) * STEP, jobs * 100, res * 100


def shares(am, pm=None):
    """-> {"jobs30": array of %, ..., "res60": array of %}"""
    mins, jobs, res = curve(am, pm)
    out = {}
    for T in TS:
        i = int(np.where(mins == T)[0][0])
        out[f"jobs{T}"] = jobs[i]
        out[f"res{T}"] = res[i]
    return out


def rounded(d):
    return {k: np.round(v, 1).tolist() for k, v in d.items()}


def hist_files(hw, year, nc):
    return load(f"{hw}/{year}/rush_am.m", nc), load(f"{hw}/{year}/rush_pm.m", nc)


def hist_rush(hw, year, nc):
    """Rush-hour shares for one year of hist.py output (HW/<year>/rush_am.m, rush_pm.m)."""
    return shares(*hist_files(hw, year, nc))


def hist_curve(hw, year, nc):
    return curve(*hist_files(hw, year, nc))


TRANSIT_AREA_PCT = 10  # transit area: squares with at least this share within 45 minutes
