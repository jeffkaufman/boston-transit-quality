"""Pull what the history pages need out of hist.py's working files into a small directory
(see histdata.py), so pages can be rebuilt without the multi-GB working directory.

Usage: hist_extract.py HISTWORK OUT_DIR   (run from the repo root; reads intermediates/grid.json)
"""
import json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import histdata  # noqa: E402
import reach as RCH  # noqa: E402

HW, OUT = sys.argv[1:3]
os.makedirs(OUT, exist_ok=True)
G = json.load(open("intermediates/grid.json"))
pop = np.array(G["pop"], float); jobs = np.array(G["jobs"], float); NC = len(pop)
H = json.load(open(f"{HW}/hist.json"))
slim, curves = {}, {}
for y, r in sorted(H.items()):
    slim[y] = {"feed": r["feed"], "date": r["date"], "summary": r["summary"],
               "rush": {"summary": r["rush"]["summary"]}, "lines": []}  # hist_lines.py fills these
    mins, cj, cr = RCH.hist_curve(HW, y, NC)
    curves[y] = [np.r_[0, mins].tolist(), np.round(np.r_[0, (cj * pop).sum(1) / pop.sum()], 3).tolist(),
                 np.round(np.r_[0, (cr * jobs).sum(1) / jobs.sum()], 3).tolist()]
    s = RCH.hist_rush(HW, y, NC)
    histdata.save_cells(OUT, y, {"rush": r["rush"]["metrics"]["jobs"], "day": r["metrics"]["jobs"],
                                 "jobs45": s["jobs45"], "res45": s["res45"]})
json.dump(slim, open(f"{OUT}/hist.json", "w"), separators=(",", ":"))
json.dump(curves, open(f"{OUT}/curves.json", "w"), separators=(",", ":"))
print("wrote", OUT, sum(os.path.getsize(f"{OUT}/{f}") for f in os.listdir(OUT)) // 1024, "KB")
