// History page compare tool: draws the change map between any two years in a canvas,
// matching hist_render.py's change maps. Vanilla JS, inlined by hist_page.py.
// Data in cmp/ (hist_render.py): meta.json, cells-YEAR.u16, frame-*-big.png, water-big.png.
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var radio = $("v-custom"), selA = $("cmpA"), selB = $("cmpB"), canvas = $("cmpc");
  if (!radio || !canvas.getContext || !window.fetch) return;
  document.querySelector("label[for=v-custom]").hidden = false;

  var meta = null, metaP = null, years = {}, imgs = {}, token = 0, grid = null;

  function getMeta() {
    if (!metaP) metaP = fetch("cmp/meta.json").then(function (r) { return r.json(); }).then(function (m) {
      meta = m;
      // grid position (top row first) -> cell index, or -1
      grid = new Int32Array(m.nr * m.ncol).fill(-1);
      for (var i = 0; i < m.nc; i++) {
        var c = m.cells[i], row = Math.floor(c / m.ncol), col = c % m.ncol;
        grid[(m.nr - 1 - row) * m.ncol + col] = i;
      }
      return m;
    });
    return metaP;
  }
  function getYear(y) {
    if (!years[y]) years[y] = fetch("cmp/cells-" + y + ".u16").then(function (r) { return r.arrayBuffer(); })
      .then(function (b) { return new Uint16Array(b); });  // little-endian, like every current browser platform
    return years[y];
  }
  function getImg(src) {
    if (!imgs[src]) imgs[src] = new Promise(function (ok, fail) {
      var i = new Image(); i.onload = function () { ok(i); }; i.onerror = fail; i.src = src;
    });
    return imgs[src];
  }
  function measure() {
    var c = document.querySelector("input[name=measure]:checked");
    return c ? c.id.slice(3) : "rush";
  }
  function hexRGB(h) { return [1, 3, 5].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }

  // band index per grid position (-1 = empty), with render.py's hole filling
  function bands(m, a, b, mi) {
    var nc = m.nc, scale = m.scales[mi], isTime = mi < 2, E = m.edges;
    var band = new Int8Array(m.nr * m.ncol).fill(-1), off = mi * nc;
    for (var p = 0; p < band.length; p++) {
      var i = grid[p];
      if (i < 0) continue;
      var va = a[off + i], vb = b[off + i];
      if (isTime && va >= 1795 && vb >= 1795) continue;  // unreachable both years: leave blank
      var d = (vb - va) / scale;
      if (!isTime) d = -d;  // gains in reach land on the purple side
      var k;
      if (d > -1 && d <= 1) k = 5;
      else { k = 0; while (k < E.length && E[k] <= d) k++; }
      band[p] = k;
    }
    var NR = m.nr, NC = m.ncol;
    for (var pass = 0; pass < 2; pass++) {
      var next = band.slice(), cnt = new Int32Array(E.length + 1);
      for (var r = 0; r < NR; r++) for (var c = 0; c < NC; c++) {
        var q = r * NC + c;
        if (grid[q] >= 0 || band[q] >= 0) continue;
        cnt.fill(0); var n = 0;
        for (var rr = Math.max(r - 1, 0); rr <= Math.min(r + 1, NR - 1); rr++)
          for (var cc = Math.max(c - 1, 0); cc <= Math.min(c + 1, NC - 1); cc++) {
            var v = band[rr * NC + cc];
            if (v >= 0 && (rr !== r || cc !== c)) { cnt[v]++; n++; }
          }
        if (n >= 5) { var best = 0; for (var t = 1; t < cnt.length; t++) if (cnt[t] > cnt[best]) best = t; next[q] = best; }
      }
      band = next;
    }
    return band;
  }

  function fmtAvg(ms, va, vb) {
    var d = vb - va, s = (d >= 0 ? "+" : "−") + Math.abs(d).toFixed(1);
    if (ms === "rush" || ms === "day")
      return "The average resident's " + (ms === "rush" ? "rush-hour commute" : "trip") + " to jobs: " +
        va.toFixed(1) + " → " + vb.toFixed(1) + " minutes (" + s + ").";
    if (ms === "jobs45")
      return "Jobs the average resident can reach within 45 minutes: " + va.toFixed(1) + "% → " + vb.toFixed(1) + "% (" + s + " points).";
    return "Residents who can reach the average job within 45 minutes: " + va.toFixed(1) + "% → " + vb.toFixed(1) + "% (" + s + " points).";
  }

  function draw() {
    if (!radio.checked) return;
    var my = ++token, ya = selA.value, yb = selB.value, ms = measure();
    try { history.replaceState(null, "", "#compare-" + ya + "-" + yb); } catch (e) {}
    $("cmplin").src = "lines-" + yb + ".png";
    getMeta().then(function (m) {
      return Promise.all([m, getYear(ya), getYear(yb), getImg("cmp/frame-" + m.frame[ms] + "-big.png"), getImg("cmp/water-big.png")]);
    }).then(function (res) {
      if (my !== token) return;  // a newer choice is already on its way
      var m = res[0], mi = m.measures.indexOf(ms), band = bands(m, res[1], res[2], mi);
      var cells = document.createElement("canvas"); cells.width = m.ncol; cells.height = m.nr;
      var cx = cells.getContext("2d"), id = cx.createImageData(m.ncol, m.nr), px = id.data;
      var rgb = m.colors.map(hexRGB), al = Math.round(m.alpha * 255);
      for (var p = 0; p < band.length; p++) if (band[p] >= 0) {
        var c = rgb[band[p]]; px[4 * p] = c[0]; px[4 * p + 1] = c[1]; px[4 * p + 2] = c[2]; px[4 * p + 3] = al;
      }
      cx.putImageData(id, 0, 0);
      var g = canvas.getContext("2d");
      g.clearRect(0, 0, m.w, m.h);
      g.drawImage(res[3], 0, 0, m.w, m.h);
      g.imageSmoothingEnabled = false;
      g.drawImage(cells, 0, m.mapTop, m.w, m.mapH);
      g.imageSmoothingEnabled = true;
      g.drawImage(res[4], 0, 0, m.w, m.h);
      var T = m.title;
      g.textBaseline = "middle";
      g.fillStyle = m.ink; g.font = "bold " + T.px + "px Arial, Helvetica, sans-serif";
      g.fillText(m.titles[ms].replace("{a}", ya).replace("{b}", yb), T.x, T.y);
      g.fillStyle = m.muted; g.font = T.subPx + "px Arial, Helvetica, sans-serif";
      g.fillText(m.subs[ms].replace("{da}", m.dates[ya]).replace("{db}", m.dates[yb]), T.x, T.subY);
      $("cmpavg").textContent = fmtAvg(ms, m.avg[ms][ya], m.avg[ms][yb]);
    }).catch(function () {
      if (my === token) $("cmpavg").textContent = "Couldn't load the map data.";
    });
  }

  selA.addEventListener("change", draw);
  selB.addEventListener("change", draw);
  radio.addEventListener("change", draw);
  document.querySelectorAll("input[name=measure]").forEach(function (r) { r.addEventListener("change", draw); });
  document.querySelectorAll("input[name=view]").forEach(function (r) {
    if (r !== radio) r.addEventListener("change", function () {
      try { history.replaceState(null, "", location.pathname + location.search); } catch (e) {}
    });
  });
  var h = /^#compare-(\d{4})-(\d{4})$/.exec(location.hash);
  if (h) {
    selA.value = h[1]; selB.value = h[2];
    if (selA.value === h[1] && selB.value === h[2]) { radio.checked = true; draw(); }  // both are real years
  }
})();
