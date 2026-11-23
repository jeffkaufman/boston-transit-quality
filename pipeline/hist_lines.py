"""Transit lines for each history year, drawn consistently across years.

Usage: hist_lines.py DATA_DIR HIST_DIR   (rewrites the "lines" of HIST_DIR/hist.json)

Older feeds are uneven: 2010 has no shapes, 2009-2012 have none for commuter rail,
ferries have none before 2017, and some shapes have stray points far off the track.
So each year's lines are built from what actually ran that day (every pair of
consecutive stops served by a subway, light rail, commuter rail, or ferry trip), and
the track between each pair comes from a library of shapes from all feeds: that
year's own if it has a clean one, otherwise the nearest later year's (then earlier). Shapes are split
wherever consecutive points jump more than 2 km, which drops the stray points. A stop
matches a shape within 150 m (commuter rail 500 m, ferry 300 m), both ends on the same piece. A pair
no shape covers is drawn straight (mostly ferries before 2017). Colors are today's,
by line, so a line keeps its color in every year.
"""
import csv, json, math, os, sys
from collections import defaultdict
from datetime import date as D
import numpy as np
from scipy.spatial import cKDTree

DATA, HD = sys.argv[1:3]
FEEDS = {y: (f"{DATA}/hist/{feed}" if feed else f"{DATA}/gtfs", date)
         for y, (feed, date) in {
             2009: ("20091106-spliced", "20091117"), 2010: ("20101119-spliced", "20101123"),
             2011: ("20111117-spliced", "20111122"), 2012: ("20121031-spliced", "20121120"),
             2013: ("20131115-spliced", "20131119"), 2014: ("20140815-spliced", "20141118"),
             2015: ("20150821", "20151117"), 2016: ("20161103", "20161122"), 2017: ("20171114", "20171121"),
             2018: ("20181113", "20181120"), 2019: ("20191114", "20191119"), 2020: ("20201112", "20201117"),
             2021: ("20211116", "20211123"), 2022: ("20221121", "20221122"), 2023: ("20231116", "20231121"),
             2024: ("20241112", "20241112"), 2025: ("20251118", "20251118"), 2026: (None, "20261201")}.items()}
KX = math.cos(math.radians(42.35))
M_PER_DEG = 111_200.0
NEAR_M, JUMP_M = 500, 2000
# how far a stop may be from a shape of its kind (old feeds put some commuter rail stations
# at the building, a few hundred metres from the track)
NEAR_BY_KIND = {"lr": 150, "subway": 150, "cr": 500, "ferry": 300}
KIND = {"0": "lr", "1": "subway", "2": "cr", "4": "ferry"}
H = json.load(open(f"{HD}/hist.json"))
assert set(H) == {str(y) for y in FEEDS}, "hist.json years don't match FEEDS"


def rd(g, name):
    with open(os.path.join(g, name), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def family(r):
    name = (r.get("route_long_name") or "") + " " + (r.get("route_short_name") or "")
    if r["route_type"] == "2":
        return "cr"
    if r["route_type"] == "4":
        return "ferry"
    for f in ("Mattapan", "Red", "Orange", "Blue", "Green"):
        if f in name:
            return f
    return None


def xy(lon, lat):  # local metres
    return np.array([lon * KX * M_PER_DEG, lat * M_PER_DEG])


def services(g, date):
    dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][D(int(date[:4]), int(date[4:6]), int(date[6:])).weekday()]
    s = {r["service_id"] for r in rd(g, "calendar.txt") if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
    if os.path.exists(os.path.join(g, "calendar_dates.txt")):
        for r in rd(g, "calendar_dates.txt"):
            if r["date"] == date:
                (s.add if r["exception_type"] == "1" else s.discard)(r["service_id"])
    return s


# today's color for each line family
COLOR = {}
for r in rd(f"{DATA}/gtfs", "routes.txt"):
    f = family(r)
    if f and r.get("route_color") and f not in COLOR:
        COLOR[f] = "#" + r["route_color"]

# ---- library of clean shape pieces, from every feed, tagged with year and kind ----
lib_pts, lib_id, pieces = [], [], []  # pieces[i] = (year, kind, xy array)
segs = {}  # year -> {(kind, family): set of (stopA xy, stopB xy)}
for y, (g, date) in sorted(FEEDS.items()):
    routes = {r["route_id"]: r for r in rd(g, "routes.txt") if r["route_type"] in KIND}
    svc = services(g, date)
    trip_route, trip_shape = {}, {}
    for r in rd(g, "trips.txt"):
        if r["route_id"] in routes:
            if r.get("shape_id"):
                trip_shape[r["trip_id"]] = r["shape_id"]
            if r["service_id"] in svc:
                trip_route[r["trip_id"]] = r["route_id"]
    shape_kind = {}
    # kinds for shapes used by any trip (not just this day's), so the library is as full as possible
    for r in rd(g, "trips.txt"):
        if r["route_id"] in routes and r.get("shape_id"):
            shape_kind.setdefault(r["shape_id"], KIND[routes[r["route_id"]]["route_type"]])
    pts = defaultdict(list)
    if os.path.exists(os.path.join(g, "shapes.txt")):
        for r in rd(g, "shapes.txt"):
            if r["shape_id"] in shape_kind:
                pts[r["shape_id"]].append((int(r["shape_pt_sequence"]), float(r["shape_pt_lon"]), float(r["shape_pt_lat"])))
    for sid, lst in pts.items():
        lst.sort()
        p = np.array([xy(lon, lat) for _, lon, lat in lst])
        cut = np.where(np.hypot(*np.diff(p, axis=0).T) > JUMP_M)[0] + 1
        for part in np.split(p, cut):
            if len(part) >= 2:
                lib_pts.append(part); lib_id += [len(pieces)] * len(part)
                pieces.append((y, shape_kind[sid], part))
    # what ran: consecutive stop pairs of this day's trips
    stops = {r["stop_id"]: xy(float(r["stop_lon"]), float(r["stop_lat"])) for r in rd(g, "stops.txt") if r.get("stop_lat")}
    seq = defaultdict(list)
    for r in rd(g, "stop_times.txt"):
        if r["trip_id"] in trip_route:
            seq[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"]))
    pairs = defaultdict(set)
    for t, lst in seq.items():
        r = routes[trip_route[t]]
        key = (KIND[r["route_type"]], family(r))
        lst.sort()
        for (_, a), (_, b) in zip(lst, lst[1:]):
            if a in stops and b in stops and a != b:
                pa, pb = tuple(np.round(stops[a], 1)), tuple(np.round(stops[b], 1))
                pairs[key].add(min(pa, pb) + max(pa, pb))
    segs[y] = pairs
    print(y, "pieces", len(pieces), "pairs", sum(len(v) for v in pairs.values()), flush=True)

ALL = np.concatenate(lib_pts); IDS = np.array(lib_id)
OFF = np.r_[0, np.cumsum([len(p) for p in lib_pts])]  # piece i's points are ALL[OFF[i]:OFF[i+1]]
tree = cKDTree(ALL)
near_cache = {}


def near(p):
    """{piece: (index within piece, distance)} for pieces passing within NEAR_M of p."""
    if p not in near_cache:
        best = {}
        for j in tree.query_ball_point(p, NEAR_M):
            i = IDS[j]; d = float(np.hypot(*(ALL[j] - p)))
            if i not in best or d < best[i][1]:
                best[i] = (j - OFF[i], d)
        near_cache[p] = best
    return near_cache[p]


def snap(p, kind):
    """A stop with no shape of its kind nearby (bad coordinates in an old feed) moves to the
    nearest point of such a shape within 1.5 km."""
    if any(pieces[i][1] == kind and d <= NEAR_BY_KIND[kind] for i, (_, d) in near(p).items()):
        return p
    js = [j for j in tree.query_ball_point(p, 1500) if pieces[IDS[j]][1] == kind]
    return tuple(ALL[min(js, key=lambda j: np.hypot(*(ALL[j] - p)))]) if js else p


def track(y, kind, a, b):
    a, b = snap(a, kind), snap(b, kind)
    na, nb = near(a), near(b)
    straight = math.dist(a, b)
    cands = []
    for i in set(na) & set(nb):
        py, pk, p = pieces[i]
        if pk != kind or max(na[i][1], nb[i][1]) > NEAR_BY_KIND[kind]:
            continue
        ia, ib = na[i][0], nb[i][0]
        if ia == ib:
            continue
        seg = p[min(ia, ib):max(ia, ib) + 1]
        length = float(np.hypot(*np.diff(seg, axis=0).T).sum())
        if length > 2.5 * straight + 500:  # went the long way round a loop
            continue
        # this year's shape first, then later years (nearest first), then earlier ones
        cands.append((0 if py == y else 1 if py > y else 2, abs(py - y), na[i][1] + nb[i][1], seg if ia < ib else seg[::-1]))
    if not cands:
        return None
    return min(cands, key=lambda c: c[:3])[3]


def simplify(pts, tol):
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


for y in sorted(FEEDS):
    out, straight_n = [], 0
    for (kind, fam), prs in sorted(segs[y].items(), key=lambda kv: str(kv[0])):
        color = COLOR.get(fam if kind in ("lr", "subway") else kind, "#888888")
        for pr in sorted(prs):
            a, b = np.array(pr[:2]), np.array(pr[2:])
            t = track(y, kind, tuple(a), tuple(b))
            if t is None:
                if os.environ.get("TQ_DEBUG") and kind != "ferry":
                    na, nb = near(tuple(a)), near(tuple(b))
                    common = [i for i in set(na) & set(nb) if pieces[i][1] == kind]
                    print("  straight", y, kind, fam, [round(float(v) / M_PER_DEG / (KX if k % 2 == 0 else 1), 5) for k, v in enumerate(pr)],
                          f"{math.dist(a, b):.0f} m; pieces near a {len(na)}, b {len(nb)}, both+kind {len(common)}")
                t = np.array([a, b]); straight_n += 1
            t = np.vstack([a, t, b])  # meet the stops exactly
            t = simplify(t, 5.0)
            coords = [[round(float(px) / (KX * M_PER_DEG), 5), round(float(py) / M_PER_DEG, 5)] for px, py in t]
            out.append({"k": kind, "c": color, "p": coords})
    H[str(y)]["lines"] = out
    print(y, len(out), "segments,", straight_n, "drawn straight", flush=True)
json.dump(H, open(f"{HD}/hist.json", "w"), separators=(",", ":"))
