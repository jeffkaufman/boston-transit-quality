"""Preprocess inputs for the transit service quality map.

Usage: python prep.py DATA_DIR WORK_DIR INTERMEDIATES_DIR

Writes binary inputs for raptor.cpp to WORK_DIR and small summaries to
INTERMEDIATES_DIR.
"""
import csv, gzip, json, math, os, sys
from collections import defaultdict
import numpy as np
import shapefile
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

DATA, WORK, INTER = sys.argv[1:4]
# Optional: a different GTFS directory and {day_name: YYYYMMDD} (for historical feeds).
GTFS_DIR = sys.argv[4] if len(sys.argv) > 4 else os.path.join(DATA, "gtfs")
DAYS_OVERRIDE = json.loads(sys.argv[5]) if len(sys.argv) > 5 else None
os.makedirs(WORK, exist_ok=True)
os.makedirs(INTER, exist_ok=True)

# Map area: roughly the 2010 map (Waltham to Winthrop, Medford to Milton), a
# little larger.
LAT0, LAT1 = 42.225, 42.475
LON0, LON1 = -71.285, -70.925
CELL_M = float(os.environ.get("TQ_CELL_M", 400))  # grid square size in metres
REF_LAT = 42.35
M_PER_DEG_LAT = 111_132.0
M_PER_DEG_LON = 111_320.0 * math.cos(math.radians(REF_LAT))
DLAT = CELL_M / M_PER_DEG_LAT
DLON = CELL_M / M_PER_DEG_LON
NROWS = int(round((LAT1 - LAT0) / DLAT))
NCOLS = int(round((LON1 - LON0) / DLON))

# Stops can be a bit outside the map so routes through the edges work.
SLAT0, SLAT1, SLON0, SLON1 = 42.19, 42.51, -71.31, -70.89

DAYS = {"weekday": "20261201", "saturday": "20261205", "sunday": "20261206"}
if DAYS_OVERRIDE:
    DAYS = DAYS_OVERRIDE


def xy(lat, lon):
    return ((np.asarray(lon) - LON0) * M_PER_DEG_LON,
            (np.asarray(lat) - LAT0) * M_PER_DEG_LAT)


# ---------------- walking network ----------------
print("loading OSM", flush=True)
osm = json.load(open(os.path.join(DATA, "osm/walk.json")))
node_ll = {}
ways = []
for el in osm["elements"]:
    if el["type"] == "node":
        node_ll[el["id"]] = (el["lat"], el["lon"])
    elif el["type"] == "way":
        ways.append(el["nodes"])
del osm
ids = list(node_ll)
idx = {n: i for i, n in enumerate(ids)}
lat = np.array([node_ll[n][0] for n in ids])
lon = np.array([node_ll[n][1] for n in ids])
nx_, ny_ = xy(lat, lon)
a, b = [], []
for w in ways:
    for u, v in zip(w, w[1:]):
        if u in idx and v in idx and u != v:
            a.append(idx[u]); b.append(idx[v])
a = np.array(a); b = np.array(b)
length = np.hypot(nx_[a] - nx_[b], ny_[a] - ny_[b])
n = len(ids)
g = coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n))
ncomp, labels = connected_components(g, directed=False)
big = np.bincount(labels).argmax()
keep = labels == big
remap = -np.ones(n, dtype=np.int64)
remap[keep] = np.arange(keep.sum())
ek = keep[a] & keep[b]
a, b, length = remap[a[ek]], remap[b[ek]], length[ek]
nx_, ny_, lat, lon = nx_[keep], ny_[keep], lat[keep], lon[keep]
n = int(keep.sum())
print(f"walk graph: {n} nodes, {len(a)} edges", flush=True)
# undirected CSR
src = np.concatenate([a, b]); dst = np.concatenate([b, a]); ln = np.concatenate([length, length])
order = np.argsort(src, kind="stable")
src, dst, ln = src[order], dst[order], ln[order]
offs = np.zeros(n + 1, dtype=np.int64)
np.add.at(offs, src + 1, 1)
offs = np.cumsum(offs)
offs.astype(np.int32).tofile(f"{WORK}/g_offs.i32")
dst.astype(np.int32).tofile(f"{WORK}/g_dst.i32")
np.round(ln).astype(np.int32).tofile(f"{WORK}/g_len.i32")
tree = cKDTree(np.c_[nx_, ny_])

# ---------------- grid ----------------
rows, cols = np.meshgrid(np.arange(NROWS), np.arange(NCOLS), indexing="ij")
clat = LAT0 + (rows + 0.5) * DLAT
clon = LON0 + (cols + 0.5) * DLON
cx, cy = xy(clat.ravel(), clon.ravel())
snapd, snapn = tree.query(np.c_[cx, cy])
# Land/walkable mask: a cell counts if it contains walkable-network nodes and
# its center is near one. This cuts out water and big inaccessible areas.
cellof = (np.floor((ny_) / (DLAT * M_PER_DEG_LAT)).astype(int) * NCOLS
          + np.floor(nx_ / (DLON * M_PER_DEG_LON)).astype(int))
inb = (nx_ >= 0) & (ny_ >= 0) & (nx_ < NCOLS * CELL_M) & (ny_ < NROWS * CELL_M)
cnt = np.bincount(cellof[inb], minlength=NROWS * NCOLS)
valid = (cnt >= 3) & (snapd < 160)
cell_ids = np.flatnonzero(valid)
NC = len(cell_ids)
print(f"grid {NROWS}x{NCOLS}, {NC} valid cells", flush=True)
np.array([NC], dtype=np.int32).tofile(f"{WORK}/cells_n.i32")
snapn[cell_ids].astype(np.int32).tofile(f"{WORK}/cell_node.i32")
np.round(snapd[cell_ids]).astype(np.int32).tofile(f"{WORK}/cell_snap.i32")

# ---------------- population and jobs ----------------
print("population/jobs", flush=True)
sf = shapefile.Reader(os.path.join(DATA, "tiger/tl_2020_25_tabblock20.shp"))
fields = [f[0] for f in sf.fields[1:]]
fi = {f: i for i, f in enumerate(fields)}
blk = {}
for rec in sf.iterRecords():
    la = float(rec[fi["INTPTLAT20"]]); lo = float(rec[fi["INTPTLON20"]])
    if LAT0 - 0.01 < la < LAT1 + 0.01 and LON0 - 0.01 < lo < LON1 + 0.01:
        blk[rec[fi["GEOID20"]]] = (la, lo, int(rec[fi["POP20"]]))
jobs = {}
with gzip.open(os.path.join(DATA, "lodes/wac.csv.gz"), "rt") as f:
    for r in csv.DictReader(f):
        if r["w_geocode"] in blk:
            jobs[r["w_geocode"]] = int(r["C000"])
vcx, vcy = cx[cell_ids], cy[cell_ids]
vtree = cKDTree(np.c_[vcx, vcy])
pop = np.zeros(NC); job = np.zeros(NC)
bl = np.array([(v[0], v[1]) for v in blk.values()])
bx, by = xy(bl[:, 0], bl[:, 1])
inside = (bx >= 0) & (by >= 0) & (bx < NCOLS * CELL_M) & (by < NROWS * CELL_M)
_, near = vtree.query(np.c_[bx, by])
for (gid, (la, lo, p)), ins, k in zip(blk.items(), inside, near):
    if ins:
        pop[k] += p
        job[k] += jobs.get(gid, 0)
print(f"pop {pop.sum():.0f}, jobs {job.sum():.0f}", flush=True)
# per-cell weights for raptor's weighted averages: jobs, residents, area
np.c_[job, pop, np.ones(NC)].T.astype(np.float64).tofile(f"{WORK}/weights.f64")

# ---------------- GTFS ----------------
G = GTFS_DIR


def rd(name):
    with open(os.path.join(G, name), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


def services_on(date):
    from datetime import date as D
    y, m, d = int(date[:4]), int(date[4:6]), int(date[6:])
    dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][D(y, m, d).weekday()]
    s = set()
    for r in rd("calendar.txt"):
        if r["start_date"] <= date <= r["end_date"] and r[dow] == "1":
            s.add(r["service_id"])
    for r in rd("calendar_dates.txt"):
        if r["date"] == date:
            (s.add if r["exception_type"] == "1" else s.discard)(r["service_id"])
    return s


stops_ll = {}
stop_name = {}
stop_parent = {}
for r in rd("stops.txt"):
    if r.get("parent_station"):
        stop_parent[r["stop_id"]] = r["parent_station"]
    if r["stop_lat"]:
        stops_ll[r["stop_id"]] = (float(r["stop_lat"]), float(r["stop_lon"]))
        stop_name[r["stop_id"]] = r["stop_name"]
route_type = {r["route_id"]: int(r["route_type"]) for r in rd("routes.txt")}
trips = {}
for r in rd("trips.txt"):
    trips[r["trip_id"]] = (r["service_id"], r["route_id"])
day_services = {k: services_on(v) for k, v in DAYS.items()}
all_services = set().union(*day_services.values())
print({k: len(v) for k, v in day_services.items()}, flush=True)


def tsec(s):
    h, m, x = s.split(":")
    return int(h) * 3600 + int(m) * 60 + int(x)


print("reading stop_times", flush=True)
st = defaultdict(list)
for r in rd("stop_times.txt"):
    t = trips.get(r["trip_id"])
    if t and t[0] in all_services:
        st[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"], tsec(r["arrival_time"]),
                                 tsec(r["departure_time"]), r.get("pickup_type") == "1", r.get("drop_off_type") == "1"))

# Expand frequency-based trips (older feeds) into individual trips.
if os.path.exists(os.path.join(G, "frequencies.txt")):
    nexp = 0
    for r in rd("frequencies.txt"):
        tid = r["trip_id"]
        if tid not in st:
            continue
        tmpl = sorted(st[tid])
        t0 = tmpl[0][3]
        start, end, hw = tsec(r["start_time"]), tsec(r["end_time"]), int(r["headway_secs"])
        for k, dep in enumerate(range(start, end, hw)):
            new = f"{tid}#f{start}-{k}"
            trips[new] = trips[tid]
            st[new] = [(sq, s, a - t0 + dep, d - t0 + dep, pu, do) for sq, s, a, d, pu, do in tmpl]
            nexp += 1
        del st[tid]
    print(f"expanded {nexp} frequency-based trips", flush=True)

# Stops: every stop served in the stop bounding box.
used = set()
for tid, lst in st.items():
    for _, s, *_ in lst:
        used.add(s)
stop_ids = sorted(s for s in used if s in stops_ll
                  and SLAT0 < stops_ll[s][0] < SLAT1 and SLON0 < stops_ll[s][1] < SLON1)
sidx = {s: i for i, s in enumerate(stop_ids)}
NS = len(stop_ids)
sll = np.array([stops_ll[s] for s in stop_ids])
sx, sy = xy(sll[:, 0], sll[:, 1])
sd, sn = tree.query(np.c_[sx, sy])
np.array([NS], dtype=np.int32).tofile(f"{WORK}/stops_n.i32")
sn.astype(np.int32).tofile(f"{WORK}/stop_node.i32")
np.round(sd).astype(np.int32).tofile(f"{WORK}/stop_snap.i32")
print(f"{NS} stops, max snap {sd.max():.0f}m", flush=True)

# Transfers inside a station (stops sharing a GTFS parent_station). OSM rarely has
# the paths inside stations, so the street network can turn an 80m platform-to-
# busway walk into 500m+. Give these pairs 1.5x the straight-line distance; the
# router uses whichever of this and the street-network walk is shorter.
by_parent = defaultdict(list)
for s_ in stop_ids:
    if s_ in stop_parent:
        by_parent[stop_parent[s_]].append(sidx[s_])
sx_ = []
for grp in by_parent.values():
    for i in grp:
        for j in grp:
            if i != j:
                sx_ += [i, j, int(round(1.5 * math.hypot(sx[i] - sx[j], sy[i] - sy[j])))]
np.array(sx_, dtype=np.int32).tofile(f"{WORK}/station_xfers.i32")
print(f"{len(sx_) // 3} in-station transfer pairs", flush=True)

for day, svcs in day_services.items():
    pats = defaultdict(list)  # key -> list of (times...)
    for tid, lst in st.items():
        if trips[tid][0] not in svcs:
            continue
        lst.sort()
        lst = [x for x in lst if x[1] in sidx]
        if len(lst) < 2:
            continue
        key = (trips[tid][1],) + tuple((sidx[s], pu, do) for _, s, _, _, pu, do in lst)
        pats[key].append([(ar, de) for _, _, ar, de, _, _ in lst])
    # split into FIFO sub-patterns
    out_pats = []
    for key, tl in pats.items():
        tl.sort(key=lambda t: t[0][1])
        subs = []
        for t in tl:
            for sub in subs:
                last = sub[-1]
                if all(t[i][0] >= last[i][0] and t[i][1] >= last[i][1] for i in range(len(t))):
                    sub.append(t); break
            else:
                subs.append([t])
        for sub in subs:
            out_pats.append((key, sub))
    p_off = [0]; p_stops = []; p_flags = []; p_toff = [0]; times = []; p_route = []
    rids = sorted({k[0] for k, _ in out_pats})
    ridx = {r: i for i, r in enumerate(rids)}
    for key, sub in out_pats:
        for s, pu, do in key[1:]:
            p_stops.append(s); p_flags.append(int(pu) | (int(do) << 1))
        p_off.append(len(p_stops))
        for t in sub:
            for ar, de in t:
                times.extend((ar, de))
        p_toff.append(len(times))
        p_route.append(ridx[key[0]])
    pre = f"{WORK}/{day}_"
    np.array([len(out_pats)], dtype=np.int32).tofile(pre + "np.i32")
    np.array(p_off, dtype=np.int32).tofile(pre + "p_off.i32")
    np.array(p_stops, dtype=np.int32).tofile(pre + "p_stops.i32")
    np.array(p_flags, dtype=np.int32).tofile(pre + "p_flags.i32")
    np.array(p_toff, dtype=np.int32).tofile(pre + "p_toff.i32")
    np.array(times, dtype=np.int32).tofile(pre + "times.i32")
    ntrips = sum(len(s) for _, s in out_pats)
    print(f"{day}: {len(out_pats)} patterns, {ntrips} trips, {len(times)//2} stop events", flush=True)

if not DAYS_OVERRIDE:
  json.dump({
    "lat0": LAT0, "lon0": LON0, "dlat": DLAT, "dlon": DLON, "nrows": NROWS, "ncols": NCOLS,
    "cells": cell_ids.tolist(), "pop": pop.round().astype(int).tolist(), "jobs": job.round().astype(int).tolist(),
    "days": DAYS,
}, open(f"{INTER}/grid.json", "w"))
json.dump({"stops": [[s, stop_name[s], round(stops_ll[s][0], 6), round(stops_ll[s][1], 6)] for s in stop_ids]},
          open(f"{WORK}/stops.json", "w"))
print("done")
