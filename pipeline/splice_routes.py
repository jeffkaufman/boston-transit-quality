"""Copy an old GTFS feed and add routes missing from it, taken from a donor feed.
The donor's trips that run on DONOR_DATE are added as running on TARGET_DATE
(via a new service_id in calendar_dates.txt).
Usage: splice_routes.py OLD_DIR DONOR_DIR DONOR_DATE TARGET_DATE OUT_DIR ROUTE [ROUTE...]
Used for 2009-2014: those feeds omit the contracted routes 710/712/713/716."""
import csv, os, shutil, sys
from datetime import date as D
old, donor, ddate, tdate, out, *want = sys.argv[1:]
os.makedirs(out, exist_ok=True)


def rows(d, n):
    p = os.path.join(d, n)
    if not os.path.exists(p):
        return [], []
    with open(p, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f); return r.fieldnames, list(r)


def svcs_on(d, date):
    dow = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][D(int(date[:4]), int(date[4:6]), int(date[6:])).weekday()]
    s = {r["service_id"] for r in rows(d, "calendar.txt")[1] if r["start_date"] <= date <= r["end_date"] and r[dow] == "1"}
    for r in rows(d, "calendar_dates.txt")[1]:
        if r["date"] == date:
            (s.add if r["exception_type"] == "1" else s.discard)(r["service_id"])
    return s


dsv = svcs_on(donor, ddate)
_, droutes = rows(donor, "routes.txt")
add_routes = [r for r in droutes if r["route_short_name"] in want]
rids = {r["route_id"] for r in add_routes}
_, dtrips = rows(donor, "trips.txt")
add_trips = [r for r in dtrips if r["route_id"] in rids and r["service_id"] in dsv]
tids = {r["trip_id"] for r in add_trips}
_, dst = rows(donor, "stop_times.txt")
add_st = [r for r in dst if r["trip_id"] in tids]
_, dstops = rows(donor, "stops.txt")
need = {r["stop_id"] for r in add_st}
SVC, PFX = "SPLICED-" + ddate, "spliced-"
for name in sorted(os.listdir(old)):
    hdr, rs = rows(old, name) if name.endswith(".txt") else (None, None)
    extra = []
    if name == "routes.txt":
        extra = [dict(r, route_id=PFX + r["route_id"]) for r in add_routes]
    elif name == "trips.txt":
        extra = [dict(r, route_id=PFX + r["route_id"], trip_id=PFX + r["trip_id"], service_id=SVC, shape_id="") for r in add_trips]
    elif name == "stop_times.txt":
        extra = [dict(r, trip_id=PFX + r["trip_id"]) for r in add_st]
    elif name == "stops.txt":
        have = {r["stop_id"] for r in rs}
        extra = [dict(r, parent_station="") for r in dstops if r["stop_id"] in need and r["stop_id"] not in have]
    elif name == "calendar_dates.txt":
        extra = [{"service_id": SVC, "date": tdate, "exception_type": "1"}]
    if hdr is None or not extra:
        shutil.copy(os.path.join(old, name), os.path.join(out, name)); continue
    with open(os.path.join(out, name), "w", newline="") as f:
        w = csv.DictWriter(f, hdr, extrasaction="ignore", restval=""); w.writeheader()
        w.writerows(rs); w.writerows(extra)
    print(f"{name}: +{len(extra)}")
