"""Characterize 2009->2026 change in the rush-hour jobs metric by place type.
Usage: change_breakdown.py HIST_JSON GTFS_2009 GTFS_2026 OUT_JSON"""
import csv, json, math, os, sys
import numpy as np
H = json.load(open(sys.argv[1])); g09, g26, OUT = sys.argv[2:5]
G = json.load(open("intermediates/grid.json"))
pop = np.array(G["pop"], float); cells = np.array(G["cells"]); r, c = cells // G["ncols"], cells % G["ncols"]
lat = G["lat0"] + (r + .5) * G["dlat"]; lon = G["lon0"] + (c + .5) * G["dlon"]
KX = math.cos(math.radians(42.35))
def dist_m(la, lo): return np.hypot((lat - la) * 111200, (lon - lo) * 111200 * KX)
def stations(g, types):
    rd = lambda n: csv.DictReader(open(os.path.join(g, n), newline="", encoding="utf-8-sig"))
    routes = {x["route_id"] for x in rd("routes.txt") if x["route_type"] in types}
    trips = {x["trip_id"] for x in rd("trips.txt") if x["route_id"] in routes}
    used = {x["stop_id"] for x in rd("stop_times.txt") if x["trip_id"] in trips}
    return [(float(x["stop_lat"]), float(x["stop_lon"])) for x in rd("stops.txt") if x["stop_id"] in used and x["stop_lat"]]
def near(pts, m=800):
    d = np.full(len(cells), 1e9)
    for la, lo in pts: d = np.minimum(d, dist_m(la, lo))
    return d < m
rt09, rt26 = near(stations(g09, {"0", "1"})), near(stations(g26, {"0", "1"}))
cr09 = near(stations(g09, {"2"}))
cls = np.where(rt09, "rapid transit (2009)", np.where(rt26, "rapid transit added since", np.where(cr09, "commuter rail only", "bus only")))
M = lambda y, k="rush": np.array(H[y]["rush"]["metrics"]["jobs"] if k == "rush" else H[y]["metrics"]["jobs"])
out = {}
for k in ("rush", "day"):
    a, b = M("2009", k), M("2026", k); d = b - a
    ok = (pop > 0) & (a < 179.5) & (b < 179.5)
    w = lambda sel: pop[sel & ok]
    def stats(sel):
        s = sel & ok; o = np.argsort(d[s]); cw = np.cumsum(pop[s][o]) / pop[s].sum()
        q = lambda p: float(d[s][o][np.searchsorted(cw, p)])
        return dict(pop=int(pop[s].sum()), mean=round(float(np.average(d[s], weights=pop[s])), 1), p25=round(q(.25), 1), med=round(q(.5), 1), p75=round(q(.75), 1))
    res = {"class": {n: stats(cls == n) for n in np.unique(cls)}}
    # baseline deciles by 2009 time (pop-weighted)
    o = np.argsort(a[ok]); cw = np.cumsum(pop[ok][o]) / pop[ok].sum()
    edges = [float(a[ok][o][np.searchsorted(cw, p)]) for p in np.linspace(0, 1, 11)[1:-1]]
    dec = np.searchsorted(edges, a)
    res["baseline_decile"] = [dict(range=f"{(edges[i-1] if i else a[ok].min()):.0f}-{(edges[i] if i < 9 else a[ok].max()):.0f}", **stats(dec == i)) for i in range(10)]
    dd = dist_m(42.3564, -71.0624) / 1609  # Park Street station
    rings = [0, 2, 4, 6, 8, 10, 13]
    res["miles_from_downtown"] = [dict(range=f"{rings[i]}-{rings[i+1]}", **stats((dd >= rings[i]) & (dd < rings[i + 1]))) for i in range(len(rings) - 1)]
    # spread over time: resident percentiles
    pct = {}
    for y in sorted(H):
        m = M(y, k); s = (pop > 0); o = np.argsort(m[s]); cw = np.cumsum(pop[s][o]) / pop[s].sum()
        pct[y] = [round(float(m[s][o][np.searchsorted(cw, p)]), 1) for p in (.1, .25, .5, .75, .9)]
    res["percentiles_p10_p25_p50_p75_p90"] = pct
    # mean change since 2009 by access class, every year
    ts = {}
    for n in np.unique(cls):
        ts[n] = {}
        for y in sorted(H):
            m = M(y, k); s_ = (cls == n) & (pop > 0) & (a < 179.5) & (m < 179.5)
            ts[n][y] = round(float(np.average(m[s_] - a[s_], weights=pop[s_])), 2)
    res["class_series"] = ts
    out[k] = res
json.dump(out, open(OUT, "w"), indent=1)
r = out["rush"]
for n, s in r["class"].items(): print(f"{n:28} {s}")
print("baseline decile (2009 rush minutes) -> change")
for s in r["baseline_decile"]: print(" ", s)
print("miles from downtown")
for s in r["miles_from_downtown"]: print(" ", s)
print("percentiles"); [print(" ", y, v) for y, v in r["percentiles_p10_p25_p50_p75_p90"].items()]
