"""Build page data files. Usage: build.py DATA_DIR WORK_DIR INTERMEDIATES_DIR OUT_DIR"""
import csv, gzip, json, math, os, sys
from collections import Counter, defaultdict
import numpy as np
import shapefile

DATA, WORK, INTER, OUT = sys.argv[1:5]
os.makedirs(OUT, exist_ok=True)
g = json.load(open(f"{INTER}/grid.json"))
cells = np.array(g["cells"]); NC = len(cells)
pop = np.array(g["pop"], float); jobs = np.array(g["jobs"], float)
area = np.ones(NC)
# WORK/{period}.m files come from raptor: [18][NC] float64 (see raptor.cpp): mean
# trips out weighted by jobs/pop/area, trips in, then reachable shares. Rush hour = out 7-9am (am.m, trips out) averaged
# with back 4:30-6:30pm (pm.m, trips in to home).
PERIODS = [("weekday_day", "Weekday, 7am–7pm"), ("weekday_rush", "Weekday rush hour, out 7–9am and back 4:30–6:30pm"),
           ("weekday_eve", "Weekday evening, 7–11pm"),
           ("saturday", "Saturday, 9am–9pm"), ("sunday", "Sunday, 9am–9pm")]

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for reach.py under python -I
import reach as RCH  # noqa: E402  (pipeline/reach.py)

metrics = {}
summary = {}
reaches = {}
for key, _ in PERIODS:
    if key == "weekday_rush":
        am, pm = np.fromfile(f"{WORK}/am.m").reshape(-1, NC), np.fromfile(f"{WORK}/pm.m").reshape(-1, NC)
        X = (am[:3] + pm[3:6]) / 2
        reaches[key] = RCH.rounded(RCH.shares(am, pm))  # out in the morning, home in the evening
    else:
        X = np.fromfile(f"{WORK}/{key}.m").reshape(-1, NC)
        reaches[key] = RCH.rounded(RCH.shares(X))
        X = X[:3]
    m = {wname: np.round(X[j], 1).tolist() for j, wname in enumerate(("jobs", "pop", "area"))}
    metrics[key] = m
    # population-weighted average over origins of the jobs metric: one regional number
    summary[key] = {w: round(float(np.average(m[w], weights=pop)), 1) for w in m}
    print(key, summary[key], flush=True)

json.dump({"lat0": g["lat0"], "lon0": g["lon0"], "dlat": g["dlat"], "dlon": g["dlon"],
           "nrows": g["nrows"], "ncols": g["ncols"], "cells": g["cells"], "pop": g["pop"],
           "jobs": g["jobs"], "periods": PERIODS, "metrics": metrics, "summary": summary, "reach": reaches},
          open(f"{OUT}/grid.json", "w"), separators=(",", ":"))
json.dump(summary, open(f"{INTER}/summary.json", "w"), indent=1)

# ---------- water from Census blocks with no land ----------
B = (g["lat0"] - 0.03, g["lat0"] + g["nrows"] * g["dlat"] + 0.03,
     g["lon0"] - 0.04, g["lon0"] + g["ncols"] * g["dlon"] + 0.04)


def simplify(pts, tol):
    if len(pts) < 4:
        return pts
    pts = np.asarray(pts)
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        ab = b - a
        L = np.hypot(*ab) or 1e-12
        d = np.abs(ab[0] * (pts[i + 1:j, 1] - a[1]) - ab[1] * (pts[i + 1:j, 0] - a[0])) / L
        k = int(np.argmax(d))
        if d[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return pts[keep]


KX = math.cos(math.radians(42.35))
sf = shapefile.Reader(os.path.join(DATA, "tiger/tl_2020_25_tabblock20.shp"))
fi = {f[0]: i for i, f in enumerate(sf.fields[1:])}
rings = []
for sr in sf.iterShapeRecords():
    rec = sr.record
    # Water: blocks with no land, or nearly all water and unpopulated (e.g. a
    # bay block that includes a tiny island).
    al, aw = int(rec[fi["ALAND20"]]), int(rec[fi["AWATER20"]])
    if al != 0 and not (aw >= 20 * al and int(rec[fi["POP20"]]) == 0):
        continue
    bb = sr.shape.bbox  # lon0 lat0 lon1 lat1
    if bb[2] < B[2] or bb[0] > B[3] or bb[3] < B[0] or bb[1] > B[1]:
        continue
    parts = list(sr.shape.parts) + [len(sr.shape.points)]
    for a, b in zip(parts, parts[1:]):
        p = np.array(sr.shape.points[a:b])
        q = p.copy(); q[:, 0] *= KX
        far = int(np.argmax(np.hypot(*(q - q[0]).T)))
        s = np.vstack([simplify(q[:far + 1], 0.00006)[:-1], simplify(q[far:], 0.00006)])  # ~7m
        if len(s) >= 4:
            s[:, 0] /= KX
            rings.append([[round(x, 5), round(y, 5)] for x, y in s])
json.dump(rings, open(f"{OUT}/water.json", "w"), separators=(",", ":"))
print("water rings", len(rings), os.path.getsize(f"{OUT}/water.json") // 1024, "KB")

# ---------- transit lines from GTFS shapes ----------
G = os.path.join(DATA, "gtfs")


def rd(name):
    with open(os.path.join(G, name), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


routes = {r["route_id"]: r for r in rd("routes.txt")}
SL = set()  # Silver Line not drawn: it is a bus (it is still used for routing)
want = {rid for rid, r in routes.items() if r["route_type"] in ("0", "1", "2", "4") or rid in SL}
shape_count = Counter()
for r in rd("trips.txt"):
    if r["route_id"] in want and r["shape_id"]:
        shape_count[(r["route_id"], r["direction_id"], r["shape_id"])] += 1
# Keep, per route, all shapes with a decent share of trips so branches show.
by_route = defaultdict(list)
for (rid, d, sid), n in shape_count.items():
    by_route[rid].append((n, sid))
keep_shapes = {}
for rid, lst in by_route.items():
    tot = max(n for n, _ in lst)
    for n, sid in lst:
        if n >= 0.15 * tot:
            keep_shapes[sid] = rid
pts = defaultdict(list)
for r in rd("shapes.txt"):
    if r["shape_pt_sequence"] and r["shape_id"] in keep_shapes:
        pts[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
KIND = {"0": "lr", "1": "subway", "2": "cr", "4": "ferry", "3": "sl"}
lines = []
seen = set()
for sid, lst in pts.items():
    lst.sort()
    p = np.array([(x * KX, y) for _, x, y in lst])
    s = simplify(p, 0.00005)
    s[:, 0] /= KX
    coords = [[round(x, 5), round(y, 5)] for x, y in s]
    sig = (keep_shapes[sid], tuple(map(tuple, coords[:: max(1, len(coords) // 8)])))
    if sig in seen:
        continue
    seen.add(sig)
    r = routes[keep_shapes[sid]]
    lines.append({"r": r["route_id"], "n": r["route_long_name"] or r["route_short_name"],
                  "k": KIND[r["route_type"]], "c": "#" + (r["route_color"] or "888888"), "p": coords})
# draw order: ferry, cr, sl, lr, subway
order = {"ferry": 0, "cr": 1, "sl": 2, "lr": 3, "subway": 4}
lines.sort(key=lambda l: order[l["k"]])

# stations: parent stations served by subway/LR/CR/ferry/SL
stops = {r["stop_id"]: r for r in rd("stops.txt")}
route_stops = defaultdict(set)
trip_route = {r["trip_id"]: r["route_id"] for r in rd("trips.txt") if r["route_id"] in want}
for r in rd("stop_times.txt"):
    rid = trip_route.get(r["trip_id"])
    if rid:
        s = stops[r["stop_id"]]
        route_stops[s["parent_station"] or s["stop_id"]].add(rid)
stations = []
for sid, rids in route_stops.items():
    s = stops[sid]
    if not s["stop_lat"]:
        continue
    la, lo = float(s["stop_lat"]), float(s["stop_lon"])
    if not (B[0] < la < B[1] and B[2] < lo < B[3]):
        continue
    kinds = {KIND[routes[r]["route_type"]] if r not in SL else "sl" for r in rids}
    rank = 0 if kinds & {"subway", "lr"} else (1 if "cr" in kinds else 2)
    stations.append([s["stop_name"], round(la, 5), round(lo, 5), rank])
json.dump({"lines": lines, "stations": stations}, open(f"{OUT}/transit.json", "w"), separators=(",", ":"))
print("lines", len(lines), "stations", len(stations), os.path.getsize(f"{OUT}/transit.json") // 1024, "KB")
