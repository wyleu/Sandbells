/* live_list.js -- poll /events/api/since/ (DB, not the Pico) and show the
 * newest strokes first.  Vanilla JS, no libraries.  Included inline by
 * events/live_panel.html so no collectstatic is needed. */
(function () {
  "use strict";
  var box = document.getElementById("live-events");
  if (!box) return;
  var d = box.dataset;
  var cfg = {
    url: d.url, type: d.type, first: +d.first, batch: +d.batch, rows: +d.rows,
    poll: +d.poll, retryMax: +d.retryMax, failsWarn: +d.failsWarn,
    idle: +d.idle, ringGap: +d.ringGap, timeout: +d.timeout, tz: d.tz
  };
  var MS_PER_S = 1000, S_PER_MIN = 60, NEW_FLASH_MS = 2000;
  var tbody = document.getElementById("live-rows");
  var lastId = null;        // null until the first answer
  var lastAt = null;        // at_ms of the newest stroke
  var offset = 0;           // server clock - this clock (ms)
  var fails = 0, lastOk = null, delay = cfg.poll, timer = null;

  function el(id) { return document.getElementById(id); }

  function cell(tr, text, cls) {
    var td = document.createElement("td");
    if (cls) td.className = cls;
    if (text !== null) td.textContent = text;
    tr.appendChild(td);
    return td;
  }

  function seconds1(ms) { return (ms / MS_PER_S).toFixed(1) + " s"; }

  function addRow(e, flash) {
    var tr = document.createElement("tr");
    if (flash) tr.className = "new";
    cell(tr, e.at_hms_ms, e.time_ok ? "" : "dim");
    var who = cell(tr, e.bell_label || "—", "");
    var ch = document.createElement("span");
    ch.className = "ch";
    ch.textContent = "ch" + e.ch;
    who.appendChild(ch);
    cell(tr, e.interval_ms === null ? "—" : seconds1(e.interval_ms), "iv");
    var q = cell(tr, null, "");
    var m = document.createElement("span");
    m.className = e.time_ok ? "q" : "q dim";
    m.textContent = e.time_ok ? "ms" : (e.acc || "?") + "·" + (e.sync || "?");
    m.title = "acc " + e.acc + ", sync " + e.sync +
      (e.err_ms === null ? "" : ", ±" + e.err_ms.toFixed(1) + " ms");
    q.appendChild(m);
    tbody.insertBefore(tr, tbody.firstChild);
    if (flash) setTimeout(function () { tr.className = ""; }, NEW_FLASH_MS);
    while (tbody.rows.length > cfg.rows) tbody.deleteRow(tbody.rows.length - 1);
  }

  function showRing(r) {
    el("live-ring-count").textContent = r.strokes;
    var parts = [];
    r.bells.forEach(function (b) {
      var heads = Object.keys(b.per_ch).map(function (ch) {
        return "ch" + ch + " " + b.per_ch[ch];
      });
      parts.push("Bell " + b.bell + (heads.length > 1 ? ": " + heads.join(" · ") : ""));
    });
    r.channels.forEach(function (c) {
      if (c.bell === null) parts.push(c.label + ": " + c.strokes);
    });
    el("live-heads").textContent = parts.join("   ") +
      (r.start_hms ? "   (from " + r.start_hms + ")" : "");
  }

  function since(ms) {
    var s = Math.floor(ms / MS_PER_S);
    if (s < S_PER_MIN) return s + " s";
    return Math.floor(s / S_PER_MIN) + " min " + (s % S_PER_MIN) + " s";
  }

  function clockTick() {
    if (lastAt === null) return;
    var ago = Math.max(0, Date.now() + offset - lastAt);
    el("live-since").textContent = since(ago);
    el("live-ring-label").textContent = ago > cfg.ringGap ? "strokes last ring"
                                                          : "strokes this ring";
    var idle = el("live-idle");
    if (ago >= cfg.idle) {
      idle.textContent = "no strokes for " + Math.floor(ago / (S_PER_MIN * MS_PER_S)) + " min";
      idle.hidden = false;
    } else {
      idle.hidden = true;
    }
  }

  function ukTime(date) {               // pages show UK time whatever the Pi's TZ
    try { return date.toLocaleTimeString("en-GB", { timeZone: cfg.tz }); }
    catch (err) { return date.toLocaleTimeString("en-GB"); }
  }

  function warn() {
    var w = el("live-warn");
    if (fails >= cfg.failsWarn) {
      w.textContent = "Live list not updating: server not answering (" + fails +
        " tries" + (lastOk ? ", last OK " + ukTime(lastOk) : "") + ")";
      w.hidden = false;
    } else {
      w.hidden = true;
    }
  }

  function url() {
    var q = "?type=" + encodeURIComponent(cfg.type);
    if (lastId === null) return cfg.url + q + "&limit=" + cfg.first;
    return cfg.url + q + "&limit=" + cfg.batch + "&after=" + lastId;
  }

  function schedule(ms) {
    clearTimeout(timer);
    timer = setTimeout(poll, ms);
  }

  function poll() {
    if (document.visibilityState === "hidden") { timer = null; return; }
    var ctl = window.AbortController ? new AbortController() : null;
    var guard = ctl ? setTimeout(function () { ctl.abort(); }, cfg.timeout) : null;
    var sent = Date.now();
    fetch(url(), { cache: "no-store", signal: ctl ? ctl.signal : undefined })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        clearTimeout(guard);
        fails = 0; delay = cfg.poll; lastOk = new Date();
        offset = data.server_ms - Math.round((sent + Date.now()) / 2);
        var evs = data.events || [];
        var flash = lastId !== null;                        // not on first load
        evs.forEach(function (e) {
          if (e.ch === null) return;
          addRow(e, flash);
          lastAt = e.at_ms;
        });
        if (data.latest_id !== null && data.latest_id !== undefined) lastId = data.latest_id;
        else if (lastId === null) lastId = 0;
        if (data.ring) showRing(data.ring);
        warn(); clockTick();
        schedule(evs.length >= cfg.batch ? 0 : cfg.poll);   // catch up a backlog
      })
      .catch(function () {
        clearTimeout(guard);
        fails += 1;                                         // quiet: no alert
        delay = Math.min(delay * 2, cfg.retryMax);
        warn();
        schedule(delay);
      });
  }

  setInterval(clockTick, MS_PER_S);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && timer === null) poll();
  });
  poll();
})();
