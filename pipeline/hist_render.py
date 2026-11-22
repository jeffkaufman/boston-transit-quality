"""Render history images: one map per year plus change maps, for two measures.

Usage: TQ_SITE=SITE_DIR hist_render.py HIST_JSON OUT_DIR
Maps have no lines or place names; pages overlay labels.png from render.py and
lines-{year}.png (each year's lines, written here; change maps use the later year's).
Measures: rush hour (default; files without suffix) and all day 7am-7pm ("-allday").
"""
import json, os, sys
from datetime import date as D
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R  # noqa: E402

H = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
os.makedirs(OUT, exist_ok=True)


def nice_date(s):
    return D(int(s[:4]), int(s[4:6]), int(s[6:])).strftime("%b %-d, %Y")


SUB = "today's population, jobs, streets"
MEASURES = {  # suffix: (metrics getter, title phrase, time window text)
    "": (lambda r: r["rush"]["metrics"], "Rush-hour commute to a typical job", "Weekday, out 7–9am, back 4:30–6:30pm"),
    "-allday": (lambda r: r["metrics"], "Average transit trip to a typical job", "Weekday 7am–7pm"),
}
for year, r in sorted(H.items()):
    R.overlay(f"{OUT}/lines-{year}", R.project_lines(r["lines"]))
print("line overlays", flush=True)
for suf, (get, phrase, window) in MEASURES.items():
    for year, r in sorted(H.items()):
        R.draw(R.time_image(get(r)["jobs"], "jobs"), [],
               f"{phrase}, {year}",
               f"{window}  ·  MBTA schedule for Tuesday {nice_date(r['date'])}  ·  {SUB}",
               R.time_legend("jobs"), f"{OUT}/year-{year}{suf}", labels=False)
    print("years", suf or "rush", flush=True)

    # Diverging change maps: purple = faster, orange = slower (ColorBrewer PuOr).
    EDGES = [-15, -10, -6, -3, -1, 1, 3, 6, 10, 15]
    HEX = ["#2d004b", "#542788", "#8073ac", "#b2abd2", "#d8daeb", "#ededea", "#fee0b6", "#fdb863", "#e08214", "#b35806", "#7f3b08"]
    RGB = [tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in HEX]
    for base, to in (("2009", "2026"), ("2019", "2026")):
        a = np.array(get(H[base])["jobs"]); b = np.array(get(H[to])["jobs"])
        d = b - a
        idx = np.searchsorted(EDGES, d, side="right")
        idx = np.where((d > -1) & (d <= 1), 5, idx)  # values exactly on +1 belong to the middle band
        alphas = np.where((a >= 179.5) & (b >= 179.5), 0.0, 0.93)
        legend = dict(colors=HEX, ticks=[(k + 1, f"{e:+d}" if e else "0") for k, e in enumerate(EDGES)],
                      right=None, caption="Change in minutes  ·  purple: faster  ·  orange: slower")
        R.draw(R.cells_image([RGB[i] for i in idx], alphas), [],
               f"Change in {phrase[0].lower() + phrase[1:]}, {base} to {to}",
               f"{window}  ·  MBTA schedules: {nice_date(H[base]['date'])} and {nice_date(H[to]['date'])}  ·  {SUB}",
               legend, f"{OUT}/change-{base}-{to}{suf}", labels=False)
        w = np.array(R.G["pop"], float)
        print(f"{suf or 'rush'} {base}->{to}: residents in faster squares {w[d < -1].sum() / w.sum():.0%}, slower {w[d > 1].sum() / w.sum():.0%}", flush=True)

# ---- Reachable shares at rush hour (45 minutes), from hist.py's kept .m files ----
import reach as RCH  # noqa: E402
HW = os.path.dirname(os.path.abspath(sys.argv[1]))
NC = len(R.G["cells"])
RS = {y: RCH.hist_rush(HW, y, NC) for y in sorted(H)}
for key in ("jobs45", "res45"):
    noun = "jobs" if key.startswith("jobs") else "residents"
    for year, r in sorted(H.items()):
        R.draw(R.share_image(RS[year][key]), [], f"{R.reach_title(key)}, {year}",
               f"Weekday rush hour, round trip  ·  MBTA schedule for Tuesday {nice_date(r['date'])}  ·  {SUB}",
               R.share_legend(key), f"{OUT}/year-{year}-{key}", labels=False)
    # change in percentage points: purple = more within reach, orange = fewer
    EDGES = [-15, -10, -6, -3, -1, 1, 3, 6, 10, 15]
    HEX = ["#2d004b", "#542788", "#8073ac", "#b2abd2", "#d8daeb", "#ededea", "#fee0b6", "#fdb863", "#e08214", "#b35806", "#7f3b08"]
    RGB = [tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in HEX]
    for base, to in (("2009", "2026"), ("2019", "2026")):
        d = -(np.array(RS[to][key]) - np.array(RS[base][key]))  # negate so gains land on the purple side
        idx = np.searchsorted(EDGES, d, side="right")
        idx = np.where((d > -1) & (d <= 1), 5, idx)
        legend = dict(colors=HEX, ticks=[(k + 1, f"{-e:+d}" if e else "0") for k, e in enumerate(EDGES)], right=None,
                      caption=f"Change in percentage points of the region's {noun}  ·  purple: more  ·  orange: fewer")
        R.draw(R.cells_image([RGB[i] for i in idx], np.full(NC, 0.93)), [],
               f"Change in {R.reach_title(key)[0].lower() + R.reach_title(key)[1:]}, {base} to {to}",
               f"Weekday rush hour, round trip  ·  MBTA schedules: {nice_date(H[base]['date'])} and {nice_date(H[to]['date'])}  ·  {SUB}",
               legend, f"{OUT}/change-{base}-{to}-{key}", labels=False)
    print("reach maps", key, flush=True)

# ---- Transit area for homes, 2009 vs 2026 ----
TH = RCH.TRANSIT_AREA_PCT
in0, in1 = np.array(RS["2009"]["jobs45"]) >= TH, np.array(RS["2026"]["jobs45"]) >= TH
BOTH, LOSS, GAIN = "#9aa3a6", "#e08214", "#8073ac"
cols = [BOTH if a and b else LOSS if a else GAIN for a, b in zip(in0, in1)]
R.draw(R.cells_image([tuple(int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)) for h in cols], np.where(in0 | in1, 0.9, 0.0)), [],
       "The transit area, 2009 and 2026",
       f"Homes from which at least {TH}% of the region's jobs are within a 45-minute rush-hour commute  ·  {SUB}",
       dict(colors=[BOTH, LOSS, GAIN], ticks=[], right=None,
            caption="Gray: in both years  ·  orange: dropped out by 2026  ·  purple: joined by 2026"),
       f"{OUT}/area-2009-2026", labels=False)
print("area map", flush=True)
