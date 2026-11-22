"""Generate the no-JS HTML fragment for jefftk.com.

Usage: gen_static.py SITE_DIR OUT_DIR [IMG_PREFIX]

Writes OUT_DIR/fragment.html (paste into a post) and OUT_DIR/preview.html
(the fragment in a 550px column, for checking locally). Images are expected
at IMG_PREFIX (default /transitq2026/).
"""
import json, sys
from PIL import Image

SITE, OUT = sys.argv[1:3]
PREFIX = sys.argv[3] if len(sys.argv) > 3 else "/transitq2026/"
G = json.load(open(f"{SITE}/grid.json"))

def grid_text(g):
    """e.g. '4,140 squares of 400m (about a quarter mile)'"""
    m = round(g["dlat"] * 111_132.0)
    size = "about a quarter mile" if abs(m - 400) < 20 else f"about {round(m * 3.281 / 50) * 50:,} feet"
    return f"{len(g['cells']):,} squares of {m}m ({size})"
GRIDTXT = grid_text(G)
IMG_H = Image.open(f"{OUT}/transitq2026/labels.png").size[1]  # map image height (depends on the grid)
METRICS = [("jobs", "Jobs", "a typical job"), ("pop", "Residents", "where a typical resident lives"),
           ("area", "Everywhere", "anywhere on the map")]
PERIODS = [("weekday_rush", "Rush hour"), ("weekday_day", "Weekday day"), ("weekday_eve", "Weekday evening"),
           ("saturday", "Saturday"), ("sunday", "Sunday")]
FULL = dict(G["periods"])
REACH = [(f"{w}{t}", f"{t} min", None) for w in ("jobs", "res") for t in (30, 45, 60)]
ALLM = METRICS + REACH  # one radio group for every map choice

css = ["""
.tq26 { margin: 1em 0; }
.tq26 > input { position: absolute; opacity: 0; width: 1px; height: 1px; margin: 0; }
.tq26 .tq-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin: 0 0 6px; }
.tq26 .tq-row span { min-width: 7.5em; font-size: 90%; color: #555; }
.tq26 label { border: 1px solid #bbb; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 90%; user-select: none; }
.tq26 label:hover { border-color: #666; }
.tq26 .tq-map { display: none; position: relative; }
.tq26 .tq-map img.lab { position: absolute; inset: 0; height: 100%; pointer-events: none; }
.tq26 .tq-map img { display: block; width: 100%; height: auto; }
.tq26 .tq-cap { font-size: 85%; color: #555; margin: 4px 0 0; }
"""]
sel_label = []
focus_label = []
for key, *_ in ALLM + PERIODS:
    sel_label.append(f"#tq-{key}:checked ~ .tq-controls label[for=tq-{key}]")
    focus_label.append(f"#tq-{key}:focus-visible ~ .tq-controls label[for=tq-{key}]")
css.append(",\n".join(sel_label) + " { background: #222; border-color: #222; color: #fff; }")
css.append(",\n".join(focus_label) + " { outline: 2px solid #2a6ebb; outline-offset: 1px; }")
show = [f"#tq-{m}:checked ~ #tq-{p}:checked ~ .tq-maps .tq-{m}-{p}" for m, *_ in ALLM for p, _ in PERIODS]
css.append(",\n".join(show) + " { display: block; }")

h = ["<style>" + "\n".join(css) + "\n</style>", '<div class="tq26">']
for i, (m, *_) in enumerate(ALLM):
    h.append(f'<input type="radio" name="tq-metric" id="tq-{m}"{" checked" if i == 0 else ""}>')
for i, (p, _) in enumerate(PERIODS):
    h.append(f'<input type="radio" name="tq-period" id="tq-{p}"{" checked" if i == 0 else ""}>')
h.append('<div class="tq-controls">')
h.append('<div class="tq-row"><span>Average trip to:</span>' + "".join(f'<label for="tq-{m}">{n}</label>' for m, n, _ in METRICS) + "</div>")
h.append('<div class="tq-row"><span>Jobs you can get to within:</span>' + "".join(f'<label for="tq-{m}">{n}</label>' for m, n, _ in REACH if m.startswith("jobs")) + "</div>")
h.append('<div class="tq-row"><span>Residents who can get here within:</span>' + "".join(f'<label for="tq-{m}">{n}</label>' for m, n, _ in REACH if m.startswith("res")) + "</div>")
h.append('<div class="tq-row"><span>When:</span>' + "".join(f'<label for="tq-{p}">{n}</label>' for p, n in PERIODS) + "</div>")
h.append("</div>")
h.append('<div class="tq-maps">')
for m, _, desc in ALLM:
    for p, _ in PERIODS:
        first = m == "jobs" and p == "weekday_rush"
        if desc:
            alt = (f"Map of Greater Boston colored by average door-to-door transit time to {desc}, "
                   f"{FULL[p]}. Darkest around downtown Boston and along rapid transit lines.")
        elif m.startswith("jobs"):
            alt = f"Map of Greater Boston colored by the share of the region's jobs reachable by transit within {m[-2:]} minutes, {FULL[p]}."
        else:
            alt = f"Map of Greater Boston colored by the share of the region's residents who can reach each square by transit within {m[-2:]} minutes, {FULL[p]}."
        h.append(f'<div class="tq-map tq-{m}-{p}"><a href="{PREFIX}{m}-{p}-big.png">'
                 f'<img src="{PREFIX}{m}-{p}.png" width="1100" height="{IMG_H}" alt="{alt}"'
                 f'{"" if first else " loading=\"lazy\""}><img class="lab" src="{PREFIX}lines.png" width="1100" height="{IMG_H}" alt="">'
                 f'<img class="lab" src="{PREFIX}labels.png" width="1100" height="{IMG_H}" alt=""></a></div>')
h.append("</div>")
h.append('<p class="tq-cap">Click the map for a larger version.</p>')
h.append("</div>")

S = G["summary"]
rows = "\n".join(f"<tr><td>{n}</td><td align=right>{round(S[p]['jobs'])}</td><td align=right>{round(S[p]['pop'])}</td></tr>"
                 for p, n in PERIODS)
h.append(f"""
<p>Region-wide, the average resident's average trip, in minutes:</p>
<table>
<tr><th></th><th>&nbsp;to jobs&nbsp;</th><th>&nbsp;to residents&nbsp;</th></tr>
{rows}
</table>

<p>I made the original <a href="/p/transit-service-quality-map">2010 map</a>. This update is a collaboration with Claude Opus 5.5. Claude wrote all of the code and text, picked the data sources and routing details, and did the analysis. That includes finding most of the data problems (old schedules that made station transfers free, a sample day with a Red Line shutdown, missing walking paths inside stations) and designing the test showing that slower bus schedules explain most of the decline. I decided what to look at, including the comparison over time, the rush-hour measure, and how much traffic was slowing buses (which prompted that test), and questioned results that looked wrong. Three of those questions led to fixes: Lexington looked much worse because of a broken transfer at Alewife; Winthrop looked unreachable in 2010, though it had buses, because the old schedules left out its routes; and a square near Waverley jumped 40 minutes because a station moved a few metres across a hard walking limit, which led me to ask whether a hard limit made sense, and Claude replaced it with a gradual penalty for long walks.</p>
<p>How this was made:</p>
<ul>
<li>The map is split into {GRIDTXT} that contain walkable streets or paths.</li>
<li>For every pair of squares Claude computed the fastest trip by MBTA subway, bus, commuter rail, ferry, and walking, using the MBTA's published Fall 2026 schedule (GTFS). Representative days are Tuesday 12/1, Saturday 12/5, and Sunday 12/6.</li>
<li>Trips run door to door from the center of one square to the center of another, including walking on OpenStreetMap streets (1.3 m/s, about 2.9 mph; past 15 minutes, each minute of walking counts as 1.5 because long walks are a bigger burden, and walks over an hour are not used), waiting, riding, and walking between transfers.</li>
<li>Each pair is averaged over departures every five minutes across the time window, so frequency counts as well as speed: a bus every 30 minutes costs about 15 minutes of waiting on average.</li>
<li>Trips are capped at three hours. Squares that can't reach most places within that get the palest color.</li>
<li>"Jobs" weights each destination by the number of jobs there (Census LODES 2024), "Residents" by population (2020 Census), and "Everywhere" weights every square equally, like the <a href="/p/transit-service-quality-map">2010 map</a>. That last one depends on where the map edges are, so the weighted versions are more meaningful.</li>
<li>This uses scheduled times, not real-world performance, so delays and slow zones aren't reflected.</li>
</ul>
""")
frag = "\n".join(h)
open(f"{OUT}/fragment.html", "w").write(frag + "\n")
open(f"{OUT}/preview.html", "w").write(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Transit map fragment preview</title>
<style>body {{ font-family: Georgia, serif; margin: 30px auto; max-width: 550px; padding: 0 16px; line-height: 1.4; }}</style>
<h2>Transit Service Quality Map, 2026</h2>
{frag}
""")
print("wrote", len(frag), "bytes")
