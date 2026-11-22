#!/bin/zsh
# Build everything from downloaded data. Run from the repo root.
# Usage: ./run_all.sh BASE_DIR
#   BASE_DIR/data must hold the inputs listed in README.md; working files go in
#   BASE_DIR/work, BASE_DIR/histwork, BASE_DIR/cfwork. Small summaries go in
#   ./intermediates and pages in ./out. Set PY to choose the Python interpreter and
#   TQ_CELL_M for the grid square size in metres (default 400), and TQ_KEEP_CF=1 to skip
#   recomputing the bus-speed counterfactual.
# Routing steps whose outputs already exist are skipped, so an interrupted run can be
# resumed; delete BASE_DIR/work, histwork, and cfwork to recompute from scratch.
set -e
B=${1:?usage: run_all.sh BASE_DIR}; D=$B/data; W=$B/work; PY=${PY:-python3}
mkdir -p $W $B/histwork $B/cfwork intermediates out/transitq2026 out/data
R=$B/raptor
SYSROOT=(); [ -n "$SDKROOT" ] && SYSROOT=(-isysroot $SDKROOT)
clang++ -O3 -std=c++17 $SYSROOT -o $R pipeline/raptor.cpp
step() { echo "[$(date +%H:%M)] $*"; }

# ---- 2026 ----
step 2026 prep
[ -f $W/weights.f64 ] || $PY -I pipeline/prep.py $D $W intermediates
# weekday 7am-7pm, plus the rush-hour windows (out 7-9am, back 4:30-6:30pm) from the same pass
step 2026 routing
[ -f $W/pm.m ] || $R $W weekday 25200 68400 300 $W/weekday_day.m 25200 32400 $W/am.m 59400 66600 $W/pm.m 2>/dev/null
[ -f $W/weekday_eve.m ] || $R $W weekday 68400 82800 300 $W/weekday_eve.m 2>/dev/null
[ -f $W/saturday.m ] || $R $W saturday 32400 75600 300 $W/saturday.m 2>/dev/null
[ -f $W/sunday.m ] || $R $W sunday 32400 75600 300 $W/sunday.m 2>/dev/null
step 2026 pages
$PY -I pipeline/build.py $D $W intermediates out/data
$PY -I pipeline/render.py out/data out/transitq2026
$PY -I pipeline/gen_static.py out/data out
$PY -I pipeline/gen_fullpage.py out/data out/transitq2026
step 2026 done

# ---- History ----
# add contracted routes missing from the 2009-2014 feeds
for f in 20091106:20091117 20101119:20101123 20111117:20111122 20121031:20121120 20131115:20131119 20140815:20141118; do
  feed=${f%%:*}; day=${f##*:}
  [ -d $D/hist/$feed-spliced ] || $PY -I pipeline/splice_routes.py $D/hist/$feed $D/hist/20141212 20150106 $day $D/hist/$feed-spliced 710 712 713 716
done
step history routing
$PY -I pipeline/hist.py $D $B/histwork intermediates $R   # caches finished years in histwork/hist.json
# systemwide weekday trips per year (bus vs rail/ferry) and bus speeds, for the history page
step history stats
$PY -c "
import json, os, re, subprocess, sys
H = json.load(open('$B/histwork/hist.json')); out = {}
feed = lambda r: '$D/hist/' + r['feed'] if r['feed'] else '$D/gtfs'
for y, r in sorted(H.items()):
    s = subprocess.run([sys.executable, '-I', 'pipeline/trips_count.py', feed(r), r['date']], capture_output=True, text=True, check=True).stdout
    n = lambda k: int(re.search(k + r'=(\\d+)', s).group(1))
    out[y] = {'date': r['date'], 'bus': n('ALL bus'), 'rail_ferry': n('ALL rail/ferry'), 'bus_hours': n('bus_hours')}
json.dump(out, open('intermediates/service_counts.json', 'w'), indent=1)
os.makedirs('intermediates/bus_speed', exist_ok=True)
for y, r in sorted(H.items()):
    s = subprocess.run([sys.executable, '-I', 'pipeline/bus_speed.py', feed(r), r['date']], capture_output=True, text=True, check=True).stdout
    open(f'intermediates/bus_speed/{y}.json', 'w').write(s)"

# ---- Bus-speed counterfactual: 2026 at 2010 bus speeds and 2010 at 2026 speeds ----
# It's one region-wide number, so TQ_KEEP_CF=1 keeps intermediates/speed_counterfactual.json
# from an earlier (e.g. coarser) run instead of recomputing it.
if [ -z "$TQ_KEEP_CF" ]; then
step counterfactual
K=$($PY -c "print(13.70/16.76)"); KI=$($PY -c "print(16.76/13.70)")
[ -d $D/cf/2026fast ] || $PY -I pipeline/scale_bus.py $D/gtfs $D/cf/2026fast $K
[ -d $D/cf/2010slow ] || $PY -I pipeline/scale_bus.py $D/hist/20101119-spliced $D/cf/2010slow $KI
for x in 2026fast:20261201 2010slow:20101123; do n=${x%%:*}; d=${x##*:}
  [ -f $B/cfwork/$n/weights.f64 ] || $PY -I pipeline/prep.py $D $B/cfwork/$n $B/cfwork/inter $D/cf/$n "{\"weekday\":\"$d\"}" >/dev/null
  [ -f $B/cfwork/$n/m.m ] || $R $B/cfwork/$n weekday 25200 68400 300 $B/cfwork/$n/m.m 2>/dev/null
done
$PY -I pipeline/counterfactual.py $B
fi

# ---- History pages ----
step history pages
TQ_SITE=out/data $PY -I pipeline/hist_render.py $B/histwork/hist.json out/transitq2026
$PY -I pipeline/change_breakdown.py $B/histwork/hist.json $D/hist/20091106-spliced $D/gtfs intermediates/change_breakdown.json
$PY -I pipeline/hist_page.py $B/histwork/hist.json intermediates/service_counts.json out/transitq2026
step all done
