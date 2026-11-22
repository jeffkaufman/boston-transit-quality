"""Generate the standalone, no-JS full-page version.

Usage: gen_fullpage.py SITE_DIR OUT_DIR

Writes OUT_DIR/index.html, which expects the PNGs from render.py alongside it.
"""
import json, sys
from PIL import Image

SITE, OUT = sys.argv[1:3]
G = json.load(open(f"{SITE}/grid.json"))

def grid_text(g):
    """e.g. '4,140 squares of 400m (about a quarter mile)'"""
    m = round(g["dlat"] * 111_132.0)
    size = "about a quarter mile" if abs(m - 400) < 20 else f"about {round(m * 3.281 / 50) * 50:,} feet"
    return f"{len(g['cells']):,} squares of {m}m ({size})"
GRIDTXT = grid_text(G)
METRICS = [("jobs", "Jobs", "a typical job"), ("pop", "Residents", "where a typical resident lives"),
           ("area", "Everywhere", "anywhere on the map")]
PERIODS = [("weekday_rush", "Rush hour"), ("weekday_day", "Weekday day"), ("weekday_eve", "Weekday evening"),
           ("saturday", "Saturday"), ("sunday", "Sunday")]
LABELS = [("labels", "On", ""), ("nolabels", "Off", "-nolabels")]
LINES = [("lines", "On"), ("nolines", "Off")]
IMG_H = Image.open(f"{OUT}/labels.png").size[1]  # map image height (depends on the grid)
FULL = dict(G["periods"])
S = G["summary"]
# reachable-share maps (render.py REACH_KEYS); all map choices share the tq-metric radio group
REACH = [(f"{w}{t}", f"{t} min", None) for w in ("jobs", "res") for t in (30, 45, 60)]
ALLM = METRICS + REACH
RCH = G["reach"]
pop_w = G["pop"]; jobs_w = G["jobs"]
wavg = lambda v, w: sum(a * b for a, b in zip(v, w)) / sum(w)

sel = ",\n".join(f"#tq-{k}:checked ~ aside label[for=tq-{k}]" for k, *_ in ALLM + PERIODS + LABELS + LINES)
foc = ",\n".join(f"#tq-{k}:focus-visible ~ aside label[for=tq-{k}]" for k, *_ in ALLM + PERIODS + LABELS + LINES)
show = ",\n".join(f"#tq-{m}:checked ~ #tq-{p}:checked ~ main .tq-{m}-{p}"
                 for m, *_ in ALLM for p, _ in PERIODS)
lede = ",\n".join(f"#tq-{m}:checked ~ aside .lede-{m}" for m, *_ in ALLM)

inputs = "\n".join(
    [f'<input type="radio" name="tq-metric" id="tq-{m}"{" checked" if i == 0 else ""}>' for i, (m, *_) in enumerate(ALLM)] +
    [f'<input type="radio" name="tq-period" id="tq-{p}"{" checked" if i == 0 else ""}>' for i, (p, _) in enumerate(PERIODS)] +
    [f'<input type="radio" name="tq-labels" id="tq-{l}"{" checked" if i == 0 else ""}>' for i, (l, *_) in enumerate(LABELS)] +
    [f'<input type="radio" name="tq-lines" id="tq-{l}"{" checked" if i == 0 else ""}>' for i, (l, _) in enumerate(LINES)])
SIZES = "(min-width: 800px) calc(100vw - 360px), 100vw"
OVERLAY = (f'<img class="lin" src="lines.png" srcset="lines.png 1100w, lines-big.png 2200w" sizes="{SIZES}" width="1100" height="{IMG_H}" alt="">'
           f'<img class="lab" src="labels.png" srcset="labels.png 1100w, labels-big.png 2200w" sizes="{SIZES}" width="1100" height="{IMG_H}" alt="">')
maps = []
for m, _, desc in ALLM:
    for p, _ in PERIODS:
        first = m == "jobs" and p == "weekday_rush"
        if desc:
            alt = (f"Map of Greater Boston colored by average door-to-door transit time to {desc}, {FULL[p]}. "
                   f"Darkest around downtown Boston and along rapid transit lines.")
        elif m.startswith("jobs"):
            alt = f"Map of Greater Boston colored by the share of the region's jobs reachable by transit within {m[-2:]} minutes, {FULL[p]}."
        else:
            alt = f"Map of Greater Boston colored by the share of the region's residents who can reach each square by transit within {m[-2:]} minutes, {FULL[p]}."
        b = f"{m}-{p}"
        maps.append(f'<a class="tq-map tq-{m}-{p}" href="{b}-big.png"><img src="{b}.png" '
                    f'srcset="{b}.png 1100w, {b}-big.png 2200w" sizes="{SIZES}" '
                    f'width="1100" height="{IMG_H}" alt="{alt}"{"" if first else " loading=\"lazy\""}>{OVERLAY}</a>')
rows = "\n".join(f"<tr><td>{n}</td><td>{round(S[p]['jobs'])}</td><td>{round(S[p]['pop'])}</td></tr>" for p, n in PERIODS)
R_ = RCH["weekday_rush"]
reach_rows = "\n".join(f"<tr><td>{t} min</td><td>{wavg(R_[f'jobs{t}'], pop_w):.0f}%</td><td>{wavg(R_[f'res{t}'], jobs_w):.0f}%</td></tr>"
                        for t in (30, 45, 60))
reach_ledes = "\n".join(
    f'<p class="lede lede-jobs{t}">Each square is colored by the share of the region\'s jobs you can get to from there within {t} minutes by MBTA and walking, waiting included. At rush hour this is a round trip: out 7–9am and home 4:30–6:30pm.</p>\n'
    f'<p class="lede lede-res{t}">Each square is colored by the share of the region\'s residents who can get there within {t} minutes by MBTA and walking, waiting included: the workplaces open to someone without a car. At rush hour this is a round trip: in 7–9am and home 4:30–6:30pm.</p>'
    for t in (30, 45, 60))

html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transit Service Quality Map, 2026</title>
<meta name="description" content="Greater Boston colored by average door-to-door MBTA travel time to jobs, residents, or everywhere, computed from the Fall 2026 schedule.">
<style>
html, body {{ margin: 0; height: 100%; }}
body {{ font-family: Georgia, "Times New Roman", serif; color: #1c2225; background: #fff; line-height: 1.4; }}
.wrap {{ display: grid; grid-template-columns: 340px 1fr; height: 100vh; height: 100dvh; }}
.wrap > input {{ position: absolute; opacity: 0; width: 1px; height: 1px; margin: 0; }}
aside {{ overflow-y: auto; padding: 22px 20px 28px; border-right: 1px solid #ddd; background: #fafaf8; }}
h1 {{ font-size: 26px; line-height: 1.1; margin: 0 0 12px; }}
.lede {{ display: none; margin: 0 0 16px; }}
{lede} {{ display: block; }}
.row {{ margin: 0 0 12px; }}
.row .name {{ display: block; font-size: 13px; text-transform: uppercase; letter-spacing: 0.05em; color: #5a6468; margin-bottom: 4px; font-family: Arial, Helvetica, sans-serif; }}
.row .opts {{ display: flex; flex-wrap: wrap; gap: 4px; }}
label {{ border: 1px solid #bbb; border-radius: 4px; padding: 3px 9px; cursor: pointer; user-select: none; background: #fff; font-size: 15px; }}
label:hover {{ border-color: #555; }}
{sel} {{ background: #1c2225; border-color: #1c2225; color: #fff; }}
{foc} {{ outline: 2px solid #2a6ebb; outline-offset: 1px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 15px; margin: 4px 0 16px; }}
td, th {{ padding: 3px 0 3px 8px; border-bottom: 1px solid #e2e2de; text-align: right; font-weight: normal; }}
td:first-child, th:first-child {{ text-align: left; padding-left: 0; }}
th {{ font-size: 13px; color: #5a6468; font-family: Arial, Helvetica, sans-serif; }}
h2 {{ font-size: 17px; margin: 18px 0 6px; }}
ul {{ padding-left: 18px; margin: 0; font-size: 15px; }}
li {{ margin-bottom: 6px; }}
.small {{ font-size: 14px; color: #5a6468; }}
a {{ color: #1c4f8a; }}
main {{ min-width: 0; min-height: 0; display: flex; align-items: center; justify-content: center; padding: 12px; }}
.tq-map {{ display: none; position: relative; }}
.tq-map img.lab, .tq-map img.lin {{ position: absolute; inset: 0; width: 100%; height: 100%; max-height: none; pointer-events: none; }}
#tq-nolabels:checked ~ main .lab {{ display: none; }}
#tq-nolines:checked ~ main .lin {{ display: none; }}
{show} {{ display: block; }}
.tq-map img {{ display: block; width: auto; height: auto; max-width: 100%; max-height: calc(100vh - 24px); max-height: calc(100dvh - 24px); }}
@media (max-width: 799px) {{
  .wrap {{ display: block; height: auto; }}
  aside {{ border-right: 0; border-bottom: 1px solid #ddd; padding: 16px; }}
  main {{ padding: 8px 0; display: block; }}
  .tq-map img {{ width: 100%; max-height: none; }}
  .methods {{ display: none; }}
  .methods-bottom {{ display: block; padding: 0 16px 24px; }}
}}
@media (min-width: 800px) {{ .methods-bottom {{ display: none; }} }}
</style>
</head>
<body>
<div class="wrap">
{inputs}
<aside>
<h1>Transit Service Quality Map, 2026</h1>
<p class="lede lede-jobs">Each square is colored by how long it takes, on average, to get from there to a typical job by MBTA and walking, waiting included.</p>
<p class="lede lede-pop">Each square is colored by how long it takes, on average, to get from there to where a typical resident lives by MBTA and walking, waiting included.</p>
<p class="lede lede-area">Each square is colored by how long it takes, on average, to get from there to anywhere on the map by MBTA and walking, waiting included. Every square counts equally, as in the 2010 map.</p>
{reach_ledes}
<div class="row"><span class="name">Average trip to</span><span class="opts">{"".join(f'<label for="tq-{m}">{n}</label>' for m, n, _ in METRICS)}</span></div>
<div class="row"><span class="name">Jobs you can get to within</span><span class="opts">{"".join(f'<label for="tq-{m}">{n}</label>' for m, n, _ in REACH if m.startswith("jobs"))}</span></div>
<div class="row"><span class="name">Residents who can get here within</span><span class="opts">{"".join(f'<label for="tq-{m}">{n}</label>' for m, n, _ in REACH if m.startswith("res"))}</span></div>
<div class="row"><span class="name">When</span><span class="opts">{"".join(f'<label for="tq-{p}">{n}</label>' for p, n in PERIODS)}</span></div>
<div class="row"><span class="name">Place names</span><span class="opts">{"".join(f'<label for="tq-{l}">{n}</label>' for l, n, _ in LABELS)}</span></div>
<div class="row"><span class="name">Transit lines</span><span class="opts">{"".join(f'<label for="tq-{l}">{n}</label>' for l, n in LINES)}</span></div>
<p class="small">Click the map for full resolution.</p>
<p class="small"><a href="history.html">How has this changed since 2009?</a></p>
<h2>Region-wide</h2>
<p class="small" style="margin:0">The average resident's average trip, in minutes:</p>
<table>
<tr><th></th><th>to jobs</th><th>to residents</th></tr>
{rows}
</table>
<p class="small" style="margin:12px 0 0">Within reach at rush hour (round trip):</p>
<table>
<tr><th></th><th>avg resident reaches<br>(share of jobs)</th><th>avg job is reachable by<br>(share of residents)</th></tr>
{reach_rows}
</table>
<div class="methods">
METHODS
</div>
</aside>
<main>
{chr(10).join(maps)}
</main>
<div class="methods-bottom">
METHODS
</div>
</div>
</body>
</html>
"""
methods = """<h2>How this was made</h2>
<p class="small">I made the original <a href="https://www.jefftk.com/p/transit-service-quality-map">2010 map</a>. This update is a collaboration with Claude Opus 5.5. Claude wrote all of the code and text, picked the data sources and routing details, and did the analysis. That includes finding most of the data problems (old schedules that made station transfers free, a sample day with a Red Line shutdown, missing walking paths inside stations) and designing the test showing that slower bus schedules explain most of the decline. I decided what to look at, including the comparison over time, the rush-hour measure, and how much traffic was slowing buses (which prompted that test), and questioned results that looked wrong. Three of those questions led to fixes: Lexington looked much worse because of a broken transfer at Alewife; Winthrop looked unreachable in 2010, though it had buses, because the old schedules left out its routes; and a square near Waverley jumped 40 minutes because a station moved a few metres across a hard walking limit, which led me to ask whether a hard limit made sense, and Claude replaced it with a gradual penalty for long walks.</p>
<ul>
<li>The map is split into @GRID@ that contain walkable streets or paths.</li>
<li>For every pair of squares Claude computed the fastest trip by MBTA subway, bus, commuter rail, ferry, and walking, using the MBTA's published Fall 2026 schedule (GTFS). Representative days are Tuesday 12/1, Saturday 12/5, and Sunday 12/6.</li>
<li>Trips run door to door between square centers, including walking on OpenStreetMap streets (1.3 m/s, about 2.9 mph; past 15 minutes, each minute of walking counts as 1.5 because long walks are a bigger burden, and walks over an hour are not used), waiting, riding, and transfer walks.</li>
<li>Every transfer between different stops takes at least two minutes. OpenStreetMap mostly lacks the paths inside stations, so transfers between stops in the same station use 1.5× the straight-line distance.</li>
<li>Each pair is averaged over departures every five minutes across the time window, so frequency counts as well as speed.</li>
<li>Rush hour averages the trip there leaving between 7 and 9am with the trip back leaving between 4:30 and 6:30pm, like a commute.</li>
<li>Trips are capped at three hours; squares that can't reach most places within that get the palest color.</li>
<li>"Jobs" weights destinations by jobs (Census LODES 2024), "Residents" by population (2020 Census), and "Everywhere" weights every square equally, like the <a href="https://www.jefftk.com/p/transit-service-quality-map">2010 map</a>. That last one depends on where the map edges are, so the weighted versions are more meaningful.</li>
<li>This uses scheduled times, not real-world performance, so delays and slow zones aren't reflected.</li>
</ul>""".replace("@GRID@", GRIDTXT)
html = html.replace("METHODS", methods)
open(f"{OUT}/index.html", "w").write(html)
print("wrote", len(html), "bytes")
