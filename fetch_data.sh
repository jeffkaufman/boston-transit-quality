#!/bin/zsh
# Download all inputs into BASE_DIR/data. Usage: ./fetch_data.sh BASE_DIR
set -e
D=${1:?usage: fetch_data.sh BASE_DIR}/data
mkdir -p $D/gtfs $D/hist $D/tiger $D/lodes $D/osm
A=https://cdn.mbtace.com/archive
get_feed() { [ -f $2/stops.txt ] || { mkdir -p $2; curl -sfL $A/$1.zip -o $2.zip; unzip -oq $2.zip -d $2; rm $2.zip; } }

# 2026 map: the Fall 2026 feed (version D) the published maps used
get_feed 20261112 $D/gtfs
# history: one feed per November (names are feed_start_date in archived_feeds.txt),
# plus 20141212, the source of the contracted routes added to 2009-2014
for f in 20091106 20101119 20111117 20121031 20131115 20140815 20141212 20150821 20161103 20171114 \
         20181113 20191114 20201112 20211116 20221121 20231116 20241112 20251118; do
  get_feed $f $D/hist/$f
done

# 2020 Census blocks for Massachusetts (population)
[ -f $D/tiger/tl_2020_25_tabblock20.shp ] || {
  curl -sfL https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_25_tabblock20.zip -o $D/tiger/blocks.zip
  unzip -oq $D/tiger/blocks.zip -d $D/tiger; }
# Jobs by workplace block, LODES 2024
[ -f $D/lodes/wac.csv.gz ] || curl -sfL https://lehd.ces.census.gov/data/lodes/LODES8/ma/wac/ma_wac_S000_JT00_2024.csv.gz -o $D/lodes/wac.csv.gz
# Walkable ways from OpenStreetMap (changes over time; results will differ slightly)
Q='[out:json][timeout:600];way["highway"]["highway"!~"motorway|motorway_link|trunk_link|construction|proposed|raceway|bus_guideway"]["foot"!~"no|private"]["access"!~"private|no"](42.19,-71.31,42.51,-70.89);(._;>;);out skel qt;'
[ -f $D/osm/walk.json ] || curl -sf --data-urlencode "data=$Q" https://overpass-api.de/api/interpreter -o $D/osm/walk.json
echo fetched
