"""Diagnostic (not for publication): match the 2010 post's map as closely as possible.
Reads band values back out of the original image by hue, computes this pipeline's
'everywhere' metric over the original map's extent, and renders original / ours / difference.
Usage: diag_2010.py ORIG_PNG OUT_PREFIX MATRIX_F32 [LABEL MATRIX_F32 ...]"""
import json, sys
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mc
from PIL import Image
orig_png, out = sys.argv[1:3]
import os
TITLE_OURS = os.environ.get("TQ_TITLE", "This pipeline, Nov 23 2010 schedule, 7am-7pm,\neverywhere = the original map's area")
variants = [("current method", sys.argv[3])] + list(zip(sys.argv[4::2], sys.argv[5::2]))
G = json.load(open("intermediates/grid.json")); NC = len(G["cells"])
cells = np.array(G["cells"]); r, c = cells // G["ncols"], cells % G["ncols"]
lat = G["lat0"] + (r + .5) * G["dlat"]; lon = G["lon0"] + (c + .5) * G["dlon"]
LON0, DLON, LAT0, DLAT = -71.245, 0.0003594, 42.437, -0.000257   # fit from the image's place labels
im = np.array(Image.open(orig_png).convert("RGB")).astype(float) / 255
Hh, Ww = im.shape[:2]
hsv = mc.rgb_to_hsv(im); hue = hsv[..., 0] * 360; sat = hsv[..., 1]
px = ((lon - LON0) / DLON).astype(int); py = ((lat - LAT0) / DLAT).astype(int)
inside = (px >= 7) & (px < Ww - 7) & (py >= 7) & (py < Hh - 7)
# band midpoints for the nine hues (0,30,...,240 degrees)
MID = np.array([47.5, 52.5, 57.5, 62.5, 67.5, 75, 85, 95, 108.5])
orig = np.full(NC, np.nan)
for k in np.where(inside)[0]:
    blk = (slice(py[k] - 6, py[k] + 7), slice(px[k] - 6, px[k] + 7))
    hh = hue[blk][sat[blk] > 0.3]
    if len(hh) < 40: continue
    hh = np.where(hh > 300, hh - 360, hh)               # reds near 360 -> negative
    idx = np.clip(np.round(hh / 30), 0, 8).astype(int)
    orig[k] = MID[np.bincount(idx, minlength=9).argmax()]   # modal band in the block
sel = inside & ~np.isnan(orig) & (np.array(G["pop"]) >= 0)
dest = inside   # 'everywhere' = points of the original map
res = {}
for name, path in variants:
    M = np.fromfile(path, np.float32).reshape(NC, NC)
    ours = M[:, dest].mean(axis=1)
    d = ours - orig
    res[name] = (ours, d)
    print(f"{name:28} mean diff {np.nanmean(d[sel]):+5.1f}  median {np.nanmedian(d[sel]):+5.1f}  "
          f"MAE {np.nanmean(np.abs(d[sel])):4.1f}  corr {np.corrcoef(ours[sel], orig[sel])[0, 1]:.3f}")
HUES = [mc.hsv_to_rgb((h / 360, .55, .95)) for h in range(0, 241, 30)]
def band_img(v):
    img = np.zeros((G["nrows"], G["ncols"], 4))
    edges = [50, 55, 60, 65, 70, 80, 90, 100]
    for k in np.where(inside & ~np.isnan(v))[0]:
        img[r[k], c[k]] = (*HUES[int(np.searchsorted(edges, v[k], side="right"))], 1)
    return img
def diff_img(d):
    img = np.zeros((G["nrows"], G["ncols"], 4)); cm = plt.get_cmap("PuOr_r")
    for k in np.where(sel)[0]:
        img[r[k], c[k]] = cm(np.clip((d[k] + 20) / 40, 0, 1))
    return img
ext = (G["lon0"], G["lon0"] + G["ncols"] * G["dlon"], G["lat0"], G["lat0"] + G["nrows"] * G["dlat"])
ours, d = res["current method"]
fig, axs = plt.subplots(2, 2, figsize=(14, 13.5), dpi=100)
axs[0, 0].imshow(Image.open(orig_png)); axs[0, 0].set_title("2010 post (original image)")
panels = [(axs[0, 1], band_img(orig), "Original, read back from the image's colors (400m squares)"),
          (axs[1, 0], band_img(ours), TITLE_OURS),
          (axs[1, 1], diff_img(d), "Difference: this pipeline minus original (minutes)\norange = this pipeline slower, purple = faster")]
LABELS = {"Boston": (42.3555, -71.0605), "Cambridge": (42.3736, -71.1097), "Somerville": (42.3876, -71.0995), "Medford": (42.4184, -71.1062),
          "Malden": (42.4251, -71.0662), "Chelsea": (42.3918, -71.0328), "Revere": (42.4084, -71.0120), "Winthrop": (42.3760, -70.9850),
          "Arlington": (42.4154, -71.1565), "Belmont": (42.3960, -71.1780), "Waltham": (42.3765, -71.2356), "Watertown": (42.3709, -71.1828),
          "Newton": (42.3370, -71.2092), "Brookline": (42.3318, -71.1212), "Roxbury": (42.3152, -71.0914), "Dorchester": (42.3016, -71.0676),
          "Jamaica Plain": (42.3097, -71.1151), "W Roxbury": (42.2793, -71.1495), "Hyde Park": (42.2557, -71.1245), "Mattapan": (42.2676, -71.0924),
          "Milton": (42.2496, -71.0662), "Quincy": (42.2529, -71.0023), "E Boston": (42.3702, -71.0389), "S Boston": (42.3381, -71.0476)}
for ax, img, t in panels:
    ax.imshow(img, extent=ext, origin="lower", interpolation="nearest")
    ax.set_xlim(LON0, LON0 + DLON * Ww); ax.set_ylim(LAT0 + DLAT * Hh, LAT0)
    ax.set_aspect(1 / np.cos(np.radians(42.35))); ax.set_title(t)
    for n, (la, lo) in LABELS.items():
        ax.text(lo, la, n, fontsize=7, ha="center", va="center", color="#111",
                bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.6))
for ax in axs.flat: ax.set_xticks([]); ax.set_yticks([])
sm = plt.cm.ScalarMappable(cmap="PuOr_r", norm=plt.Normalize(-20, 20))
fig.colorbar(sm, ax=axs[1, 1], fraction=0.04, pad=0.02, label="minutes")
plt.tight_layout()
# Exact pixel width (blog images should be multiples of 550px); default 2200.
plt.savefig(out + ".png", dpi=int(os.environ.get("TQ_WIDTH_PX", 2200)) / fig.get_figwidth())
# biggest disagreements, clustered by label
print("largest disagreements (this pipeline minus original):")
o = np.argsort(-np.abs(np.nan_to_num(d) * sel))
for k in o[:25]:
    near = min(LABELS, key=lambda n: (LABELS[n][0] - lat[k]) ** 2 + ((LABELS[n][1] - lon[k]) * .74) ** 2)
    print(f"  {lat[k]:.4f},{lon[k]:.4f} near {near:12} ours {ours[k]:5.1f} orig {orig[k]:5.1f} diff {d[k]:+5.1f}")
json.dump({"orig_est": np.nan_to_num(orig, nan=-1).round(1).tolist(), "ours": ours.round(1).tolist()}, open(out + ".json", "w"))
