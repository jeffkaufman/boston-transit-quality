"""Compute weekday-daytime travel-time metrics for historical MBTA feeds.

Usage: hist.py DATA_DIR HIST_WORK_DIR INTERMEDIATES_DIR RAPTOR_BIN

For each year: prep.py on that feed (same grid, walk network, and population /
jobs weights as the current map), raptor for 7am-7pm on a mid-November
Tuesday, then the jobs/residents/area-weighted averages and that year's
transit lines. Writes HIST_WORK_DIR/hist.json and INTERMEDIATES_DIR/hist_summary.json.
"""
import csv, json, math, os, subprocess, sys
from collections import Counter, defaultdict
import numpy as np

DATA, HW, INTER, RAPTOR = sys.argv[1:5]
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
FEEDS = {  # year: (archive feed, service date)
    2009: ("20091106", "20091117"), 2010: ("20101119", "20101123"), 2011: ("20111117", "20111122"),
    2012: ("20121031", "20121120"), 2013: ("20131115", "20131119"), 2014: ("20140815", "20141118"),
    2015: ("20150821", "20151117"), 2016: ("20161103", "20161122"), 2017: ("20171114", "20171121"),
    2018: ("20181113", "20181120"), 2019: ("20191114", "20191119"), 2020: ("20201112", "20201117"),
    2021: ("20211116", "20211123"), 2022: ("20221121", "20221122"), 2023: ("20231116", "20231121"),
    # 2024 uses Nov 12: Nov 19 had a Red Line Broadway-Harvard shutdown.
    2024: ("20241112", "20241112"), 2025: ("20251118", "20251118"), 2026: (None, "20261201"),
}
# The 2009-2014 feeds omit the privately contracted routes 710, 712, 713 and 716
# (Winthrop's only buses). Use copies with those routes spliced in from the
# Dec 2014 feed (splice_routes.py), the earliest archived feed that has their trips.
for y in range(2009, 2015):
    FEEDS[y] = (FEEDS[y][0] + "-spliced", FEEDS[y][1])
grid = json.load(open(f"{INTER}/grid.json"))
NC = len(grid["cells"])
pop = np.array(grid["pop"], float); jobs = np.array(grid["jobs"], float)
KX = math.cos(math.radians(42.35))
LAT0, LAT1 = grid["lat0"] - 0.03, grid["lat0"] + grid["nrows"] * grid["dlat"] + 0.03
LON0, LON1 = grid["lon0"] - 0.04, grid["lon0"] + grid["ncols"] * grid["dlon"] + 0.04


def simplify(pts, tol):
    pts = np.asarray(pts)
    if len(pts) < 4:
        return pts
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]; ab = b - a; L = np.hypot(*ab) or 1e-12
        d = np.abs(ab[0] * (pts[i + 1:j, 1] - a[1]) - ab[1] * (pts[i + 1:j, 0] - a[0])) / L
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True; stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return pts[keep]


def rd(g, name):
    with open(os.path.join(g, name), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def lines_for(g, date):
    """Rapid transit, commuter rail, and ferry lines that ran on `date`."""
    from datetime import date as D
    y, m, d = int(date[:4]), int(date[4:6]), int(date[6:])
    dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][D(y, m, d).weekday()]
    svcs = {r["service_id"] for r in rd(g, "calendar.txt") if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
    if os.path.exists(os.path.join(g, "calendar_dates.txt")):
        for r in rd(g, "calendar_dates.txt"):
            if r["date"] == date:
                (svcs.add if r["exception_type"] == "1" else svcs.discard)(r["service_id"])
    routes = {r["route_id"]: r for r in rd(g, "routes.txt")}
    want = {rid for rid, r in routes.items() if r["route_type"] in ("0", "1", "2", "4")}
    cnt = Counter()
    for r in rd(g, "trips.txt"):
        if r["route_id"] in want and r.get("shape_id") and r["service_id"] in svcs:
            cnt[(r["route_id"], r["shape_id"])] += 1
    by_route = defaultdict(list)
    for (rid, sid), n in cnt.items():
        by_route[rid].append((n, sid))
    keep = {}
    for rid, lst in by_route.items():
        top = max(n for n, _ in lst)
        for n, sid in lst:
            if n >= 0.15 * top:
                keep[sid] = rid
    pts = defaultdict(list)
    for r in rd(g, "shapes.txt"):
        if r["shape_id"] in keep:
            pts[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
    kind = {"0": "lr", "1": "subway", "2": "cr", "4": "ferry"}
    out, seen = [], set()
    for sid, lst in pts.items():
        lst.sort()
        p = np.array([(x * KX, y) for _, x, y in lst])
        s = simplify(p, 0.00005); s[:, 0] /= KX
        coords = [[round(x, 5), round(y, 5)] for x, y in s]
        sig = tuple(map(tuple, coords[:: max(1, len(coords) // 8)]))
        if sig in seen:
            continue
        seen.add(sig)
        r = routes[keep[sid]]
        out.append({"k": kind[r["route_type"]], "c": "#" + (r.get("route_color") or "888888"), "p": coords})
    return out


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for reach.py under python -I
import reach as RCH  # noqa: E402  (pipeline/reach.py)


results = json.load(open(f"{HW}/hist.json")) if os.path.exists(f"{HW}/hist.json") else {}
for year, (feed, date) in FEEDS.items():
    if str(year) in results:
        continue
    g = os.path.join(DATA, "hist", feed) if feed else os.path.join(DATA, "gtfs")
    work = os.path.join(HW, str(year))
    os.makedirs(work, exist_ok=True)
    print(f"== {year} ({feed or 'current'}, {date})", flush=True)
    subprocess.run([PY, "-I", f"{HERE}/prep.py", DATA, work, INTER, g, json.dumps({"weekday": date})], check=True,
                   stdout=open(f"{work}/prep.log", "w"))
    print(open(f"{work}/prep.log").read().strip().splitlines()[-2], flush=True)
    # one pass over 7am-7pm also writes the two rush-hour windows
    mat, am, pm = (f"{work}/{n}.m" for n in ("weekday_day", "rush_am", "rush_pm"))
    subprocess.run([RAPTOR, work, "weekday", "25200", "68400", "300", mat, "25200", "32400", am, "59400", "66600", pm],
                   check=True, stderr=subprocess.DEVNULL)
    # raptor writes [6][NC]: trips out weighted by jobs/pop/area, then trips in
    X = np.fromfile(mat).reshape(-1, NC)
    m = {w: np.round(X[j], 1).tolist() for j, w in enumerate(("jobs", "pop", "area"))}
    summ = {w: round(float(np.average(m[w], weights=pop)), 1) for w in m}
    results[str(year)] = {"feed": feed, "date": date, "metrics": m, "summary": summ, "lines": lines_for(g, date),
                          "reach": RCH.rounded(RCH.shares(X))}
    # Rush-hour commute: home -> destination leaving 7-9am, averaged with destination ->
    # home leaving 4:30-6:30pm (the transposed evening matrix).
    A, P = np.fromfile(am).reshape(-1, NC), np.fromfile(pm).reshape(-1, NC)
    R = (A[:3] + P[3:6]) / 2
    mr = {w: np.round(R[j], 1).tolist() for j, w in enumerate(("jobs", "pop", "area"))}
    results[str(year)]["rush"] = {"metrics": mr, "summary": {w: round(float(np.average(mr[w], weights=pop)), 1) for w in mr},
                                  "reach": RCH.rounded(RCH.shares(A, P))}
    json.dump(results, open(f"{HW}/hist.json", "w"), separators=(",", ":"))
    print(year, summ, flush=True)

json.dump({y: {"date": r["date"], **r["summary"], "rush": r["rush"]["summary"]} for y, r in sorted(results.items())},
          open(f"{INTER}/hist_summary.json", "w"), indent=1)
