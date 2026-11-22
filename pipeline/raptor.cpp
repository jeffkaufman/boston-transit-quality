// All-pairs cell-to-cell transit travel times, averaged over departure times.
//
// Usage: raptor WORK_DIR DAY START_SEC END_SEC STEP_SEC OUT_FILE [SUB_START SUB_END SUB_OUT]...
//
// Each SUB window (inside START-END) also gets its own matrix, averaged over just
// the departures in [SUB_START, SUB_END), from the same pass.
//
// For each window, writes OUT as float64 [6 + 4*NT][NC] (NT = 24 thresholds, 5..120 min):
//   0-2   each cell's mean travel time in minutes to all cells (trips out), weighted
//         by jobs, residents, and area
//   3-5   the same for trips from all cells to it (trips in)
//   6 + 2t, 7 + 2t           share of the region's jobs / residents reachable on a trip
//                            out within 5*(t+1) minutes, averaged over departures
//   6 + 2NT + 2t, 7 + 2NT + 2t  the same for trips in: share of jobs / residents from
//                            which the cell can be reached within 5*(t+1) minutes
// The weights come from WORK/weights.f64 (prep.py). With TQ_MATRIX=1 it also writes the full
// NC x NC float32 matrix (row = origin, col = destination) to OUT.f32; that needs
// NC*NC*4 bytes of memory per window. Uses range-RAPTOR (departures processed latest
// first, labels kept between them) with walking access/egress/transfers on the
// OSM pedestrian network.
#include <algorithm>
#include <atomic>
#include <mutex>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <queue>
#include <string>
#include <thread>
#include <vector>
using namespace std;

static const double WALK_MPS = 1.3;          // ~2.9 mph
// Walking to/from transit and walk-only trips: minutes past the first 15 count
// 1.5x (people dislike long walks), instead of a hard cutoff that makes results
// jump when a stop moves a few metres. Walks over 60 minutes are not considered.
static const double WALK_EASY_S = 15 * 60;
static const double WALK_PENALTY = 1.5;
static const int MAX_ACCESS_M = 4680;        // 60 min walk to/from transit
static const int MAX_DIRECT_M = 4680;        // walk-only trips up to 60 min
static inline int walk_cost(int m) {
  double t = m / WALK_MPS;
  return int(t <= WALK_EASY_S ? t : WALK_EASY_S + WALK_PENALTY * (t - WALK_EASY_S));
}
static const int MAX_TRANSFER_M = 500;       // ~6.4 min transfer walks
// Every transfer between different stops takes at least this long. Older feeds
// put all of a station's platforms at one point, which would otherwise make
// station transfers free; this keeps years comparable.
static const int MIN_TRANSFER_S = 120;
static const int K = 6;                      // max transit legs
static const int CAP_SEC = 180 * 60;         // cap travel time at 3 hours
static const int INF = 1 << 29;
static const int REACH_STEP_S = 5 * 60;                   // reach thresholds: 5, 10, ..., 120 min
static const int NT = 24;
static const int NM = 6 + 4 * NT;                          // rows per output window

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
  // output windows: [0] is the full range, then any sub-windows
  struct Win { int t0, t1; string out; };
  vector<Win> wins = {{T0, T1, outpath}};
  for (int a = 7; a + 2 < argc; a += 3) wins.push_back({atoi(argv[a]), atoi(argv[a + 1]), argv[a + 2]});
  int NW = wins.size();
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
              if (m <= MAX_ACCESS_M) access[c].push_back({s, walk_cost(m)});
            }
            for (int c2 : node_cells[u]) {
              int m = d + cell_snap[c] + cell_snap[c2];
              if (m <= MAX_DIRECT_M) direct[c].push_back({c2, walk_cost(m)});
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
  // egress walks (stop -> cell, the reverse of access), flattened per cell, shortest first
  vector<int> e_off(NC + 1, 0), e_stop, e_w;
  for (int c = 0; c < NC; c++) {
    auto v = access[c];
    sort(v.begin(), v.end(), [](auto& x, auto& y) { return x.second < y.second || (x.second == y.second && x.first < y.first); });
    for (auto [s, w] : v) { e_stop.push_back(s); e_w.push_back(w); }
    e_off[c + 1] = e_stop.size();
  }
  // direct walks deduplicated to the shortest per target cell
  for (auto& v : direct) {
    sort(v.begin(), v.end());
    vector<pair<int,int>> u;
    for (auto& x : v) if (u.empty() || u.back().first != x.first) u.push_back(x);
    v.swap(u);
  }
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
  // which windows each departure counts toward, and how many departures each has
  // Departures run latest first, so each window is a contiguous range of indices.
  int ND = deps.size();
  vector<int> wlo(NW, ND), whi(NW, 0), wn(NW, 0);
  for (int d = 0; d < ND; d++)
    for (int w = 0; w < NW; w++)
      if (deps[d] >= wins[w].t0 && deps[d] < wins[w].t1) { wlo[w] = min(wlo[w], d); whi[w] = d + 1; wn[w]++; }
  bool want_matrix = getenv("TQ_MATRIX") && atoi(getenv("TQ_MATRIX"));
  vector<vector<float>> result(want_matrix ? NW : 0, vector<float>((size_t)NC * NC));
  auto wt = load<double>(W + "/weights.f64");  // [3][NC]: jobs, pop, area
  if ((int)wt.size() != 3 * NC) { fprintf(stderr, "weights.f64 doesn't match cells\n"); return 1; }
  double wsum[3] = {0, 0, 0};
  for (int j = 0; j < 3; j++) for (int c = 0; c < NC; c++) wsum[j] += wt[(size_t)j * NC + c];
  // metrics[w][j][c]: rows as described at the top of the file
  vector<vector<double>> metrics(NW, vector<double>(NM * (size_t)NC, 0.0));
  mutex mtx;

  atomic<int> next(0);
  vector<thread> th;
  for (int t = 0; t < nthreads; t++) th.emplace_back([&] {
    vector<vector<int>> tau(K + 1, vector<int>(NS));
    vector<char> marked(NS), pmarked(NP);
    vector<int> pmin(NP);
    // et[s]: best arrival at s by a trip with at least one transit leg. Walk-only
    // arrivals at stops are not used for egress: a trip with no transit is a direct
    // walk, and splitting it at a stop would restart the long-walk penalty.
    // er[s]: arrival at s straight off a ride; et adds one transfer walk after it
    vector<int> et(NS), er(NS), etlist;
    vector<char> etm(NS);
    vector<int> Bst((size_t)NS * ND);  // et for each stop and departure, [stop][dep]
    vector<int> A(ND), TT(ND), dw(NC, INF), smin(NS);
    vector<vector<double>> colacc(NW, vector<double>(3 * (size_t)NC, 0.0));  // this thread's column sums
    vector<vector<double>> colreach(NW, vector<double>(2 * NT * (size_t)NC, 0.0));  // [c][t*2+j]
    vector<int> hist(NT + 1);
    for (int o; (o = next++) < NC;) {
      for (auto& v : tau) fill(v.begin(), v.end(), INF);
      fill(et.begin(), et.end(), INF);
      fill(er.begin(), er.end(), INF);
      for (int di = 0; di < ND; di++) {
        int dep = deps[di];
        // round 0: access walk
        fill(marked.begin(), marked.end(), 0);
        for (auto [s, w] : access[o]) {
          int a = dep + w;
          if (a < tau[0][s]) { tau[0][s] = a; marked[s] = 1; }
        }
        for (int k = 1; k <= K; k++) {
          // tau[k] = best arrival with at most k rides. Labels are kept across
          // departures, so prune against this rather than against arrivals in any
          // round, which may have used more rides than are left.
          {
            int* __restrict tk = tau[k].data();
            const int* __restrict tp = tau[k - 1].data();
            for (int st = 0; st < NS; st++) tk[st] = min(tk[st], tp[st]);
          }
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
                if (arr < er[s]) {  // even if walking here was faster
                  er[s] = arr;
                  if (arr < et[s]) et[s] = arr;
                  if (!etm[s]) { etm[s] = 1; etlist.push_back(s); }
                }
                if (arr < tau[k][s]) {
                  tau[k][s] = arr;
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
              if (a < tau[k][s2]) { tau[k][s2] = a; marked[s2] = 1; any = true; }
            }
          }
          // egress after a ride may also include one transfer walk
          for (int s : etlist) {
            etm[s] = 0;
            for (auto [s2, w] : transfers[s]) if (er[s] + w < et[s2]) et[s2] = er[s] + w;
          }
          etlist.clear();
          if (!any) break;
        }
        for (int st = 0; st < NS; st++) Bst[(size_t)st * ND + di] = et[st];
      }
      // egress: arrival at each cell for every departure at once (vectorizes over
      // departures), then the shorter of that and walking straight there
      for (auto [c2, wd] : direct[o]) dw[c2] = wd;
      vector<double> rowacc(NW * 3, 0.0), rowreach(NW * NT * 2, 0.0);
      const int nd = ND;  // local copies so the compiler can vectorize
      const int* __restrict B0 = Bst.data();
      // smin[s]: s's best trip time over all departures. A stop can't help a cell if its
      // walk plus smin is no better than the cell's worst trip time so far (exact pruning)
      for (int st = 0; st < NS; st++) {
        const int* b = B0 + (size_t)st * nd; int m = INF;
        for (int d = 0; d < nd; d++) m = min(m, b[d] - deps[d]);
        smin[st] = m;
      }
      for (int c = 0; c < NC; c++) {
        int* __restrict a = A.data();
        const int wd0 = min(dw[c], CAP_SEC);  // walking straight there, capped
        for (int d = 0; d < nd; d++) a[d] = deps[d] + wd0;
        int amax = wd0;
        for (int k = e_off[c]; k < e_off[c + 1]; k++) {
          const int w = e_w[k];
          if (w >= amax) break;  // sorted by walk, so no later stop can help either
          if (w + smin[e_stop[k]] >= amax) continue;
          const int* __restrict b = B0 + (size_t)e_stop[k] * nd;
          for (int d = 0; d < nd; d++) a[d] = min(a[d], b[d] + w);
          int mx = 0;
          for (int d = 0; d < nd; d++) mx = max(mx, a[d] - deps[d]);
          amax = mx;
        }
        for (int d = 0; d < ND; d++) TT[d] = a[d] - deps[d];
        for (int w = 0; w < NW; w++) {
          long sm = 0;
          for (int d = wlo[w]; d < whi[w]; d++) sm += TT[d];
          float v = float((double)sm / wn[w] / 60.0);
          if (want_matrix) result[w][(size_t)o * NC + c] = v;
          for (int j = 0; j < 3; j++) {
            rowacc[w * 3 + j] += wt[(size_t)j * NC + c] * v;
            colacc[w][(size_t)j * NC + c] += wt[(size_t)j * NC + o] * v;
          }
          // share of departures from which c is reached within each threshold
          // (bucket each departure once by trip time, then running totals)
          fill(hist.begin(), hist.end(), 0);
          for (int d = wlo[w]; d < whi[w]; d++) {
            int b = TT[d] <= 0 ? 0 : (TT[d] - 1) / REACH_STEP_S;  // within threshold t+1 if b <= t
            hist[min(b, NT)]++;
          }
          double* col = &colreach[w][(size_t)c * 2 * NT];
          const double wj0 = wt[c], wj1 = wt[(size_t)NC + c], wo0 = wt[o], wo1 = wt[(size_t)NC + o];
          int cnt = 0;
          for (int t = 0; t < NT; t++) {
            cnt += hist[t];
            if (!cnt) continue;
            double f = (double)cnt / wn[w];
            rowreach[(w * NT + t) * 2] += wj0 * f;
            rowreach[(w * NT + t) * 2 + 1] += wj1 * f;
            col[t * 2] += wo0 * f;
            col[t * 2 + 1] += wo1 * f;
          }
        }
      }
      for (int w = 0; w < NW; w++)
      {
        for (int j = 0; j < 3; j++) metrics[w][(size_t)j * NC + o] = rowacc[w * 3 + j] / wsum[j];
        for (int t = 0; t < NT; t++)
          for (int j = 0; j < 2; j++)
            metrics[w][(size_t)(6 + t * 2 + j) * NC + o] = rowreach[(w * NT + t) * 2 + j] / wsum[j];
      }
      for (auto [c2, wd] : direct[o]) dw[c2] = INF;
      if (o % 200 == 0) fprintf(stderr, "origin %d\n", o);
    }
    lock_guard<mutex> lk(mtx);
    for (int w = 0; w < NW; w++)
      for (int j = 0; j < 3; j++)
        for (int c = 0; c < NC; c++) metrics[w][(size_t)(3 + j) * NC + c] += colacc[w][(size_t)j * NC + c] / wsum[j];
    for (int w = 0; w < NW; w++)
      for (int c = 0; c < NC; c++)
        for (int tj = 0; tj < 2 * NT; tj++)
          metrics[w][(size_t)(6 + 2 * NT + tj) * NC + c] += colreach[w][(size_t)c * 2 * NT + tj] / wsum[tj % 2];
  });
  for (auto& x : th) x.join();
  for (int w = 0; w < NW; w++) {
    FILE* f = fopen(wins[w].out.c_str(), "wb");
    fwrite(metrics[w].data(), sizeof(double), metrics[w].size(), f);
    fclose(f);
    if (want_matrix) {
      f = fopen((wins[w].out + ".f32").c_str(), "wb");
      fwrite(result[w].data(), sizeof(float), result[w].size(), f);
      fclose(f);
    }
    fprintf(stderr, "wrote %s (%d departures)\n", wins[w].out.c_str(), wn[w]);
  }
}
