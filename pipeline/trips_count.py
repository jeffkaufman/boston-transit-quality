import csv, os, sys
from collections import Counter, defaultdict
from datetime import date as D
g, date = sys.argv[1], sys.argv[2]
def rd(n):
    with open(os.path.join(g, n), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)
dow = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"][D(int(date[:4]),int(date[4:6]),int(date[6:])).weekday()]
svcs = {r["service_id"] for r in rd("calendar.txt") if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
for r in rd("calendar_dates.txt"):
    if r["date"] == date: (svcs.add if r["exception_type"] == "1" else svcs.discard)(r["service_id"])
routes = {r["route_id"]: r for r in rd("routes.txt")}
trips = {r["trip_id"]: r["route_id"] for r in rd("trips.txt") if r["service_id"] in svcs}
first = {}; span = defaultdict(lambda: [10**9, 0])
for r in rd("stop_times.txt"):
    t = r["trip_id"]
    if t in trips:
        h, m, s = map(int, r["departure_time"].split(":")); x = h*3600+m*60+s
        sp = span[t]; sp[0] = min(sp[0], x); sp[1] = max(sp[1], x)
cnt = Counter(); hours = Counter()
for t, (a, b) in span.items():
    if 7*3600 <= a < 19*3600:
        rt = routes[trips[t]]
        mode = {"3": "bus"}.get(rt["route_type"], "rail/ferry")
        name = rt["route_short_name"] or rt["route_long_name"]
        cnt[name] += 1; hours[mode] += (b - a) / 3600
        cnt["ALL " + mode] += 1
print(date, " ".join(f"{k}={cnt[k]}" for k in ["ALL bus","ALL rail/ferry","1","15","22","23","28","32","39","57","66","70","73","77","111","116","117"]), f"bus_hours={hours['bus']:.0f}")
