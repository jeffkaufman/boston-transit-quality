"""Scheduled bus speed (crow-flies stop-to-stop km / scheduled hours) for weekday
trips in the map area, overall and per route, by time band.
Usage: bus_speed.py GTFS_DIR YYYYMMDD -> JSON on stdout"""
import csv, json, math, os, sys
from collections import defaultdict
from datetime import date as D

g, date = sys.argv[1], sys.argv[2]
LAT0, LAT1, LON0, LON1 = 42.225, 42.475, -71.285, -70.925


def rd(n):
    with open(os.path.join(g, n), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][D(int(date[:4]), int(date[4:6]), int(date[6:])).weekday()]
svcs = {r["service_id"] for r in rd("calendar.txt") if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
for r in rd("calendar_dates.txt"):
    if r["date"] == date:
        (svcs.add if r["exception_type"] == "1" else svcs.discard)(r["service_id"])
routes = {r["route_id"]: r for r in rd("routes.txt")}
trips = {}
for r in rd("trips.txt"):
    rt = routes[r["route_id"]]
    if r["service_id"] in svcs and rt["route_type"] == "3":
        trips[r["trip_id"]] = rt["route_short_name"] or rt["route_long_name"]
stops = {r["stop_id"]: (float(r["stop_lat"]), float(r["stop_lon"])) for r in rd("stops.txt") if r["stop_lat"]}
seqs = defaultdict(list)
for r in rd("stop_times.txt"):
    if r["trip_id"] in trips and r["stop_id"] in stops:
        t = r["arrival_time"] or r["departure_time"]
        if not t:
            continue
        h, m, s = map(int, t.split(":"))
        seqs[r["trip_id"]].append((int(r["stop_sequence"]), h * 3600 + m * 60 + s, stops[r["stop_id"]]))


def km(a, b):
    return math.hypot((a[0] - b[0]) * 111.2, (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0])))


BANDS = {"am": (7, 9), "mid": (10, 15), "pm": (16, 18), "all": (7, 19)}
agg = defaultdict(lambda: [0.0, 0.0, 0])  # (band, route) -> km, hours, trips
for tid, seq in seqs.items():
    seq.sort()
    if len(seq) < 2:
        continue
    # only hops inside the box
    dist = tm = 0.0
    for (_, t0, p0), (_, t1, p1) in zip(seq, seq[1:]):
        if all(LAT0 < p[0] < LAT1 and LON0 < p[1] < LON1 for p in (p0, p1)) and t1 >= t0:
            dist += km(p0, p1); tm += (t1 - t0) / 3600
    if tm <= 0:
        continue
    hr = seq[0][1] / 3600
    for b, (lo, hi) in BANDS.items():
        if lo <= hr < hi:
            for key in ((b, "*"), (b, trips[tid])):
                a = agg[key]; a[0] += dist; a[1] += tm; a[2] += 1
out = defaultdict(dict)
for (b, rt), (d, h, n) in agg.items():
    out[b][rt] = [round(d / h, 2), n, round(h, 1)]
json.dump(out, sys.stdout)
