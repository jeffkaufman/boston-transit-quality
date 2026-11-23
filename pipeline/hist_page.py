"""Generate the history page.

Usage: hist_page.py HIST_DIR SERVICE_COUNTS_JSON OUT_DIR   (HIST_DIR: see histdata.py)
Writes OUT_DIR/history.html; images from hist_render.py must sit alongside. The page works
without JavaScript; with it, a compare tool draws any two years (vanilla JS, no libraries).
"""
import json, os, sys
from PIL import Image
from datetime import date as D
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # for reach.py under python -I
import reach as RCH  # noqa: E402
import histdata  # noqa: E402

HD = sys.argv[1]
H, CURVES = histdata.load(HD)
SC = json.load(open(sys.argv[2]))
OUT = sys.argv[3]
YEARS = sorted(H)
BS = {y: json.load(open(f"intermediates/bus_speed/{y}.json"))["all"]["*"][0] / 1.609 for y in YEARS}
CF = json.load(open("intermediates/speed_counterfactual.json"))
GRID_ = json.load(open("intermediates/grid.json"))
CELL_M = round(GRID_["dlat"] * 111_132.0)
POP = np.array(GRID_["pop"], float); JOBS = np.array(GRID_["jobs"], float)
RS = {y: histdata.cells(HD, y, len(POP)) for y in YEARS}  # per square: rush, day, jobs45, res45
TH = RCH.TRANSIT_AREA_PCT
CHANGES = [("change-2009-2026", "2009 → 2026"), ("change-2019-2026", "2019 → 2026")]
VIEWS = [(c, n) for c, n in CHANGES] + [(f"year-{y}", y) for y in YEARS]
DEFAULT = "change-2009-2026"
INK, MUTE, GRID = "#1c2225", "#5a6468", "#e4e4e0"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


def nudge(ys, gap=11):
    """Spread label y positions so neighbours are at least `gap` apart, keeping order."""
    order = sorted(range(len(ys)), key=lambda i: ys[i]); out = list(ys)
    for _ in range(50):
        moved = False
        for a, b in zip(order, order[1:]):
            if out[b] - out[a] < gap:
                d = (gap - (out[b] - out[a])) / 2; out[a] -= d; out[b] += d; moved = True
        if not moved:
            break
    return out


def line_chart(series, ymin, ymax, yticks, unit, label, R_=74, fmt="{:,}"):
    """series: [(name, [values by YEARS], color, dash)]. Static SVG, native tooltips."""
    W_, H_, L, T_, B = 320, 170, 38, 10, 24
    x = lambda i: L + (W_ - L - R_) * i / (len(YEARS) - 1)
    y = lambda v: T_ + (H_ - T_ - B) * (1 - (v - ymin) / (ymax - ymin))
    p = [f'<svg viewBox="0 0 {W_} {H_}" width="100%" role="img" aria-label="{esc(label)}">']
    for t in yticks:
        p.append(f'<line x1="{L}" x2="{W_ - R_}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#e4e4e0"/>'
                 f'<text x="{L - 5}" y="{y(t) + 3.5:.1f}" text-anchor="end" font-size="10" fill="#5a6468">{fmt.format(t) if t else 0}</text>')
    for i, yr in enumerate(YEARS):
        if int(yr) % 4 == 2 or yr == YEARS[-1]:
            p.append(f'<text x="{x(i):.1f}" y="{H_ - 7}" text-anchor="middle" font-size="10" fill="#5a6468">{yr}</text>')
    # end-of-line labels: nudge apart so they don't overlap
    ly = nudge([y(v[-1]) for _, v, _, _ in series])
    for si, (name, vals, color, dash) in enumerate(series):
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        p.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"'
                 f'{" stroke-dasharray=\"4 3\"" if dash else ""}/>')
        for i, v in enumerate(vals):
            p.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="5" fill="transparent"><title>{YEARS[i]}: {fmt.format(v)} {unit}</title></circle>')
        p.append(f'<circle cx="{x(len(vals) - 1):.1f}" cy="{y(vals[-1]):.1f}" r="2.5" fill="{color}"/>'
                 f'<text x="{x(len(vals) - 1) + 6:.1f}" y="{ly[si] + 3.5:.1f}" font-size="10" fill="#1c2225">{esc(name)}</text>')
    p.append("</svg>")
    return "".join(p)


jobs = [round(H[y]["summary"]["jobs"], 1) for y in YEARS]
rush = [round(H[y]["rush"]["summary"]["jobs"], 1) for y in YEARS]
popm = rush
bus = [SC[y]["bus"] for y in YEARS]
rail = [SC[y]["rail_ferry"] for y in YEARS]
lo = int(min(jobs + popm) // 2 * 2) - 2
hi = int(max(jobs + popm) // 2 * 2) + 4
chart1 = line_chart([("rush hour", rush, "#8f3410", False), ("all day", jobs, "#5a6468", True)],
                    lo, hi, list(range(lo, hi + 1, 2 if hi - lo <= 12 else 4)), "min",
                    "Average resident's trip to jobs in minutes, rush hour and all day, 2009 to 2026")
chart2 = line_chart([("bus", bus, "#8f3410", False), ("rail + ferry", rail, "#5a6468", True)],
                    0, 12000, [0, 4000, 8000, 12000], "trips",
                    "MBTA weekday trips starting 7am to 7pm, 2009 to 2026")

# ---- Within reach (rush hour round trip), from reach.py ----
CURVE = CURVES  # year -> (minutes incl. 0, avg resident's % of jobs, avg job's % of residents)


def minutes_to(y, pct, side=1):
    m, *c = CURVE[y]
    return float(np.interp(pct, c[side - 1], m))


def curve_chart(years, label, side=1, xmax=75, ymax=80):
    """Share reachable (y) against minutes allowed (x), one line per year, direct-labeled."""
    W_, H_, L, R_, T_, B = 320, 190, 38, 44, 10, 30
    x = lambda v: L + (W_ - L - R_) * v / xmax
    y = lambda v: T_ + (H_ - T_ - B) * (1 - v / ymax)
    p = [f'<svg viewBox="0 0 {W_} {H_}" width="100%" role="img" aria-label="{esc(label)}">']
    for t in range(0, ymax + 1, 10):
        p.append(f'<line x1="{L}" x2="{W_ - R_}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}"/>'
                 f'<text x="{L - 5}" y="{y(t) + 3.5:.1f}" text-anchor="end" font-size="10" fill="{MUTE}">{f"{t}%" if t else 0}</text>')
    for t in range(0, xmax + 1, 15):
        p.append(f'<text x="{x(t):.1f}" y="{H_ - 16}" text-anchor="middle" font-size="10" fill="{MUTE}">{t}</text>')
    p.append(f'<text x="{L + (W_ - L - R_) / 2:.1f}" y="{H_ - 3}" text-anchor="middle" font-size="10" fill="{MUTE}">minutes</text>')
    ends = []
    for yr, color, dash in years:
        m, cj, cr = CURVE[yr]
        c = cj if side == 1 else cr
        keep = m <= xmax
        pts = " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in zip(m[keep], c[keep]))
        p.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"'
                 f'{" stroke-dasharray=\"4 3\"" if dash else ""}/>')
        for a, b in zip(m[keep][1:], c[keep][1:]):
            p.append(f'<circle cx="{x(a):.1f}" cy="{y(b):.1f}" r="5" fill="transparent"><title>{yr}, within {a:.0f} min: {b:.1f}%</title></circle>')
        ends.append(y(c[keep][-1]))
    for (yr, color, _), ly in zip(years, nudge(ends)):
        p.append(f'<text x="{W_ - R_ + 5}" y="{ly + 3.5:.1f}" font-size="10" fill="{INK}">{yr}</text>')
    p.append("</svg>")
    return "".join(p)


CY = (("2009", "#6b7378", True), ("2019", "#2a6ebb", True), ("2026", "#8f3410", False))
chartK1 = curve_chart(CY, "Share of the region's jobs the average resident can reach, by minutes allowed, 2009, 2019, and 2026")
PCTS = ((10, "#6b7378", True), (25, "#8f3410", False), (50, "#2a6ebb", True))
mins_series = [(f"{pc}% of jobs", [minutes_to(y, pc) for y in YEARS], c, d) for pc, c, d in PCTS]
mlo = int(min(min(v) for _, v, *_ in mins_series) // 5 * 5)
mhi = int(np.ceil(max(max(v) for _, v, *_ in mins_series) / 5) * 5)
chartK2 = line_chart(mins_series, mlo, mhi, list(range(mlo, mhi + 1, 5 if mhi - mlo <= 40 else 10)), "min",
                     "Minutes the average resident needs to reach 10%, 25%, and 50% of the region's jobs, 2009 to 2026",
                     R_=78, fmt="{:.0f}")
m25 = {y: minutes_to(y, 25) for y in ("2009", "2026")}
wavg = lambda v, w: float((np.asarray(v) * w).sum() / w.sum())
area_res = [POP[np.asarray(RS[y]["jobs45"]) >= TH].sum() / POP.sum() * 100 for y in YEARS]
area_jobs = [JOBS[np.asarray(RS[y]["res45"]) >= TH].sum() / JOBS.sum() * 100 for y in YEARS]
alo = int(max(0, (min(area_res + area_jobs) - 5) // 10 * 10))
chartR3 = line_chart([("residents", area_res, "#8f3410", False), ("jobs", area_jobs, "#2a6ebb", True)],
                     alo, 100, list(range(alo, 101, 10)), "",
                     "Share of residents living in the transit area and of jobs in the transit job market, 2009 to 2026", fmt="{:.0f}%")
in0, in1 = np.asarray(RS["2009"]["jobs45"]) >= TH, np.asarray(RS["2026"]["jobs45"]) >= TH
moved_out = POP[in0 & ~in1].sum() / POP.sum() * 100
moved_in = POP[~in0 & in1].sum() / POP.sum() * 100
j45 = {y: wavg(RS[y]["jobs45"], POP) for y in ("2009", "2026")}
in_chg = wavg(RS["2026"]["jobs45"], POP * in0) / wavg(RS["2009"]["jobs45"], POP * in0) - 1

# ---- Characterizing the change (rush hour, 2009 -> 2026), from change_breakdown.py ----
CB = json.load(open("intermediates/change_breakdown.json"))["rush"]


def axis_y(p, y, ticks, L, W_, R_, fmt):
    for t in ticks:
        p.append(f'<line x1="{L}" x2="{W_ - R_}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="{GRID}"/>'
                 f'<text x="{L - 5}" y="{y(t) + 3.5:.1f}" text-anchor="end" font-size="10" fill="{MUTE}">{fmt.format(t) if t else 0}</text>')


def range_chart(rows, xlabel, label, ymax=14, bar=False):
    """rows: [(category label, stats dict with p25/med/p75/pop)]. Median dot + middle-half bar, or a plain bar."""
    W_, H_, L, R_, T_, B = 320, 180, 30, 6, 10, 40
    n = len(rows); bw = (W_ - L - R_) / n
    y = lambda v: T_ + (H_ - T_ - B) * (1 - v / ymax)
    p = [f'<svg viewBox="0 0 {W_} {H_}" width="100%" role="img" aria-label="{esc(label)}">']
    axis_y(p, y, range(0, ymax + 1, 4), L, W_, R_, "{:+d}")
    for i, (cat, st) in enumerate(rows):
        cx = L + bw * (i + .5)
        tip = f"<title>{esc(cat)}: median {st['med']:+.1f} min, middle half {st['p25']:+.1f} to {st['p75']:+.1f} ({st['pop']:,} residents)</title>"
        if bar:
            p.append(f'<rect x="{cx - bw * .32:.1f}" y="{y(st["med"]):.1f}" width="{bw * .64:.1f}" height="{y(0) - y(st["med"]):.1f}" rx="2" fill="#8f3410">{tip}</rect>')
        else:
            p.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{y(st["p25"]):.1f}" y2="{y(st["p75"]):.1f}" stroke="#d9a58a" stroke-width="6" stroke-linecap="round"/>'
                     f'<circle cx="{cx:.1f}" cy="{y(st["med"]):.1f}" r="4" fill="#8f3410" stroke="#fff" stroke-width="1.5"/>'
                     f'<rect x="{cx - bw / 2:.1f}" y="{T_}" width="{bw:.1f}" height="{H_ - T_ - B}" fill="transparent">{tip}</rect>')
        lab = cat.split("-")[0] if not bar else cat
        p.append(f'<text x="{cx:.1f}" y="{H_ - B + 13}" text-anchor="middle" font-size="9.5" fill="{MUTE}">{esc(lab)}</text>')
    p.append(f'<text x="{L + (W_ - L - R_) / 2:.1f}" y="{H_ - 6}" text-anchor="middle" font-size="10" fill="{MUTE}">{esc(xlabel)}</text>')
    p.append("</svg>")
    return "".join(p)


def fan_chart(pct, label):
    W_, H_, L, R_, T_, B = 320, 180, 30, 40, 10, 24
    vals = [pct[y_] for y_ in YEARS]; ymin, ymax = 40, 95
    x = lambda i: L + (W_ - L - R_) * i / (len(YEARS) - 1)
    y = lambda v: T_ + (H_ - T_ - B) * (1 - (v - ymin) / (ymax - ymin))
    p = [f'<svg viewBox="0 0 {W_} {H_}" width="100%" role="img" aria-label="{esc(label)}">']
    axis_y(p, y, range(40, 96, 10), L, W_, R_, "{}")
    for i, yr in enumerate(YEARS):
        if int(yr) % 4 == 2 or yr == YEARS[-1]:
            p.append(f'<text x="{x(i):.1f}" y="{H_ - 7}" text-anchor="middle" font-size="10" fill="{MUTE}">{yr}</text>')
    def band(lo, hi, fill):
        pts = [f"{x(i):.1f},{y(v[hi]):.1f}" for i, v in enumerate(vals)] + [f"{x(i):.1f},{y(v[lo]):.1f}" for i, v in reversed(list(enumerate(vals)))]
        p.append(f'<polygon points="{" ".join(pts)}" fill="{fill}"/>')
    band(0, 4, "#f1dccf"); band(1, 3, "#dfb197")
    p.append(f'<polyline points="{" ".join(f"{x(i):.1f},{y(v[2]):.1f}" for i, v in enumerate(vals))}" fill="none" stroke="#8f3410" stroke-width="2"/>')
    for k, name in ((4, "90th"), (3, "75th"), (2, "median"), (1, "25th"), (0, "10th")):
        p.append(f'<text x="{x(len(vals) - 1) + 5:.1f}" y="{y(vals[-1][k]) + 3.5:.1f}" font-size="9.5" fill="{INK if k == 2 else MUTE}">{name}</text>')
    for i, v in enumerate(vals):
        p.append(f'<rect x="{x(i) - 6:.1f}" y="{T_}" width="12" height="{H_ - T_ - B}" fill="transparent"><title>{YEARS[i]}: 10th {v[0]:.0f}, 25th {v[1]:.0f}, median {v[2]:.0f}, 75th {v[3]:.0f}, 90th {v[4]:.0f} min</title></rect>')
    p.append("</svg>")
    return "".join(p)


chartA = range_chart([(s_["range"], s_) for s_ in CB["baseline_decile"]], "2009 rush-hour commute (minutes), tenths of residents",
                     "Change in rush-hour commute 2009 to 2026, by 2009 commute time")
CLS = [("rapid transit (2009)", "rapid transit", "#2a6ebb", False), ("rapid transit added since", "new rapid transit", "#2a6ebb", True),
       ("commuter rail only", "commuter rail", "#6b7378", True), ("bus only", "bus only", "#8f3410", False)]
chartB = line_chart([(lab, [CB["class_series"][k][y_] for y_ in YEARS], col, dash) for k, lab, col, dash in CLS],
                    -2, 12, [0, 4, 8, 12], "min vs 2009", "Change in rush-hour commute since 2009 by type of nearby transit",
                    R_=92, fmt="{:+g}")
chartC = fan_chart(CB["percentiles_p10_p25_p50_p75_p90"], "Spread of residents' rush-hour commutes, 2009 to 2026")
chartD = range_chart([(s_["range"], s_) for s_ in CB["miles_from_downtown"]], "Miles from Park Street",
                     "Median change in rush-hour commute 2009 to 2026 by distance from Park Street", bar=True)
CL = CB["class"]

sel = ",\n".join(f"#v-{k}:checked ~ aside label[for=v-{k}]" for k, _ in VIEWS + [("custom", "")])
foc = ",\n".join(f"#v-{k}:focus-visible ~ aside label[for=v-{k}]" for k, _ in VIEWS + [("custom", "")])
LABS = [("on", "On", ""), ("off", "Off", "-nolabels")]
TLS = [("on", "On"), ("off", "Off")]
IMG_H = Image.open(f"{sys.argv[3]}/labels.png").size[1]  # map image height (depends on the grid)
MEAS = [("rush", "Rush hour", ""), ("day", "All day", "-allday"),
        ("jobs45", "Jobs within 45 min", "-jobs45"), ("res45", "Residents within 45 min", "-res45")]
show = ",\n".join(f"#v-{k}:checked ~ #ms-{ms}:checked ~ main .m-{k}-{ms}" for k, _ in VIEWS for ms, *_ in MEAS)
msel = ",\n".join(f"#ms-{ms}:checked ~ aside label[for=ms-{ms}]" for ms, *_ in MEAS)
mfoc = ",\n".join(f"#ms-{ms}:focus-visible ~ aside label[for=ms-{ms}]" for ms, *_ in MEAS)
lsel = ",\n".join(f"#l-{l}:checked ~ aside label[for=l-{l}]" for l, *_ in LABS)
lfoc = ",\n".join(f"#l-{l}:focus-visible ~ aside label[for=l-{l}]" for l, *_ in LABS)
tsel = ",\n".join(f"#tl-{l}:checked ~ aside label[for=tl-{l}]" for l, _ in TLS)
tfoc = ",\n".join(f"#tl-{l}:focus-visible ~ aside label[for=tl-{l}]" for l, _ in TLS)
inputs = "\n".join(f'<input type="radio" name="view" id="v-{k}"{" checked" if k == DEFAULT else ""}>' for k, _ in VIEWS)
inputs += '\n<input type="radio" name="view" id="v-custom">'
inputs += "\n" + "\n".join(f'<input type="radio" name="measure" id="ms-{ms}"{" checked" if ms == "rush" else ""}>' for ms, *_ in MEAS)
inputs += "\n" + "\n".join(f'<input type="radio" name="labels" id="l-{l}"{" checked" if l == "on" else ""}>' for l, *_ in LABS)
inputs += "\n" + "\n".join(f'<input type="radio" name="tlines" id="tl-{l}"{" checked" if l == "on" else ""}>' for l, _ in TLS)
maps = []
SIZES = "(min-width: 800px) calc(100vw - 360px), 100vw"
OVERLAY = f'<img class="lab" src="labels.png" srcset="labels.png 1100w, labels-big.png 2200w" sizes="{SIZES}" width="1100" height="{IMG_H}" alt="">'
# each year's map shows that year's lines; change maps show the later year's
lines_img = lambda y: (f'<img class="lin" src="lines-{y}.png" srcset="lines-{y}.png 1100w, lines-{y}-big.png 2200w" '
                       f'sizes="{SIZES}" width="1100" height="{IMG_H}" alt="">')
for (k, n), (ms, mname, msuf) in ((v, m_) for v in VIEWS for m_ in MEAS):
    f = k + msuf
    what = {"rush": "rush-hour commute time to jobs", "day": "average weekday transit trip time to jobs",
            "jobs45": "the share of the region's jobs within a 45-minute rush-hour commute",
            "res45": "the share of the region's residents who can commute to each square within 45 minutes"}[ms]
    alt = (f"Map of Greater Boston colored by change in {what}, {n.replace('→', 'to')}."
           if k.startswith("change") else f"Map of Greater Boston colored by {what} in {n}.")
    maps.append(f'<a class="m m-{k}-{ms}" href="{f}-big.png"><img src="{f}.png" srcset="{f}.png 1100w, {f}-big.png 2200w" '
                f'sizes="(min-width: 800px) calc(100vw - 360px), 100vw" width="1100" height="{IMG_H}" alt="{alt}"'
                f'{"" if (k == DEFAULT and ms == "rush") else " loading=\"lazy\""}>{lines_img(k.split("-")[-1])}{OVERLAY}</a>')
CMP = json.load(open(f"{OUT}/cmp/meta.json"))
JS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare.js")).read()
rows = "\n".join(f"<tr><td>{y}</td><td>{H[y]['rush']['summary']['jobs']:.1f}</td><td>{H[y]['summary']['jobs']:.1f}</td>"
                 f"<td>{SC[y]['bus']:,}</td><td>{SC[y]['rail_ferry']:,}</td></tr>" for y in YEARS)
j10, j19, j26 = (H[y]["summary"]["jobs"] for y in ("2009", "2019", "2026"))
r10, r19, r26 = (H[y]["rush"]["summary"]["jobs"] for y in ("2009", "2019", "2026"))

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transit Service Quality, 2009–2026</title>
<meta name="description" content="How Greater Boston's scheduled MBTA service quality changed from 2009 to 2026, recomputed from archived GTFS schedules.">
<style>
html, body {{ margin: 0; height: 100%; }}
body {{ font-family: Georgia, "Times New Roman", serif; color: #1c2225; background: #fff; line-height: 1.4; }}
.wrap {{ display: grid; grid-template-columns: 340px 1fr; height: 100vh; height: 100dvh; }}
.wrap > input {{ position: absolute; opacity: 0; width: 1px; height: 1px; margin: 0; }}
aside {{ overflow-y: auto; padding: 22px 20px 28px; border-right: 1px solid #ddd; background: #fafaf8; }}
h1 {{ font-size: 26px; line-height: 1.1; margin: 0 0 12px; }}
h2 {{ font-size: 17px; margin: 18px 0 6px; }}
p {{ margin: 0 0 12px; }}
.name {{ display: block; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: #5a6468; margin-bottom: 4px; font-family: Arial, Helvetica, sans-serif; }}
.opts {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; }}
.years {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 4px; margin-bottom: 12px; }}
label {{ border: 1px solid #bbb; border-radius: 4px; padding: 3px 8px; cursor: pointer; user-select: none; background: #fff; font-size: 15px; text-align: center; }}
.years label {{ padding: 3px 0; font-size: 14px; }}
label:hover {{ border-color: #555; }}
{sel} {{ background: #1c2225; border-color: #1c2225; color: #fff; }}
{msel} {{ background: #1c2225; border-color: #1c2225; color: #fff; }}
{mfoc} {{ outline: 2px solid #2a6ebb; outline-offset: 1px; }}
{lsel} {{ background: #1c2225; border-color: #1c2225; color: #fff; }}
{lfoc} {{ outline: 2px solid #2a6ebb; outline-offset: 1px; }}
{tsel} {{ background: #1c2225; border-color: #1c2225; color: #fff; }}
{tfoc} {{ outline: 2px solid #2a6ebb; outline-offset: 1px; }}
{foc} {{ outline: 2px solid #2a6ebb; outline-offset: 1px; }}
.small {{ font-size: 14px; color: #5a6468; }}
table {{ border-collapse: collapse; width: 100%; font-size: 14px; margin: 4px 0 12px; font-variant-numeric: tabular-nums; }}
td, th {{ padding: 2px 0 2px 6px; border-bottom: 1px solid #e2e2de; text-align: right; font-weight: normal; }}
td:first-child, th:first-child {{ text-align: left; padding-left: 0; }}
th {{ font-size: 12px; color: #5a6468; font-family: Arial, Helvetica, sans-serif; vertical-align: bottom; }}
ul {{ padding-left: 18px; margin: 0; font-size: 15px; }}
li {{ margin-bottom: 6px; }}
a {{ color: #1c4f8a; }}
svg text {{ font-family: Arial, Helvetica, sans-serif; }}
main {{ min-width: 0; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 12px; }}
.m {{ display: none; position: relative; }}
.m img.lab, .m img.lin {{ position: absolute; inset: 0; width: 100%; height: 100%; max-height: none; pointer-events: none; }}
#l-off:checked ~ main .lab {{ display: none; }}
#tl-off:checked ~ main .lin {{ display: none; }}
{show} {{ display: block; }}
#cmpctl {{ display: none; }}
#v-custom:checked ~ aside #cmpctl, #v-custom:checked ~ main .m-custom {{ display: block; }}
.cmpsel {{ align-items: center; }}
.cmpsel select {{ font: inherit; font-size: 15px; padding: 2px 4px; }}
.m canvas {{ display: block; width: auto; height: auto; max-width: 100%; max-height: calc(100vh - 24px); max-height: calc(100dvh - 24px); }}
.m img {{ display: block; width: auto; height: auto; max-width: 100%; max-height: calc(100vh - 24px); max-height: calc(100dvh - 24px); }}
@media (max-width: 799px) {{
  .wrap {{ display: block; height: auto; }}
  aside {{ border-right: 0; border-bottom: 1px solid #ddd; padding: 16px; }}
  main {{ padding: 8px 0; display: block; }}
  .m img, .m canvas {{ width: 100%; max-height: none; }}
}}
</style>
</head>
<body>
<div class="wrap">
{inputs}
<aside>
<h1>Transit Service Quality, 2009–2026</h1>
<p>The same calculation as the <a href="./">2026 map</a>, run on archived MBTA schedules from each November. By the schedule, the average resident's rush-hour commute to jobs was {r10:.1f} minutes in 2009, {r19:.1f} in 2019, and {r26:.1f} in 2026. Averaged over the whole weekday it went from {j10:.1f} to {j19:.1f} to {j26:.1f}: rush-hour service was cut more than service at other times.</p>
<span class="name">Change</span>
<div class="opts">{"".join(f'<label for="v-{k}">{n}</label>' for k, n in CHANGES)}<label for="v-custom" hidden>Pick years</label></div>
<div id="cmpctl"><div class="opts cmpsel"><select id="cmpA" aria-label="From year">{"".join(f'<option{" selected" if y == "2019" else ""}>{y}</option>' for y in YEARS)}</select>
<span>to</span><select id="cmpB" aria-label="To year">{"".join(f'<option{" selected" if y == "2023" else ""}>{y}</option>' for y in YEARS)}</select></div>
<p class="small" id="cmpavg"></p></div>
<span class="name">Measure</span>
<div class="opts">{"".join(f'<label for="ms-{ms}">{n}</label>' for ms, n, _ in MEAS)}</div>
<span class="name">Single year</span>
<div class="years">{"".join(f'<label for="v-year-{y}">{y}</label>' for y in YEARS)}</div>
<span class="name">Place names</span>
<div class="opts">{"".join(f'<label for="l-{l}">{n}</label>' for l, n, _ in LABS)}</div>
<span class="name">Transit lines</span>
<div class="opts">{"".join(f'<label for="tl-{l}">{n}</label>' for l, n in TLS)}</div>
<p class="small">Click the map for full resolution.</p>
<h2>Region-wide</h2>
<p class="small">The average resident's trip to jobs, in minutes:</p>
{chart1}
<p class="small">MBTA weekday trips starting between 7am and 7pm, systemwide:</p>
{chart2}
<p class="small">Bus schedules also got slower: buses in this area are scheduled at {BS["2009"]:.1f} mph in 2009 and {BS["2026"]:.1f} mph in 2026 (straight-line distance between stops). That accounts for most of the all-day change: rerunning the 2026 schedule with buses at 2010 speeds gives {CF["2026_at_2010_bus_speed"]:.1f} minutes to jobs (actual: {CF["2026"]:.1f}; 2010: {CF["2010"]:.1f}).</p>
<h2>Within reach</h2>
<p class="small">Another way to measure transit: how much of the region you can get to within a reasonable commute, rather than the average trip to everywhere. Rush-hour round trip, as above.</p>
<p class="small"><b>Jobs you can get to</b>: the share of the region's jobs the average resident can reach, depending on how long a commute they'll accept. The 2026 curve sits to the right: reaching the same jobs takes longer.</p>
{chartK1}
<p class="small"><b>The commute it takes.</b> Minutes the average resident needs to reach 10%, 25%, and half of the region's jobs. A quarter of jobs took {m25["2009"]:.0f} minutes in 2009 and {m25["2026"]:.0f} in 2026.</p>
{chartK2}
<p class="small"><b>The transit area shrank.</b> Call a home in the transit area if at least {TH}% of the region's jobs are within a 45-minute commute, and a job in the transit job market if at least {TH}% of residents can commute to it within 45 minutes. Share of all residents and jobs inside:</p>
{chartR3}
<p class="small">Between 2009 and 2026, {moved_out:.0f}% of residents dropped out of the transit area and {moved_in:.1f}% joined. Inside the 2009 area, jobs within 45 minutes fell by {-in_chg * 100:.0f}%.</p>
<a href="area-2009-2026-big.png"><img src="area-2009-2026.png" width="1100" height="{IMG_H}" alt="Map of the transit area in 2009 and 2026: gray where it stayed, orange where homes dropped out, purple where they joined." style="width:100%;height:auto"></a>
<h2>What changed, and where</h2>
<p class="small">All four charts use the rush-hour commute to jobs, weighted by residents.</p>
<p class="small"><b>Places that were already slow lost the most.</b> Change from 2009 to 2026, with residents grouped into tenths by their 2009 commute (dot: median; bar: middle half):</p>
{chartA}
<p class="small"><b>The bus slowdown shows up by place.</b> Change since 2009 by the transit within 800m (half a mile): neighborhoods near rapid transit lost a median {CL["rapid transit (2009)"]["med"]:.0f} minutes, those with only buses or only commuter rail about {CL["bus only"]["med"]:.0f}. New rapid transit is mostly the Green Line Extension.</p>
{chartB}
<p class="small"><b>The gap widened.</b> Rush-hour commutes for residents at the 10th, 25th, 50th, 75th, and 90th percentiles:</p>
{chartC}
<p class="small"><b>Farther out lost more.</b> Median change from 2009 to 2026 by distance from Park Street:</p>
{chartD}
<h2>How this was made</h2>
<p class="small">I made the original <a href="https://www.jefftk.com/p/transit-service-quality-map">2010 map</a>. This update is a collaboration with Claude Opus 5.5. Claude wrote all of the code and text, picked the data sources and routing details, and did the analysis. That includes finding most of the data problems (old schedules that made station transfers free, a sample day with a Red Line shutdown, missing walking paths inside stations) and designing the test showing that slower bus schedules explain most of the decline. I decided what to look at, including the comparison over time, the rush-hour measure, and how much traffic was slowing buses (which prompted that test), and questioned results that looked wrong. Three of those questions led to fixes: Lexington looked much worse because of a broken transfer at Alewife; Winthrop looked unreachable in 2010, though it had buses, because the old schedules left out its routes; and a square near Waverley jumped 40 minutes because a station moved a few metres across a hard walking limit, which led me to ask whether a hard limit made sense, and Claude replaced it with a gradual penalty for long walks.</p>
<ul>
<li>For each year Claude took the MBTA's archived GTFS schedule for a mid-November Tuesday and ran the same routing as the 2026 map: every pair of {CELL_M}m squares, departures every five minutes from 7am to 7pm, door to door including walking and waiting. Past 15 minutes, each minute of walking counts as 1.5, and walks over an hour are not used.</li>
<li>Rush hour averages the trip from home leaving between 7 and 9am with the trip back leaving between 4:30 and 6:30pm, like a commute. All day averages trips leaving any time from 7am to 7pm.</li>
<li>Population (2020 Census), jobs (LODES 2024), and the walking network (current OpenStreetMap) are held fixed at today's values, so differences between years come only from the transit schedule.</li>
<li>Every transfer between different stops takes at least two minutes. Older feeds put all of a station's platforms at a single point, which would otherwise make station transfers free and flatter the early years. Newer feeds go the other way, placing each platform and busway berth precisely, and since the walking network doesn't include paths inside stations, transfers between stops in the same station are allowed at 1.5× the straight-line distance.</li>
<li>These are scheduled times. If older schedules were more optimistic about how fast buses would actually run, some of the apparent slowdown is schedules becoming more realistic. Changes in how often buses run are real either way.</li>
<li>Claude checked each sample day for subway shutdowns. The 2024 sample is Nov 12 because Nov 19 had a Red Line shutdown between Broadway and Harvard. The 2018 sample includes the Wollaston station closure, which lasted more than a year.</li>
<li>The archived 2009–2014 schedules leave out the privately contracted bus routes 710, 712, 713, and 716, including Winthrop's only buses. For those years Claude added these routes using their schedules from the December 2014 file, the earliest archived file that includes them.</li>
<li>Commuter rail and ferry lines on each map come from that year's feed.</li>
</ul>
<h2>Data</h2>
<table>
<tr><th>Year</th><th>Rush hour (min to jobs)</th><th>All day (min to jobs)</th><th>Bus trips</th><th>Rail + ferry trips</th></tr>
{rows}
</table>
<p class="small">Schedules: MBTA GTFS archive, https://cdn.mbta.com/archive/archived_feeds.txt</p>
</aside>
<main>
{chr(10).join(maps)}
<div class="m m-custom"><canvas id="cmpc" width="{CMP["w"]}" height="{CMP["h"]}" role="img" aria-label="Map of Greater Boston colored by change between two chosen years"></canvas><img class="lin" id="cmplin" alt="">{OVERLAY}</div>
</main>
<script>{JS}</script>
</div>
</body>
</html>
"""
open(f"{OUT}/history.html", "w").write(html)
print("wrote", len(html), "bytes")
