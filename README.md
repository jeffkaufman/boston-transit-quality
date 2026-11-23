# Boston Transit Service Quality

How long it takes to get from each part of the Boston area to a typical job (or
resident, or anywhere) by MBTA and walking, waiting included, and how that has
changed from 2009 to 2026.

This updates the 2010 map at https://www.jefftk.com/p/transit-service-quality-map.
Jeff Kaufman made the original. Claude Opus 5.5 wrote this code, working with Jeff.

## Method

- **Grid:** the area is split into squares (400m by default; set `TQ_CELL_M`, e.g. 150) that have walkable streets or paths. At 400m that's 4,140 squares; at 150m 26,456; at 100m 50,027.
- **Routing:** `pipeline/raptor.cpp` (range-RAPTOR) computes the trip between every pair of squares from the MBTA's GTFS schedules. It averages over departures every 5 minutes. It writes each square's average trip out and trip in, weighted by jobs, residents, and area, rather than the full matrix, so memory doesn't grow with the square of the grid (`TQ_MATRIX=1` also writes the matrix). Most of the time goes to egress (arrival at every square from every nearby stop); stops that can't beat a square's current worst trip time are skipped, which is exact and about a third faster.
- **Modes:** subway, bus, commuter rail, and ferry.
- **Walking:**
  - Uses OpenStreetMap paths at 1.3 m/s.
  - Past 15 minutes, each minute of walking to or from a stop (or on a walk-only trip) counts 1.5×. Walks over 60 minutes are not used.
  - A trip with no ride is a single direct walk; it can't be split at a bus stop to restart the penalty.
  - Transfers between stops are limited to 500m and take at least 2 minutes.
  - Stops in the same station (GTFS `parent_station`) connect at 1.5× straight-line distance.
- **Trip cap:** trips are capped at 3 hours.
- **Reachable jobs:** the router also records the share of the region's jobs and residents reachable within 30, 45, and 60 minutes, averaged over departures (rush hour: out in the morning, home in the evening). The 2026 page maps them ("Jobs you can get to within" and "Residents who can get here within"); the history page maps the 45-minute versions by year and as changes, charts all three, and tracks a "transit area" (homes with at least 10% of jobs within 45 minutes; `pipeline/reach.py`).
- **Measures:**
  - Jobs (LODES 2024).
  - Residents (2020 Census).
  - Anywhere: every square counts equally, as in the 2010 map.
- **Periods:**
  - Weekday 7am–7pm.
  - Rush hour: out 7–9am averaged with back 4:30–6:30pm.
  - Weekday evening.
  - Saturday.
  - Sunday.
- **History:**
  - Each year 2009–2026 uses the archived schedule for a mid-November Tuesday.
  - Population, jobs, and streets stay at today's values, so only the schedules differ.
  - The 2009–2014 feeds lack contracted routes 710/712/713/716. `pipeline/splice_routes.py` adds them from the December 2014 feed.
  - 2024 uses Nov 12 because Nov 19 had a Red Line shutdown.

## Running

You need Python 3 with `requirements.txt`, clang++ (C++17), and about 6 GB of disk (mostly the downloaded schedules).

    pip install -r requirements.txt
    ./fetch_data.sh /some/big/dir      # MBTA feeds, Census blocks, LODES, OSM walkways
    ./run_all.sh /some/big/dir         # about 30 min at 400m; ~4 h at 150m, ~10 h at 100m (TQ_CELL_M)

`TQ_KEEP_CF=1` skips the bus-speed counterfactual (one region-wide number) and keeps
`intermediates/speed_counterfactual.json` from an earlier run.

On macOS, if linking fails, set `SDKROOT` to an SDK that works, e.g.
`SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk`.

Outputs:

- `out/transitq2026/`: static pages for jefftk.com (no libraries; the history page's year picker uses a little vanilla JavaScript and the rest works without it).
  - `index.html`: the 2026 map.
  - `history.html`: 2009–2026. "Pick years" draws the change between any two years in the browser from `cmp/` (per-year data, ~400 KB a year at 100m).
  - Map images are 1100px, plus 2200px `-big` versions.
  - `labels.png` is a place-name overlay.
- `out/fragment.html`: the 2026 map as a fragment to paste into a post.
- `out/data/`: per-square averages, transit lines, and water outlines that the renderers read.
- `intermediates/`: small JSON summaries, and `intermediates/hist/`, the per-year extract the history pages are built from (see `pipeline/histdata.py`). Keep it: rebuilding it means rerunning hours of routing.

The OSM extract is fetched live, so streets (and results) will drift slightly from the published version.

## Layout

- `pipeline/`: everything `run_all.sh` uses.
  - `prep.py`: grid, walking graph, timetables → binary inputs for raptor.
  - `raptor.cpp`: all-pairs travel-time matrices.
  - `build.py`, `render.py`, `gen_static.py`, `gen_fullpage.py`: the 2026 map.
  - `hist.py`, `hist_extract.py`, `hist_lines.py`, `histdata.py`, `hist_render.py`, `hist_page.py`, `compare.js`, `change_breakdown.py`, `trips_count.py`, `splice_routes.py`: history.
  - `scale_bus.py`, `counterfactual.py`: rerun schedules at another year's bus speeds.
- `analysis/`: one-off investigations.
  - Bus speeds, rail headways, station transfer distances, and per-area comparisons.
  - `diag_2010.py` / `compare_2010.py` / `raptor_diag.cpp`: comparing with the 2010 map's assumptions.
