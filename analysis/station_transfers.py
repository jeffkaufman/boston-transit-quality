"""Walking-network distance between stops whose names match, as the router sees it
(stop snap + network path + stop snap). Usage: station_transfers.py WORK NAME [NAME..]"""
import heapq, json, sys
import numpy as np
W = sys.argv[1]
offs = np.fromfile(f"{W}/g_offs.i32", np.int32); dst = np.fromfile(f"{W}/g_dst.i32", np.int32); ln = np.fromfile(f"{W}/g_len.i32", np.int32)
sn = np.fromfile(f"{W}/stop_node.i32", np.int32); sd = np.fromfile(f"{W}/stop_snap.i32", np.int32)
stops = json.load(open(f"{W}/stops.json"))["stops"]
def dij(src, lim=1500):
    d = {src: 0}; q = [(0, src)]
    while q:
        x, u = heapq.heappop(q)
        if x > d.get(u, 1e18) or x > lim: continue
        for e in range(offs[u], offs[u + 1]):
            v, y = dst[e], x + ln[e]
            if y < d.get(v, 1e18): d[v] = y; heapq.heappush(q, (y, v))
    return d
for name in sys.argv[2:]:
    ids = [i for i, s in enumerate(stops) if name.lower() in s[1].lower()]
    print("==", name)
    for i in ids:
        d = dij(sn[i])
        row = []
        for j in ids:
            if j != i:
                m = d.get(sn[j]); row.append("x" if m is None else str(int(m + sd[i] + sd[j])))
        print(f"  {stops[i][0]:>12} snap{sd[i]:4d} {stops[i][1][:38]:38}", " ".join(row))
