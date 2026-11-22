"""Spot-check travel times between known places. Usage: check.py GRID_JSON MATRIX"""
import json, sys
import numpy as np

g = json.load(open(sys.argv[1]))
cells = np.array(g["cells"])
M = np.fromfile(sys.argv[2], dtype=np.float32).reshape(len(cells), len(cells))
r, c = cells // g["ncols"], cells % g["ncols"]
clat = g["lat0"] + (r + 0.5) * g["dlat"]
clon = g["lon0"] + (c + 0.5) * g["dlon"]
P = {
    "Harvard Sq": (42.3734, -71.1189), "Downtown Crossing": (42.3555, -71.0603),
    "Kendall": (42.3625, -71.0862), "Davis": (42.3967, -71.1218),
    "Logan/Airport stn": (42.3743, -71.0304), "Mattapan": (42.2676, -71.0924),
    "Waltham center": (42.3765, -71.2361), "Back Bay": (42.3473, -71.0752),
    "Ruggles": (42.3364, -71.0890), "West Medford": (42.4211, -71.1328),
    "Copley": (42.3500, -71.0775), "Revere Beach": (42.4078, -70.9925),
}
idx = {k: int(np.argmin((clat - a) ** 2 + ((clon - b) * 0.74) ** 2)) for k, (a, b) in P.items()}
pairs = [("Harvard Sq", "Downtown Crossing"), ("Davis", "Kendall"), ("Harvard Sq", "Logan/Airport stn"),
         ("Mattapan", "Downtown Crossing"), ("Waltham center", "Back Bay"), ("Ruggles", "Harvard Sq"),
         ("West Medford", "Copley"), ("Revere Beach", "Kendall"), ("Davis", "Mattapan")]
for a, b in pairs:
    print(f"{a:>18} -> {b:<18} {M[idx[a], idx[b]]:5.1f} min   (reverse {M[idx[b], idx[a]]:5.1f})")
avg = M.mean(axis=1)
print("area-avg range", avg.min(), avg.max())
for k in P:
    print(f"{k:>18} avg to everywhere {avg[idx[k]]:5.1f}")
