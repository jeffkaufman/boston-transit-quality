"""Copy a GTFS feed, stretching every bus trip's running time by factor K
(times measured from the trip's first stop). Usage: scale_bus.py SRC DST K"""
import csv, os, sys
src, dst, k = sys.argv[1], sys.argv[2], float(sys.argv[3])
os.makedirs(dst, exist_ok=True)
for f in os.listdir(src):
    if f != "stop_times.txt" and not os.path.exists(os.path.join(dst, f)):
        os.symlink(os.path.join(src, f), os.path.join(dst, f))


def rd(n):
    with open(os.path.join(src, n), newline="", encoding="utf-8-sig") as f:
        yield from csv.DictReader(f)


bus_routes = {r["route_id"] for r in rd("routes.txt") if r["route_type"] == "3"}
bus_trips = {r["trip_id"] for r in rd("trips.txt") if r["route_id"] in bus_routes}
sec = lambda t: (lambda h, m, s: h * 3600 + m * 60 + s)(*map(int, t.split(":")))
fmt = lambda s: f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"
first = {}
for r in rd("stop_times.txt"):
    if r["trip_id"] in bus_trips and r["departure_time"]:
        t = sec(r["departure_time"])
        if t < first.get(r["trip_id"], 10 ** 9):
            first[r["trip_id"]] = t
with open(os.path.join(src, "stop_times.txt"), newline="", encoding="utf-8-sig") as fi, \
        open(os.path.join(dst, "stop_times.txt"), "w", newline="") as fo:
    rdr = csv.DictReader(fi); w = csv.DictWriter(fo, rdr.fieldnames); w.writeheader()
    for r in rdr:
        t0 = first.get(r["trip_id"])
        if t0 is not None:
            for c in ("arrival_time", "departure_time"):
                if r[c]:
                    r[c] = fmt(round(t0 + (sec(r[c]) - t0) * k))
        w.writerow(r)
print("scaled", len(first), "bus trips by", k)
