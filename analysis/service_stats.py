"""Weekday 7am-7pm service in the map area, by mode and by route.
Usage: service_stats.py GTFS_DIR YYYYMMDD [OUT_JSON]"""
import csv, json, os, sys
from collections import Counter
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
MODE = {"0": "light rail", "1": "subway", "2": "commuter rail", "3": "bus", "4": "ferry"}
trips = {r["trip_id"]: r["route_id"] for r in rd("trips.txt") if r["service_id"] in svcs}
inbox = set()
for r in rd("stops.txt"):
    if r["stop_lat"] and LAT0 < float(r["stop_lat"]) < LAT1 and LON0 < float(r["stop_lon"]) < LON1:
        inbox.add(r["stop_id"])
freq = {}
if os.path.exists(os.path.join(g, "frequencies.txt")):
    for r in rd("frequencies.txt"):
        h = lambda s: int(s.split(":")[0]) * 3600 + int(s.split(":")[1]) * 60
        freq[r["trip_id"]] = freq.get(r["trip_id"], 0) + max(1, (h(r["end_time"]) - h(r["start_time"])) // int(r["headway_secs"]))
mode_events, route_events = Counter(), Counter()
for r in rd("stop_times.txt"):
    rid = trips.get(r["trip_id"])
    if rid and r["stop_id"] in inbox and 7 <= int(r["departure_time"].split(":")[0]) < 19:
        n = freq.get(r["trip_id"], 1)
        mode_events[MODE.get(routes[rid]["route_type"], "other")] += n
        name = routes[rid]["route_short_name"] or routes[rid]["route_long_name"]
        route_events[name] += n
out = {"modes": dict(mode_events), "routes": dict(route_events)}
print(date, {k: v for k, v in sorted(mode_events.items())})
if len(sys.argv) > 3:
    json.dump(out, open(sys.argv[3], "w"))
