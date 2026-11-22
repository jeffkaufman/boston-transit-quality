"""Compare jobs metric for cells near given points across years vs region.
Usage: area_compare.py HIST_JSON NAME:lat,lon[;lat,lon...] ... (radius 800m)"""
import json, sys, math
import numpy as np
G = json.load(open("intermediates/grid.json")); H = json.load(open(sys.argv[1]))
cells = np.array(G["cells"]); pop = np.array(G["pop"], float)
r, c = cells // G["ncols"], cells % G["ncols"]
lat = G["lat0"] + (r + .5) * G["dlat"]; lon = G["lon0"] + (c + .5) * G["dlon"]
YRS = ["2010", "2019", "2021", "2022", "2023", "2024", "2026"]
M = {y: np.array(H[y]["metrics"]["jobs"]) for y in YRS}
def wavg(m, sel): return (m[sel] * pop[sel]).sum() / pop[sel].sum()
print("area".ljust(22), " ".join(y.rjust(6) for y in YRS), "  pop")
print("region".ljust(22), " ".join(f"{wavg(M[y], pop > 0):6.1f}" for y in YRS))
for arg in sys.argv[2:]:
    name, pts = arg.split(":")
    sel = np.zeros(len(cells), bool)
    for p in pts.split(";"):
        la, lo = map(float, p.split(","))
        d = np.hypot((lat - la) * 111000, (lon - lo) * 111000 * math.cos(math.radians(la)))
        sel |= d < 800
    sel &= pop > 0
    print(name.ljust(22), " ".join(f"{wavg(M[y], sel):6.1f}" for y in YRS), f"  {int(pop[sel].sum())}")
