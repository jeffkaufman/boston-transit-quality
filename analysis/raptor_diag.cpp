// All-pairs cell-to-cell transit travel times, averaged over departure times.
//
// Usage: raptor WORK_DIR DAY START_SEC END_SEC STEP_SEC OUT_FILE
//
// DIAGNOSTIC COPY (diag_2010): env TQ_AGG=min takes the best departure instead of the mean;
// TQ_WALK sets walking speed in m/s.
// Writes an NC x NC float32 matrix of mean travel time in minutes (row =
// origin, col = destination). Uses range-RAPTOR (departures processed latest
// first, labels kept between them) with walking access/egress/transfers on the
// OSM pedestrian network.
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <queue>
#include <string>
#include <thread>
#include <vector>
using namespace std;

static double WALK_MPS = getenv("TQ_WALK") ? atof(getenv("TQ_WALK")) : 1.3;          // ~2.9 mph
static const int MAX_ACCESS_M = 2400;        // ~31 min walk to/from transit
static const int MAX_DIRECT_M = 5000;        // walk-only trips up to ~64 min
static const int MAX_TRANSFER_M = 500;       // ~6.4 min transfer walks
// Every transfer between different stops takes at least this long. Older feeds
// put all of a station's platforms at one point, which would otherwise make
// station transfers free; this keeps years comparable.
static const int MIN_TRANSFER_S = 120;
static const int K = 6;                      // max transit legs
static const bool AGG_MIN = getenv("TQ_AGG") && string(getenv("TQ_AGG")) == "min";
static const int CAP_SEC = 180 * 60;         // cap travel time at 3 hours
static const int INF = 1 << 29;

template <class T> vector<T> load(const string& path) {
  FILE* f = fopen(path.c_str(), "rb");
  if (!f) { fprintf(stderr, "can't open %s\n", path.c_str()); exit(1); }
  fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
  vector<T> v(n / sizeof(T));
  if (fread(v.data(), sizeof(T), v.size(), f) != v.size()) exit(2);
  fclose(f);
  return v;
}

vector<int> g_offs, g_dst, g_len;

// Dijkstra from a node; returns (node, dist) pairs within limit.
struct DijkstraWS { vector<int> dist; vector<int> touched; };
void dijkstra(int src, int limit, DijkstraWS& ws, vector<pair<int,int>>& out) {
  if (ws.dist.empty()) ws.dist.assign(g_offs.size() - 1, INF);
  for (int t : ws.touched) ws.dist[t] = INF;
  ws.touched.clear(); out.clear();
  priority_queue<pair<int,int>, vector<pair<int,int>>, greater<>> pq;
  ws.dist[src] = 0; ws.touched.push_back(src); pq.push({0, src});
  while (!pq.empty()) {
    auto [d, u] = pq.top(); pq.pop();
    if (d > ws.dist[u]) continue;
    out.push_back({u, d});
    for (int e = g_offs[u]; e < g_offs[u + 1]; e++) {
      int v = g_dst[e], nd = d + g_len[e];
      if (nd <= limit && nd < ws.dist[v]) {
        if (ws.dist[v] == INF) ws.touched.push_back(v);
        ws.dist[v] = nd; pq.push({nd, v});
      }
    }
  }
}

int main(int argc, char** argv) {
  if (argc < 7) { fprintf(stderr, "usage\n"); return 1; }
  string W = argv[1], day = argv[2];
  int T0 = atoi(argv[3]), T1 = atoi(argv[4]), STEP = atoi(argv[5]);
  string outpath = argv[6];
  int nthreads = max(1u, thread::hardware_concurrency());

  g_offs = load<int>(W + "/g_offs.i32"); g_dst = load<int>(W + "/g_dst.i32"); g_len = load<int>(W + "/g_len.i32");
  int NC = load<int>(W + "/cells_n.i32")[0], NS = load<int>(W + "/stops_n.i32")[0];
  auto cell_node = load<int>(W + "/cell_node.i32"), cell_snap = load<int>(W + "/cell_snap.i32");
  auto stop_node = load<int>(W + "/stop_node.i32"), stop_snap = load<int>(W + "/stop_snap.i32");
  string P = W + "/" + day + "_";
  int NP = load<int>(P + "np.i32")[0];
  auto p_off = load<int>(P + "p_off.i32"), p_stops = load<int>(P + "p_stops.i32"),
       p_flags = load<int>(P + "p_flags.i32"), p_toff = load<int>(P + "p_toff.i32"),
       times = load<int>(P + "times.i32");
  fprintf(stderr, "%d cells, %d stops, %d patterns\n", NC, NS, NP);

  // node -> cells / stops snapped there
  int NN = g_offs.size() - 1;
  vector<vector<int>> node_cells(NN), node_stops(NN);
  for (int c = 0; c < NC; c++) node_cells[cell_node[c]].push_back(c);
  for (int s = 0; s < NS; s++) node_stops[stop_node[s]].push_back(s);

  // walking: cell->stop (access, also egress by symmetry), cell->cell direct, stop->stop transfers
  vector<vector<pair<int,int>>> access(NC), direct(NC), transfers(NS);  // (target, seconds)
  {
    atomic<int> next(0);
    vector<thread> th;
    for (int t = 0; t < nthreads; t++) th.emplace_back([&] {
      DijkstraWS ws; vector<pair<int,int>> out;
      for (int c; (c = next++) < NC + NS;) {
        if (c < NC) {
          dijkstra(cell_node[c], MAX_DIRECT_M, ws, out);
          for (auto [u, d] : out) {
            for (int s : node_stops[u]) {
              int m = d + cell_snap[c] + stop_snap[s];
              if (m <= MAX_ACCESS_M) access[c].push_back({s, int(m / WALK_MPS)});
            }
            for (int c2 : node_cells[u]) {
              int m = d + cell_snap[c] + cell_snap[c2];
              direct[c].push_back({c2, int(m / WALK_MPS)});
            }
          }
        } else {
          int s = c - NC;
          if (stop_snap[s] > MAX_TRANSFER_M) continue;
          dijkstra(stop_node[s], MAX_TRANSFER_M, ws, out);
          for (auto [u, d] : out)
            for (int s2 : node_stops[u]) {
              if (s2 == s) continue;
              int m = d + stop_snap[s] + stop_snap[s2];
              if (m <= MAX_TRANSFER_M) transfers[s].push_back({s2, max(MIN_TRANSFER_S, int(m / WALK_MPS))});
            }
        }
      }
    });
    for (auto& x : th) x.join();
  }
  // In-station transfers from GTFS parent_station (see prep.py); keep the faster.
  {
    FILE* f = fopen((W + "/station_xfers.i32").c_str(), "rb");
    if (f) {
      vector<int> v; int x;
      while (fread(&x, 4, 1, f) == 1) v.push_back(x);
      fclose(f);
      long added = 0, improved = 0;
      for (size_t k = 0; k + 2 < v.size(); k += 3) {
        int s = v[k], s2 = v[k + 1], sec = max(MIN_TRANSFER_S, int(v[k + 2] / WALK_MPS));
        bool found = false;
        for (auto& [t, w] : transfers[s])
          if (t == s2) { found = true; if (sec < w) { w = sec; improved++; } }
        if (!found) { transfers[s].push_back({s2, sec}); added++; }
      }
      fprintf(stderr, "station transfers: %ld added, %ld shortened\n", added, improved);
    }
  }
  vector<vector<pair<int,int>>> egress(NC);  // cell -> (stop, sec)
  for (int c = 0; c < NC; c++) egress[c] = access[c];
  long na = 0, nt = 0;
  for (auto& v : access) na += v.size();
  for (auto& v : transfers) nt += v.size();
  fprintf(stderr, "walking done: %ld access links, %ld transfers\n", na, nt);

  // stop -> (pattern, position)
  vector<vector<pair<int,int>>> stop_pats(NS);
  for (int p = 0; p < NP; p++)
    for (int i = p_off[p]; i < p_off[p + 1]; i++) stop_pats[p_stops[i]].push_back({p, i - p_off[p]});

  vector<int> deps;
  for (int t = T1 - STEP; t >= T0; t -= STEP) deps.push_back(t);  // latest first
  int ND = deps.size();
  vector<float> result((size_t)NC * NC);

  atomic<int> next(0);
  vector<thread> th;
  for (int t = 0; t < nthreads; t++) th.emplace_back([&] {
    vector<vector<int>> tau(K + 1, vector<int>(NS));
    vector<int> best(NS);
    vector<char> marked(NS), pmarked(NP);
    vector<int> pmin(NP);
    vector<double> sum(NC);
    vector<int> cellarr(NC);
    for (int o; (o = next++) < NC;) {
      for (auto& v : tau) fill(v.begin(), v.end(), INF);
      fill(best.begin(), best.end(), INF);
      fill(sum.begin(), sum.end(), AGG_MIN ? 1e18 : 0.0);
      for (int dep : deps) {
        // round 0: access walk
        fill(marked.begin(), marked.end(), 0);
        for (auto [s, w] : access[o]) {
          int a = dep + w;
          if (a < tau[0][s]) { tau[0][s] = a; if (a < best[s]) best[s] = a; marked[s] = 1; }
        }
        for (int k = 1; k <= K; k++) {
          // collect patterns
          vector<int> plist;
          for (int s = 0; s < NS; s++) if (marked[s]) {
            for (auto [p, i] : stop_pats[s]) {
              if (!pmarked[p]) { pmarked[p] = 1; pmin[p] = i; plist.push_back(p); }
              else if (i < pmin[p]) pmin[p] = i;
            }
          }
          fill(marked.begin(), marked.end(), 0);
          bool any = false;
          vector<int> newly;
          for (int p : plist) {
            pmarked[p] = 0;
            int L = p_off[p + 1] - p_off[p];
            int ntr = (p_toff[p + 1] - p_toff[p]) / (2 * L);
            const int* tt = &times[p_toff[p]];
            int trip = -1;
            for (int i = pmin[p]; i < L; i++) {
              int s = p_stops[p_off[p] + i], fl = p_flags[p_off[p] + i];
              if (trip >= 0 && !(fl & 2)) {
                int arr = tt[(trip * L + i) * 2];
                if (arr < best[s] && arr < tau[k][s]) {
                  tau[k][s] = arr; best[s] = arr;
                  if (!marked[s]) { marked[s] = 1; newly.push_back(s); }
                  any = true;
                }
              }
              int prev = tau[k - 1][s];
              if (prev < INF && !(fl & 1) && (trip < 0 || prev <= tt[(trip * L + i) * 2 + 1])) {
                // earliest trip departing >= prev (binary search; FIFO pattern)
                int lo = 0, hi = (trip < 0 ? ntr : trip);
                while (lo < hi) { int mid = (lo + hi) / 2; if (tt[(mid * L + i) * 2 + 1] >= prev) hi = mid; else lo = mid + 1; }
                if (lo < ntr && (trip < 0 || lo < trip)) trip = lo;
              }
            }
          }
          // transfers from stops improved this round
          for (int s : newly) {
            for (auto [s2, w] : transfers[s]) {
              int a = tau[k][s] + w;
              if (a < best[s2] && a < tau[k][s2]) { tau[k][s2] = a; best[s2] = a; marked[s2] = 1; any = true; }
            }
          }
          if (!any) break;
        }
        // egress
        for (int c = 0; c < NC; c++) cellarr[c] = INF;
        for (auto [c2, w] : direct[o]) cellarr[c2] = min(cellarr[c2], dep + w);
        for (int c = 0; c < NC; c++) {
          int a = cellarr[c];
          for (auto [s, w] : egress[c]) { int x = best[s] + w; if (x < a) a = x; }
          int tt = min(a - dep, CAP_SEC);
          if (AGG_MIN) sum[c] = min(sum[c], double(tt)); else sum[c] += tt;
        }
      }
      for (int c = 0; c < NC; c++) result[(size_t)o * NC + c] = float((AGG_MIN ? sum[c] : sum[c] / ND) / 60.0);
      if (o % 200 == 0) fprintf(stderr, "origin %d\n", o);
    }
  });
  for (auto& x : th) x.join();
  FILE* f = fopen(outpath.c_str(), "wb");
  fwrite(result.data(), sizeof(float), result.size(), f);
  fclose(f);
  fprintf(stderr, "wrote %s\n", outpath.c_str());
}
