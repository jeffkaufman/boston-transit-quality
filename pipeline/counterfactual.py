"""Bus-speed counterfactual summary -> intermediates/speed_counterfactual.json.
Usage: counterfactual.py T_DIR   (T_DIR holds work/, histwork/, cfwork/ matrices; see run_all.sh)
cfwork/2026fast = 2026 schedule with bus run times scaled to 2010 speeds (scale_bus.py, k below);
cfwork/2010slow = 2010 schedule slowed to 2026 speeds."""
import json, sys
import numpy as np
T = sys.argv[1]
G = json.load(open("intermediates/grid.json"))
pop = np.array(G["pop"], float); jobs = np.array(G["jobs"], float); NC = len(pop)
# raptor's .m files: row 0 is each cell's mean trip to jobs; average it over residents
S = lambda p: float(np.average(np.fromfile(f"{T}/{p}").reshape(-1, NC)[0], weights=pop))
res = {k: round(S(p), 2) for k, p in (("2010", "histwork/2010/weekday_day.m"), ("2019", "histwork/2019/weekday_day.m"),
                                      ("2026", "work/weekday_day.m"), ("2026_at_2010_bus_speed", "cfwork/2026fast/m.m"),
                                      ("2010_at_2026_bus_speed", "cfwork/2010slow/m.m"))}
res["k"] = 13.70 / 16.76
print(res)
json.dump(res, open("intermediates/speed_counterfactual.json", "w"), indent=1)
