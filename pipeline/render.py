"""Render static map PNGs for the blog version.

Usage: render.py SITE_DIR OUT_DIR

Reads grid.json, transit.json, water.json from SITE_DIR (output of build.py)
and writes {metric}-{period}.png (1100px wide) and -big.png (2200px wide).
"""
import json, math, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, patheffects
from matplotlib.path import Path
from matplotlib.patches import PathPatch, Rectangle
from PIL import Image

SITE = sys.argv[1] if __name__ == "__main__" else os.environ["TQ_SITE"]
OUT = sys.argv[2] if __name__ == "__main__" else None
if OUT:
    os.makedirs(OUT, exist_ok=True)
FD = "/System/Library/Fonts/Supplemental/"
for f in ("Arial.ttf", "Arial Bold.ttf", "Arial Narrow Bold.ttf"):  # macOS fonts; others fall back
    if os.path.exists(FD + f):
        font_manager.fontManager.addfont(FD + f)
plt.rcParams["font.family"] = "Arial"

G = json.load(open(f"{SITE}/grid.json"))
T = json.load(open(f"{SITE}/transit.json"))
W = json.load(open(f"{SITE}/water.json"))
NR, NCOL = G["nrows"], G["ncols"]
cells = np.array(G["cells"]); rows, cols = cells // NCOL, cells % NCOL
latTop = G["lat0"] + NR * G["dlat"]

LAND, WATER, INK, MUTED, HALO = "#e6e6e0", "#c6d3d9", "#1c2225", "#5a6468", "#fbfbf9"
BANDS = {"jobs": (35, 5, 16), "pop": (45, 5, 16), "area": (65, 5, 16)}
METRIC_TITLE = {"jobs": "Average transit trip to a typical job",
                "pop": "Average transit trip to where a typical resident lives",
                "area": "Average transit trip to anywhere on the map"}
PERIOD_TITLE = dict(G["periods"])
LABELS = [["Cambridge",42.3744,-71.1192,0],["Dedham",42.2439,-71.1747,0],["Winthrop",42.3745,-70.9766,0],["Milton",42.2585,-71.0695,0],["Brookline",42.3324,-71.1295,0],["Needham",42.294,-71.2356,0],["Arlington",42.4173,-71.1627,0],["Belmont",42.3885,-71.1685,0],["Medford",42.4153,-71.106,0],["Somerville",42.3888,-71.1011,0],["Quincy",42.255,-71.0124,0],["Watertown",42.3666,-71.1853,0],["Revere",42.4145,-71.0094,0],["Chelsea",42.3958,-71.0334,0],["Malden",42.4288,-71.0615,0],["Everett",42.4087,-71.0524,0],["Melrose",42.4555,-71.0647,0],["Waltham",42.3763,-71.2402,0],["Nahant",42.4278,-70.9341,0],["Winchester",42.4483,-71.1403,0],["Newton",42.3432,-71.2067,0],["Saugus",42.4573,-71.0093,0],["Lexington",42.4419,-71.2342,0],["Downtown",42.3555,-71.0602,1],["Back Bay",42.3473,-71.0757,1],["Charlestown",42.3736,-71.0695,1],["East Boston",42.3691,-71.0395,1],["South Boston",42.3365,-71.047,1],["Dorchester",42.3001,-71.0617,1],["Roxbury",42.3195,-71.088,1],["Jamaica Plain",42.3105,-71.1074,1],["Roslindale",42.2874,-71.1303,1],["West Roxbury",42.2814,-71.1601,1],["Hyde Park",42.255,-71.1255,1],["Mattapan",42.2676,-71.0925,1],["Allston",42.3555,-71.13,1],["Brighton",42.3465,-71.1560,1],["Fenway",42.3430,-71.1000,1],["South End",42.3405,-71.0725,1]]


def proj(lat, lon):
    return (np.asarray(lon) - G["lon0"]) / G["dlon"], (latTop - np.asarray(lat)) / G["dlat"]


def oklch(L, C, h):
    a, b = C * math.cos(math.radians(h)), C * math.sin(math.radians(h))
    l_, m_, s_ = L + .3963377774 * a + .2158037573 * b, L - .1055613458 * a - .0638541728 * b, L - .0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    lin = [4.0767416621 * l - 3.3077115913 * m + .2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - .3413193965 * s,
           -.0041960863 * l - .7034186147 * m + 1.7076147010 * s]
    return [max(0, min(1, (12.92 * v if v <= .0031308 else 1.055 * v ** (1 / 2.4) - .055))) for v in (max(0, min(1, x)) for x in lin)]


def ramp(n):  # light-theme color ramp
    return [oklch(.38 + .56 * t, .15 - .115 * t, 36 + 40 * t) for t in (i / (n - 1) for i in range(n))]


# Water as one compound path (shapefile ring orientation makes islands holes under nonzero fill).
verts, codes = [], []
for ring in W:
    x, y = proj([p[1] for p in ring], [p[0] for p in ring])
    verts += list(zip(x, y)); codes += [Path.MOVETO] + [Path.LINETO] * (len(ring) - 2) + [Path.CLOSEPOLY]
water_path = Path(verts, codes)
def project_lines(raw):
    out = []
    for l in raw:
        x, y = proj([p[1] for p in l["p"]], [p[0] for p in l["p"]])
        out.append((x, y, l["c"], l["k"]))
    return out


lines = project_lines(T["lines"])
WIDTH = {"subway": 1.3, "lr": 1.1, "cr": 0.8, "sl": 0.8, "ferry": 0.7}
ORDER = {"ferry": 0, "cr": 1, "sl": 2, "lr": 3, "subway": 4}

MAP_W = 5.5                    # inches; dpi 200 -> 1100 px, shown at 550 CSS px
MAP_H = MAP_W * NR / NCOL
HEAD, FOOT = 0.46, 0.62
FIG_H = HEAD + MAP_H + FOOT


def _cell_mask():
    m = np.zeros((NR, NCOL), bool)
    m[NR - 1 - np.asarray(rows), np.asarray(cols)] = True
    return m


is_cell = _cell_mask()


def cells_image(colors, alphas):
    """colors: per-cell RGB (0-1); alphas: per-cell alpha."""
    img = np.zeros((NR, NCOL, 4))
    for i in range(len(cells)):
        r = NR - 1 - rows[i]
        img[r, cols[i], :3] = colors[i]
        img[r, cols[i], 3] = alphas[i]
    # Fill small holes: grid squares that aren't cells (no walkable network near
    # their center, common for small squares inside large blocks) take the most
    # common color of their neighbors when most neighbors are cells. Display only;
    # their residents and jobs already count toward the nearest cell.
    for _ in range(2):
        filled = img.copy()
        for r in range(NR):
            for c in range(NCOL):
                if is_cell[r, c] or img[r, c, 3] > 0:
                    continue
                nb = [tuple(img[rr, cc]) for rr in range(max(r - 1, 0), min(r + 2, NR))
                      for cc in range(max(c - 1, 0), min(c + 2, NCOL)) if (rr, cc) != (r, c) and img[rr, cc, 3] > 0]
                if len(nb) >= 5:
                    filled[r, c] = max(set(nb), key=nb.count)
        img = filled
    return img


def draw(img, line_list, title, subtitle, legend, out_base, labels=True):
    """legend: dict(colors=[...], ticks=[(index, text)], right=str, caption=str)."""
    fig = plt.figure(figsize=(MAP_W, FIG_H), dpi=200, facecolor="white")
    ax = fig.add_axes([0, FOOT / FIG_H, 1, MAP_H / FIG_H])
    ax.set_xlim(0, NCOL); ax.set_ylim(NR, 0); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), NCOL, NR, facecolor=LAND, edgecolor="none", zorder=0))
    ax.imshow(img, extent=(0, NCOL, NR, 0), interpolation="nearest", zorder=1)
    ax.add_patch(PathPatch(water_path, facecolor=WATER, edgecolor="none", zorder=2))
    halo = [patheffects.withStroke(linewidth=2, foreground=HALO)]
    for x, y, c, k in sorted(line_list, key=lambda t: ORDER[t[3]]):
        ax.plot(x, y, color=HALO, lw=WIDTH[k] + 1.1, solid_capstyle="round", solid_joinstyle="round", zorder=3)
    for x, y, c, k in sorted(line_list, key=lambda t: ORDER[t[3]]):
        ax.plot(x, y, color=c, lw=WIDTH[k], ls=(0, (2.5, 1.5)) if k == "ferry" else "-",
                solid_capstyle="round", solid_joinstyle="round", zorder=4)
    for name, la, lo_, kind in (LABELS if labels else []):
        x, y = proj(la, lo_)
        if kind:
            ax.text(x, y, name, fontsize=5.6, color=MUTED, ha="center", va="center", zorder=5, path_effects=halo)
        else:
            ax.text(x, y, name.upper(), fontsize=6.4, family="Arial Narrow", weight="bold", color=INK,
                    ha="center", va="center", zorder=5, path_effects=halo)
    fig.text(0.012, 1 - 0.17 / FIG_H, title, fontsize=10.5, weight="bold", color=INK, va="center")
    fig.text(0.012, 1 - 0.36 / FIG_H, subtitle, fontsize=6.6, color=MUTED, va="center")
    n = len(legend["colors"])
    lx, lw_, ly, lh = 0.012, 0.56, 0.31 / FIG_H, 0.11 / FIG_H
    for k, c in enumerate(legend["colors"]):
        fig.patches.append(Rectangle((lx + lw_ * k / n, ly), lw_ / n, lh, transform=fig.transFigure,
                                     facecolor=c, edgecolor="none"))
    for k, t in legend["ticks"]:
        fig.text(lx + lw_ * k / n, ly - 0.03 / FIG_H, t, fontsize=6.4, color=MUTED, ha="center", va="top")
    if legend.get("right"):
        fig.text(lx + lw_ + 0.006, ly + lh / 2, legend["right"], fontsize=6.4, color=MUTED, va="center")
    fig.text(lx, ly + lh + 0.05 / FIG_H, legend["caption"], fontsize=6.4, color=MUTED, va="bottom")
    fig.text(0.988, 0.12 / FIG_H, "Data: MBTA GTFS, OpenStreetMap contributors, US Census",
             fontsize=5.4, color=MUTED, ha="right", va="center")
    for suffix, dpi in (("", 200), ("-big", 400)):
        path = f"{out_base}{suffix}.png"
        fig.savefig(path, dpi=dpi, facecolor="white")
        Image.open(path).convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(path, optimize=True)
    plt.close(fig)


def overlay(out_base, line_list=(), labels=False):
    """Transit lines and/or place names alone on a transparent canvas laid out exactly
    like draw()'s map, so pages can stack it over any map and toggle it with CSS."""
    fig = plt.figure(figsize=(MAP_W, FIG_H), dpi=200)
    fig.patch.set_alpha(0)
    ax = fig.add_axes([0, FOOT / FIG_H, 1, MAP_H / FIG_H])
    ax.set_xlim(0, NCOL); ax.set_ylim(NR, 0); ax.axis("off"); ax.patch.set_alpha(0)
    halo = [patheffects.withStroke(linewidth=2, foreground=HALO)]
    for x, y, c, k in sorted(line_list, key=lambda t: ORDER[t[3]]):
        ax.plot(x, y, color=HALO, lw=WIDTH[k] + 1.1, solid_capstyle="round", solid_joinstyle="round")
    for x, y, c, k in sorted(line_list, key=lambda t: ORDER[t[3]]):
        ax.plot(x, y, color=c, lw=WIDTH[k], ls=(0, (2.5, 1.5)) if k == "ferry" else "-",
                solid_capstyle="round", solid_joinstyle="round")
    for name, la, lo_, kind in (LABELS if labels else []):
        x, y = proj(la, lo_)
        if kind:
            ax.text(x, y, name, fontsize=5.6, color=MUTED, ha="center", va="center", path_effects=halo)
        else:
            ax.text(x, y, name.upper(), fontsize=6.4, family="Arial Narrow", weight="bold", color=INK,
                    ha="center", va="center", path_effects=halo)
    for suffix, dpi in (("", 200), ("-big", 400)):
        path = f"{out_base}{suffix}.png"
        fig.savefig(path, dpi=dpi, transparent=True)
        Image.open(path).convert("RGBA").quantize(colors=64, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(path, optimize=True)
    plt.close(fig)


def labels_overlay(out_base):
    overlay(out_base, labels=True)


def time_legend(metric):
    lo, step, n = BANDS[metric]
    return dict(colors=ramp(n), ticks=[(k, str(lo + k * step)) for k in range(1, n, 3)],
                right=f"{lo + (n - 1) * step}+ min", caption="Minutes, shorter is better")


def time_image(vals, metric):
    vals = np.asarray(vals)
    lo, step, n = BANDS[metric]
    cols_ = ramp(n)
    band = np.clip(((vals - lo) // step).astype(int), 0, n - 1)
    return cells_image([cols_[b] for b in band], np.where(vals >= 179.5, 0.45, 0.93))


# Reachable-share maps (pipeline/reach.py): jobs30..60 and res30..60
REACH_KEYS = [f"{w}{t}" for w in ("jobs", "res") for t in (30, 45, 60)]
SHARE_STEP, SHARE_N = 5, 14  # 0-5%, ..., 65%+


def reach_title(key):
    t = key[-2:]
    return (f"Jobs you can get to within {t} minutes" if key.startswith("jobs")
            else f"Residents who can get here within {t} minutes")


def share_legend(key):
    return dict(colors=ramp(SHARE_N)[::-1], ticks=[(k, f"{k * SHARE_STEP}%") for k in range(2, SHARE_N, 2)],
                right=f"{(SHARE_N - 1) * SHARE_STEP}%+",
                caption=f"Share of the region's {'jobs' if key.startswith('jobs') else 'residents'}, more is better")


def share_image(vals):
    cols_ = ramp(SHARE_N)[::-1]  # light (few) -> dark (many): darker is better, as on the time maps
    band = np.clip((np.asarray(vals) // SHARE_STEP).astype(int), 0, SHARE_N - 1)
    return cells_image([cols_[b] for b in band], np.full(len(band), 0.93))


def render_reach(key, period):
    draw(share_image(G["reach"][period][key]), [], reach_title(key),
         f"{PERIOD_TITLE[period]}  ·  MBTA and walking, door to door, waiting included  ·  Dec 2026 schedule",
         share_legend(key), f"{OUT}/{key}-{period}", labels=False)


def render(metric, period):
    # Maps carry no lines or place names; pages stack lines.png and labels.png on top.
    draw(time_image(G["metrics"][period][metric], metric), [], METRIC_TITLE[metric],
         f"{PERIOD_TITLE[period]}  ·  MBTA and walking, door to door, waiting included  ·  Dec 2026 schedule",
         time_legend(metric), f"{OUT}/{metric}-{period}", labels=False)


if __name__ == "__main__":
    labels_overlay(f"{OUT}/labels")
    overlay(f"{OUT}/lines", lines)
    for m in ("jobs", "pop", "area"):
        for p, _ in G["periods"]:
            render(m, p)
            print(m, p, os.path.getsize(f"{OUT}/{m}-{p}.png") // 1024, "KB", flush=True)
    for k in REACH_KEYS:
        for p, _ in G["periods"]:
            render_reach(k, p)
        print(k, flush=True)
