"""Render history images: one map per year plus change maps, for four measures, and the
files the history page's compare tool draws any two years from in the browser.

Usage: TQ_SITE=SITE_DIR hist_render.py HIST_DIR OUT_DIR
  HIST_DIR: hist_extract.py output (see histdata.py)
Maps have no lines or place names; pages overlay labels.png from render.py and
lines-{year}.png (each year's lines, written here; change maps use the later year's).
Measures: rush hour (files without suffix), all day 7am-7pm ("-allday"), and the rush-hour
shares of jobs / residents within 45 minutes ("-jobs45", "-res45").

Compare tool (OUT_DIR/cmp/): cells-YEAR.u16 (copied from HIST_DIR), meta.json (grid,
image geometry, colors, titles), and per-measure frames frame-*.png (white page,
land, legend, no cells or title) plus water.png; the page draws cells, then water,
then the title.
"""
import json, os, shutil, sys
from datetime import date as D
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R  # noqa: E402
import histdata  # noqa: E402
import reach as RCH  # noqa: E402

HD, OUT = sys.argv[1:3]
os.makedirs(f"{OUT}/cmp", exist_ok=True)
H, _ = histdata.load(HD)
NC = len(R.G["cells"])
CELLS = {y: histdata.cells(HD, y, NC) for y in sorted(H)}


def nice_date(s):
    return D(int(s[:4]), int(s[4:6]), int(s[6:])).strftime("%b %-d, %Y")


SUB = "today's population, jobs, streets"
WIN = {"rush": "Weekday, out 7–9am, back 4:30–6:30pm", "day": "Weekday 7am–7pm",
       "jobs45": "Weekday rush hour, round trip", "res45": "Weekday rush hour, round trip"}
PHRASE = {"rush": "Rush-hour commute to a typical job", "day": "Average transit trip to a typical job",
          "jobs45": R.reach_title("jobs45"), "res45": R.reach_title("res45")}
SUFFIX = {"rush": "", "day": "-allday", "jobs45": "-jobs45", "res45": "-res45"}
lower = lambda s: s[0].lower() + s[1:]

# Diverging change maps: purple = better, orange = worse (ColorBrewer PuOr).
# Time: d = later - earlier minutes. Shares: d = -(later - earlier) points, so gains are purple.
EDGES = [-15, -10, -6, -3, -1, 1, 3, 6, 10, 15]
HEX = ["#2d004b", "#542788", "#8073ac", "#b2abd2", "#d8daeb", "#ededea", "#fee0b6", "#fdb863", "#e08214", "#b35806", "#7f3b08"]
RGB = [tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in HEX]


def change_legend(ms):
    if ms in ("rush", "day"):
        return dict(colors=HEX, ticks=[(k + 1, f"{e:+d}" if e else "0") for k, e in enumerate(EDGES)],
                    right=None, caption="Change in minutes  ·  purple: faster  ·  orange: slower")
    noun = "jobs" if ms == "jobs45" else "residents"
    return dict(colors=HEX, ticks=[(k + 1, f"{-e:+d}" if e else "0") for k, e in enumerate(EDGES)], right=None,
                caption=f"Change in percentage points of the region's {noun}  ·  purple: more  ·  orange: fewer")


def change_title(ms, a, b):
    return f"Change in {lower(PHRASE[ms])}, {a} to {b}"


def change_sub(ms, a, b):
    return f"{WIN[ms]}  ·  MBTA schedules: {nice_date(H[a]['date'])} and {nice_date(H[b]['date'])}  ·  {SUB}"


for year, r in sorted(H.items()):
    R.overlay(f"{OUT}/lines-{year}", R.project_lines(r["lines"]))
print("line overlays", flush=True)

for ms in ("rush", "day", "jobs45", "res45"):
    for year, r in sorted(H.items()):
        v = CELLS[year][ms]
        if ms in ("rush", "day"):
            img, legend = R.time_image(v, "jobs"), R.time_legend("jobs")
        else:
            img, legend = R.share_image(v), R.share_legend(ms)
        R.draw(img, [], f"{PHRASE[ms]}, {year}",
               f"{WIN[ms]}  ·  MBTA schedule for Tuesday {nice_date(r['date'])}  ·  {SUB}",
               legend, f"{OUT}/year-{year}{SUFFIX[ms]}", labels=False)
    for base, to in (("2009", "2026"), ("2019", "2026")):
        a, b = CELLS[base][ms], CELLS[to][ms]
        d = np.round(b - a if ms in ("rush", "day") else -(b - a), 6)  # no float noise at band edges; matches the browser
        idx = np.searchsorted(EDGES, d, side="right")
        idx = np.where((d > -1) & (d <= 1), 5, idx)  # values exactly on +1 belong to the middle band
        alphas = (np.where((a >= 179.5) & (b >= 179.5), 0.0, 0.93) if ms in ("rush", "day") else np.full(NC, 0.93))
        R.draw(R.cells_image([RGB[i] for i in idx], alphas), [], change_title(ms, base, to),
               change_sub(ms, base, to), change_legend(ms), f"{OUT}/change-{base}-{to}{SUFFIX[ms]}", labels=False)
        if ms == "rush":
            w = np.array(R.G["pop"], float)
            print(f"rush {base}->{to}: residents in faster squares {w[d < -1].sum() / w.sum():.0%}, slower {w[d > 1].sum() / w.sum():.0%}", flush=True)
    print("maps", ms, flush=True)

# ---- Transit area for homes, 2009 vs 2026 ----
TH = RCH.TRANSIT_AREA_PCT
in0, in1 = CELLS["2009"]["jobs45"] >= TH, CELLS["2026"]["jobs45"] >= TH
BOTH, LOSS, GAIN = "#9aa3a6", "#e08214", "#8073ac"
cols = [BOTH if a and b else LOSS if a else GAIN for a, b in zip(in0, in1)]
R.draw(R.cells_image([tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in cols], np.where(in0 | in1, 0.9, 0.0)), [],
       "The transit area, 2009 and 2026",
       f"Homes from which at least {TH}% of the region's jobs are within a 45-minute rush-hour commute  ·  {SUB}",
       dict(colors=[BOTH, LOSS, GAIN], ticks=[], right=None,
            caption="Gray: in both years  ·  orange: dropped out by 2026  ·  purple: joined by 2026"),
       f"{OUT}/area-2009-2026", labels=False)
print("area map", flush=True)

# ---- Compare tool: any two years, drawn in the browser ----
blank = np.zeros((R.NR, R.NCOL, 4))
for fr, ms in (("time", "rush"), ("jobs45", "jobs45"), ("res45", "res45")):
    R.draw(blank, [], "", "", change_legend(ms), f"{OUT}/cmp/frame-{fr}", labels=False, water=False)
R.overlay(f"{OUT}/cmp/water", water=True)
for y in H:
    shutil.copy(f"{HD}/cells-{y}.u16", f"{OUT}/cmp/cells-{y}.u16")
Wb, Hb = Image.open(f"{OUT}/cmp/frame-time-big.png").size
px = Hb / R.FIG_H  # pixels per inch in the -big images
meta = {
    "years": sorted(H), "nc": NC, "nr": R.NR, "ncol": R.NCOL,
    "cells": R.G["cells"],  # index = row * ncol + col, row 0 at the south edge
    "measures": [n for n, _ in histdata.MEASURES], "scales": [s for _, s in histdata.MEASURES],
    "w": Wb, "h": Hb, "mapTop": round(Hb - (R.FOOT + R.MAP_H) * px, 2), "mapH": round(R.MAP_H * px, 2),
    "title": {"x": round(0.012 * Wb, 1), "y": round(0.17 * px, 1), "px": round(10.5 * px / 72, 1),
              "subY": round(0.36 * px, 1), "subPx": round(6.6 * px / 72, 1)},
    "land": R.LAND, "ink": R.INK, "muted": R.MUTED, "alpha": 0.93,
    "edges": EDGES, "colors": HEX,
    "frame": {"rush": "time", "day": "time", "jobs45": "jobs45", "res45": "res45"},
    "titles": {ms: change_title(ms, "{a}", "{b}") for ms in PHRASE},
    "subs": {ms: f"{WIN[ms]}  ·  MBTA schedules: {{da}} and {{db}}  ·  {SUB}" for ms in PHRASE},
    "dates": {y: nice_date(H[y]["date"]) for y in H},
    # region-wide averages shown under the compare tool
    "avg": {"rush": {y: H[y]["rush"]["summary"]["jobs"] for y in H}, "day": {y: H[y]["summary"]["jobs"] for y in H},
            "jobs45": {y: round(float(np.average(CELLS[y]["jobs45"], weights=R.G["pop"])), 1) for y in H},
            "res45": {y: round(float(np.average(CELLS[y]["res45"], weights=R.G["jobs"])), 1) for y in H}},
}
json.dump(meta, open(f"{OUT}/cmp/meta.json", "w"), separators=(",", ":"), ensure_ascii=False)
print("compare tool data", flush=True)
