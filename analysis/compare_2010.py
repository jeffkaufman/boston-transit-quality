"""Side-by-side: the 2010 post's colored map vs. this pipeline's 2010 'everywhere' metric,
recomputed over the original map's extent and drawn in the original's color bands.
Usage: compare_2010.py MATRIX_F32 ORIG_PNG OUT_PNG"""
import json, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
mat, orig, out = sys.argv[1:4]
G = json.load(open("intermediates/grid.json")); NC = len(G["cells"])
cells = np.array(G["cells"]); r, c = cells // G["ncols"], cells % G["ncols"]
lat = G["lat0"] + (r + .5) * G["dlat"]; lon = G["lon0"] + (c + .5) * G["dlon"]
# Georeference of the original image from its place labels (Boston, Waltham, Quincy, Medford): linear fit.
LON0, DLON, LAT0, DLAT = -71.245, 0.0003594, 42.437, -0.000257
W, H = 774, 757
lon1, lat1 = LON0 + DLON * W, LAT0 + DLAT * H
inside = (lon > LON0) & (lon < lon1) & (lat < LAT0) & (lat > lat1)
M = np.fromfile(mat, np.float32).reshape(NC, NC)
full = M.mean(axis=1)                       # everywhere, over this project's whole map
crop = M[:, inside].mean(axis=1)            # everywhere, over the original map's extent
BANDS = [(45, "#ff0000"), (50, "#ff8800"), (55, "#ffff00"), (60, "#c8f000"), (65, "#7cfc00"), (70, "#00c000"),
         (80, "#00b0a0"), (90, "#87cefa"), (100, "#4169e1"), (117, None)]
def colorize(v):
    img = np.ones((G["nrows"], G["ncols"], 4))
    img[..., 3] = 0
    for k in range(len(cells)):
        x = v[k]; col = BANDS[-2][1]
        for (lo, cl), (hi, _) in zip(BANDS, BANDS[1:]):
            if lo <= x < hi: col = cl; break
        if x < 45: col = BANDS[0][1]
        rgb = tuple(int(col[i:i + 2], 16) / 255 for i in (1, 3, 5))
        img[r[k], c[k]] = (*rgb, 0.6)
    return img
fig, axs = plt.subplots(1, 3, figsize=(18, 6.4), dpi=110)
axs[0].imshow(Image.open(orig)); axs[0].set_title("2010 post (tillberg's maps)")
ext = (G["lon0"], G["lon0"] + G["ncols"] * G["dlon"], G["lat0"], G["lat0"] + G["nrows"] * G["dlat"])
for ax, v, t in ((axs[1], crop, "This pipeline, Nov 2010 schedule,\neverywhere = original map's area"),
                 (axs[2], full, "This pipeline, Nov 2010 schedule,\neverywhere = this project's larger area")):
    ax.imshow(colorize(v), extent=ext, origin="lower", interpolation="nearest")
    ax.set_xlim(LON0, lon1); ax.set_ylim(lat1, LAT0); ax.set_aspect(1 / np.cos(np.radians(42.35))); ax.set_title(t)
for ax in axs: ax.set_xticks([]); ax.set_yticks([])
plt.tight_layout(); plt.savefig(out)
def at(la, lo): i = int(np.argmin(np.hypot(lat - la, (lon - lo) * .74))); return f"{crop[i]:.0f} / {full[i]:.0f}"
for n, p in {"Downtown": (42.3555, -71.0605), "Harvard": (42.3734, -71.1189), "Newton Ctr": (42.33, -71.192), "Hyde Park": (42.256, -71.124), "Winthrop": (42.376, -70.985), "Malden": (42.427, -71.074), "Quincy Ctr": (42.2518, -71.0054), "Waltham": (42.376, -71.236)}.items():
    print(f"{n:12} crop/full {at(*p)}")
