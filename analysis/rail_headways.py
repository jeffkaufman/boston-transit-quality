"""Departures per hour (7-19) of a route from stops matching a name; also median
scheduled run time between two stop names. Usage: rail_headways.py GTFS DATE ROUTE_SUBSTR FROM TO"""
import csv, os, sys
from collections import Counter, defaultdict
from datetime import date as D
g, date, rsub, A, B = sys.argv[1:6]
def rd(n):
    with open(os.path.join(g, n), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)
dow = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][D(int(date[:4]), int(date[4:6]), int(date[6:])).weekday()]
svcs = {r["service_id"] for r in rd("calendar.txt") if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
for r in rd("calendar_dates.txt"):
    if r["date"] == date: (svcs.add if r["exception_type"] == "1" else svcs.discard)(r["service_id"])
routes = {r["route_id"] for r in rd("routes.txt") if rsub.lower() in (r["route_long_name"] + " " + r["route_short_name"] + " " + r["route_id"]).lower()}
trips = {r["trip_id"] for r in rd("trips.txt") if r["service_id"] in svcs and r["route_id"] in routes}
names = {r["stop_id"]: r["stop_name"] for r in rd("stops.txt")}
st = defaultdict(dict)
for r in rd("stop_times.txt"):
    if r["trip_id"] in trips:
        n = names.get(r["stop_id"], "")
        sec = lambda t: (lambda h, m, s: h*3600+m*60+s)(*map(int, t.split(":")))
        for key in (A, B):
            if key.lower() in n.lower():
                st[r["trip_id"]][key] = (int(r["stop_sequence"]), sec(r["departure_time"] or r["arrival_time"]))
deps = Counter(); runs = []
for t, d in st.items():
    if A in d and B in d and d[A][0] < d[B][0] and 7*3600 <= d[A][1] < 19*3600:
        deps[d[A][1] // 3600] += 1; runs.append((d[B][1] - d[A][1]) / 60)
runs.sort()
print(date, rsub, f"{A}->{B}: deps/hr", [deps[h] for h in range(7, 19)], "total", sum(deps.values()), "median run", runs[len(runs)//2] if runs else None)
