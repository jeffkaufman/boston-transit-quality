"""Count weekday 7am-7pm departures at stops matching names, per route.
Usage: count_deps.py GTFS_DIR YYYYMMDD "stop name substring" [...]"""
import csv, os, sys
from collections import Counter
from datetime import date as D

g, date, names = sys.argv[1], sys.argv[2], sys.argv[3:]


def rd(n):
    with open(os.path.join(g, n), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][D(int(date[:4]), int(date[4:6]), int(date[6:])).weekday()]
svcs = {r["service_id"] for r in rd("calendar.txt") if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
for r in rd("calendar_dates.txt"):
    if r["date"] == date:
        (svcs.add if r["exception_type"] == "1" else svcs.discard)(r["service_id"])
routes = {r["route_id"]: (r["route_short_name"] or r["route_long_name"]) for r in rd("routes.txt")}
trips = {r["trip_id"]: routes[r["route_id"]] for r in rd("trips.txt") if r["service_id"] in svcs}
stops = {r["stop_id"]: r["stop_name"] for r in rd("stops.txt")}
for name in names:
    ids = {s for s, n in stops.items() if name.lower() in n.lower()}
    c = Counter()
    for r in rd("stop_times.txt"):
        if r["stop_id"] in ids and r["trip_id"] in trips:
            h = int(r["departure_time"].split(":")[0])
            if 7 <= h < 19:
                c[trips[r["trip_id"]]] += 1
    print(f"  {name}: " + ", ".join(f"{k} {v}" for k, v in c.most_common(8)))
