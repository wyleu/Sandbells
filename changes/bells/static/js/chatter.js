/* chatter.js -- the "Chatter test" on the sandheads page (sandswing
 * chatter.py, laser.pwm_hz).  Does a laser drive below 100 % (the laser
 * chopped by its PWM) make the comparator chatter?  Proven by counting:
 *
 *   1. the head's laser drive and the lasers' PWM speed are set (live only);
 *   2. sandtest turns its vane to just outside this head's window (a
 *      one-cycle sweep from pad_deg further out to the start: it ends at
 *      one or the other, both outside the window);
 *   3. the concentrator starts counting edges ({"chatter":"start"});
 *   4. sandtest sweeps the vane through the beam `passes` round trips
 *      (each crosses the beam twice: 4 transitions);
 *   5. the count is stopped and read back: transitions, clean (one edge),
 *      most edges in one, longest burst, spurious edges;
 *   6. one row in the results table (kept: /farm/heads/chatter-log/);
 *   7. drive and PWM speed go back to what they were.
 *
 * "Run the set" does that at each of cfg.drives_pct at today's speed, then
 * the last drive at cfg.fast_pwm_hz.  Without sandtest a single run counts
 * until Stop while the vane (or the bell) is moved by hand.
 *
 * align.js owns the connection: Chatter.attach(card, api) per head card,
 * then .refresh(state), .note(ackBody) (every ack: the PWM speed),
 * .owns(ackBody) / .ack(ackBody) and .report(body) (align_chatter).
 * The helpers on window.Chatter are plain arithmetic (tested in node).
 */
(function () {
  "use strict";

  var FULL = 65535;
  var PCT = 100;
  var KHZ = 1000;
  var RETRY_MS = 1500;            // "tower not quiet" / "too fast": ask again this often
  var QUIET_WAIT_MS = 60000;      // ... for at most this long (ring-down is 10 s after the last stroke)
  var ACK_WAIT_MS = 6000;         // no ack this long: the concentrator is not there
  var RIG_POLL_MS = 1000;         // sandtest status, as its own page polls
  var RIG_MOVE_WAIT_MS = 120000;  // the vane to its start position
  var RUN_SLACK = 1.5;            // a run may take this times its planned time ...
  var RUN_EXTRA_MS = 20000;       // ... plus this, before it is given up
  var MS_PER_S = 1000;
  var SETTLE_MS = 500;            // vane stopped -> stop the count (well over chatter_gap_ms)
  var RIG_START_MS = 3000;        // "idle" this soon after a command, never seen moving: not started yet
  // sandtest status sweep.mode while the vane moves (sandtest.js SPECS)
  var RIG_MOVING = ["sweep", "scan", "visit", "menace", "profile"];
  var DRIVES = [100, 75, 52, 25, 10];                 // the drive choices, %
  var SPEEDS = [1000, 5000, 20000, 50000, 100000];    // the PWM speed choices, Hz
  var RETRY_WHY = ["tower not quiet", "too fast"];
  var CHATTER_WHAT = ["use", "pwm", "chatter"];
  var BY_HAND = "0";

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  /* ---- plain helpers (node tests) ------------------------------------------ */

  function dutyOf(pct) { return Math.round(pct * FULL / PCT); }
  function pctOf(duty) { return duty === null || duty === undefined ? null : Math.round(duty * PCT * 10 / FULL) / 10; }
  function hzText(hz) {
    if (hz === null || hz === undefined) return "—";
    return hz >= KHZ ? (Math.round(hz / 100) / 10) + " kHz" : hz + " Hz";
  }
  function cleanPct(trans, clean) {
    if (!trans) return null;
    return Math.round((clean || 0) * PCT * 10 / trans) / 10;
  }

  /* "Run the set": every drive at today's speed, then the last one fast */
  function plan(opt) {
    var d = opt.drives_pct || [100, 52, 25];
    var now = opt.pwmNow || 1000;
    var runs = [];
    for (var i = 0; i < d.length; i++) runs.push({ pct: d[i], hz: now });
    runs.push({ pct: d[d.length - 1], hz: opt.fast_pwm_hz || now });
    return runs;
  }

  /* sandtest's status (rig) -> the vane's start / end angles for one rig head,
     or {error}.  Shaft angle = the head's angle + the face's offset; the
     sweep runs pad_deg past the head's window each side. */
  function rigSpan(rig, head, face, opt) {
    var sw = (rig || {}).sweep || {};
    var h = (sw.heads || {})[String(head)];
    if (!h) return { error: "sandtest has no position " + head };
    var faces = sw.faces || {};
    if (!(face in faces)) return { error: "sandtest has no face “" + face + "”" };
    var c = h.angle_deg + faces[face];
    var half = (h.width_deg || 0) / 2 + (opt.pad_deg || 0);
    return { from: Math.round((c - half) * 100) / 100, to: Math.round((c + half) * 100) / 100 };
  }

  /* to the start: sandtest has no "go to" (sandtest.js SPECS), so one
     cycle between pad_deg further out and the start; shaft angles, so the
     face is already in them (rigSpan) */
  function rigPrep(span, opt) {
    return { cmd: "sweep", mode: "sweep", from_deg: Math.round((span.from - opt.pad_deg) * 100) / 100,
             to_deg: span.from, speed_dps: opt.speed_dps, cycles: 1 };
  }

  function rigSweep(span, opt, passes) {
    return { cmd: "sweep", mode: "sweep", from_deg: span.from, to_deg: span.to,
             speed_dps: opt.speed_dps, cycles: passes };
  }

  /* the planned time of the passes, ms */
  function runMs(span, opt, passes) {
    return Math.round(passes * 2 * Math.abs(span.to - span.from) / opt.speed_dps * MS_PER_S);
  }

  /* the longest a run may take before it is given up, ms */
  function runLimitMs(span, opt, passes) {
    return Math.round(runMs(span, opt, passes) * RUN_SLACK + RUN_EXTRA_MS);
  }

  function rigMoving(rig) {
    var sw = (rig || {}).sweep || {};
    return RIG_MOVING.indexOf(sw.mode) >= 0;
  }

  function retryable(why) {
    for (var i = 0; i < RETRY_WHY.length; i++) if (String(why || "").indexOf(RETRY_WHY[i]) === 0) return true;
    return false;
  }

  /* one logged run: the page's POST to chatterLogUrl */
  function rowFrom(b, run) {
    return { ch: run.ch, label: run.label || "", drv: run.drv, pwm_hz: run.pwmHz === undefined ? null : run.pwmHz,
             passes: run.passes || null, trans: b.trans, clean: b.clean, max_edges: b.max_edges,
             mean_x10: b.mean_x10, max_burst_ms: b.max_burst_ms, spurious: b.spurious,
             end: run.end || "" };
  }

  /* ---- the panel ------------------------------------------------------------ */

  function select(cls, items, value) {
    var s = el("select", cls);
    for (var i = 0; i < items.length; i++) {
      var o = el("option", "", items[i][1]);
      o.value = String(items[i][0]);
      s.appendChild(o);
    }
    s.value = String(value);
    return s;
  }

  function attach(card, api) {
    var opt = api.cfg || {};
    var urls = api.urls || {};
    var v = { card: card, api: api, opt: opt, urls: urls, st: {}, busy: false, tok: 0, wait: null,
              waitReport: null, pwmHz: null, rig: null, rows: [], runs: [], stopping: false };
    var box = el("div", "chatter");
    box.appendChild(el("h3", "", "Chatter test: one clean edge each time?"));
    box.appendChild(el("p", "lnote",
      "Keep the tower quiet.  Sandtest turns its vane through this head's beam and the concentrator " +
      "counts every edge.  The drive and PWM speed go back as they were at the end."));
    var row1 = el("div", "lacts");
    var drives = [];
    for (var i = 0; i < DRIVES.length; i++) drives.push([DRIVES[i], "Drive " + DRIVES[i] + " %"]);
    v.drive = select("lslot", drives, DRIVES[0]);
    var speeds = [];
    var lo = opt.pwmMin || 200, hi = opt.pwmMax || 150000;
    var all = SPEEDS.slice();
    if (opt.fast_pwm_hz && all.indexOf(opt.fast_pwm_hz) < 0) all.push(opt.fast_pwm_hz);
    all.sort(function (a, b) { return a - b; });
    for (var j = 0; j < all.length; j++) {
      if (all[j] < lo || all[j] > hi) continue;
      speeds.push([all[j], "PWM " + hzText(all[j]) + (all[j] === (opt.pwmNow || 1000) ? " (as now)" : "")]);
    }
    v.speed = select("lslot", speeds, opt.pwmNow || 1000);
    v.pos = select("lslot", [[BY_HAND, "Vane by hand"]], BY_HAND);
    v.pos.addEventListener("change", function () { refresh(v); });
    v.pos.title = "Which sandtest position faces this head";
    row1.appendChild(v.drive);
    row1.appendChild(v.speed);
    row1.appendChild(v.pos);
    box.appendChild(row1);
    var row2 = el("div", "lacts");
    v.start = el("button", "big", "Start");
    v.start.type = "button";
    v.start.addEventListener("click", function () { begin(v, false); });
    v.set = el("button", "big", "Run the set");
    v.set.type = "button";
    v.set.title = "Drive " + (opt.drives_pct || []).join(" %, ") + " % at " + hzText(opt.pwmNow || 1000) +
      ", then " + ((opt.drives_pct || []).slice(-1)[0]) + " % at " + hzText(opt.fast_pwm_hz);
    v.set.addEventListener("click", function () { begin(v, true); });
    v.stop = el("button", "big stop", "Stop");
    v.stop.type = "button";
    v.stop.addEventListener("click", function () { stop(v, "stopped"); });
    row2.appendChild(v.start);
    row2.appendChild(v.set);
    row2.appendChild(v.stop);
    box.appendChild(row2);
    v.status = el("div", "lstatus", "");
    box.appendChild(v.status);
    v.msg = el("div", "msg", "");
    box.appendChild(v.msg);
    v.table = el("table", "ctable");
    box.appendChild(v.table);
    if (urls.chatterCsvUrl) {
      var a = el("a", "", "Download the results (CSV, last 30 days)");
      a.setAttribute("href", urls.chatterCsvUrl + "?days=30");
      box.appendChild(a);
    }
    v.box = box;
    render(v);
    refresh(v);
    loadRows(v);
    rigStatus(v, function () {});
    return {
      box: box, v: v,
      refresh: function (st) { v.st = st || {}; refresh(v); },
      note: function (b) { note(v, b); },
      owns: function (b) { return v.busy && CHATTER_WHAT.indexOf(b.what) >= 0; },
      ack: function (b) { ack(v, b); },
      report: function (b) { report(v, b); }
    };
  }

  function setMsg(v, text, bad) {
    v.msg.textContent = text;
    v.msg.className = "msg" + (bad ? " refused" : "");
  }

  function say(v, text) { v.status.textContent = text; }

  function refresh(v) {
    var st = v.st;
    v.box.className = "chatter" + (st.active ? "" : " hidden");
    var idle = !v.busy;
    v.start.disabled = !idle || !st.active;
    v.set.disabled = !idle || !st.active || v.pos.value === BY_HAND;
    v.stop.disabled = idle || v.stopping;
    v.drive.disabled = v.speed.disabled = v.pos.disabled = !idle;
  }

  /* every ack carries the lasers' PWM speed (firmware with laser.pwm_hz) */
  function note(v, b) {
    if (typeof b.pwm_hz === "number") v.pwmHz = b.pwm_hz;
  }

  /* ---- talking to the rig and to Django --------------------------------------- */

  function http(v, method, url, body, cb) {
    try {
      var x = new window.XMLHttpRequest();
      x.open(method, url, true);
      if (body !== null) {
        x.setRequestHeader("Content-Type", "application/json");
        if (v.api.csrf) x.setRequestHeader("X-CSRFToken", v.api.csrf());
      }
      x.onload = function () {
        var o = null;
        try { o = JSON.parse(x.responseText); } catch (e) { o = null; }
        cb(x.status, o);
      };
      x.onerror = function () { cb(0, null); };
      x.send(body === null ? null : JSON.stringify(body));
    } catch (e) { cb(0, null); }
  }

  function rigStatus(v, cb) {
    if (!v.urls.sandtestStatusUrl) { v.rig = null; cb(null); return; }
    http(v, "GET", v.urls.sandtestStatusUrl, null, function (status, o) {
      v.rig = status === 200 && o && o.ok ? o.rig : null;
      fillPositions(v);
      cb(v.rig);
    });
  }

  function fillPositions(v) {
    var heads = ((v.rig || {}).sweep || {}).heads || {};
    var keep = v.pos.value;
    v.pos.innerHTML = "";
    var o = el("option", "", v.rig ? "Vane by hand" : "Vane by hand (sandtest not connected)");
    o.value = BY_HAND;
    v.pos.appendChild(o);
    var any = false;
    for (var k in heads) {
      if (!heads.hasOwnProperty(k)) continue;
      var p = el("option", "", "Sandtest position " + k);
      p.value = String(k);
      v.pos.appendChild(p);
      any = true;
    }
    var stored = null;
    try { stored = window.localStorage ? window.localStorage.getItem("chatterPos" + v.card.ch) : null; } catch (e) { stored = null; }
    var first = null;
    for (var f in heads) if (heads.hasOwnProperty(f) && first === null) first = String(f);
    v.pos.value = heads[keep] ? keep : (stored && heads[stored] ? stored : (any ? first : BY_HAND));
    refresh(v);
  }

  function rigCmd(v, cmd, then) {
    http(v, "POST", v.urls.sandtestCmdUrl, cmd, function (status, o) {
      if (status === 200 && o && o.ok) then();
      else fail(v, "Sandtest said no: " + ((o && o.error) || ("HTTP " + status)));
    });
  }

  function loadRows(v) {
    if (!v.urls.chatterLogUrl) return;
    http(v, "GET", v.urls.chatterLogUrl, null, function (status, o) {
      if (status === 200 && o && o.rows) { v.rows = o.rows; render(v); }
    });
  }

  function pctText(p) { return p === null || p === undefined ? "—" : p + " %"; }

  function render(v) {
    var t = v.table;
    t.innerHTML = "";
    var head = el("tr", "");
    var cols = ["When", "Head", "Drive", "PWM", "Transitions (expected)", "Clean", "Most edges",
                "Longest burst", "Spurious"];
    for (var i = 0; i < cols.length; i++) head.appendChild(el("th", "", cols[i]));
    t.appendChild(head);
    if (!v.rows.length) {
      var e = el("tr", "");
      e.appendChild(el("td", "", "No runs yet."));
      t.appendChild(e);
      return;
    }
    for (var j = 0; j < v.rows.length; j++) {
      var r = v.rows[j];
      var tr = el("tr", r.trans && r.clean === r.trans && !r.spurious ? "good" : "bad");
      var when = String(r.at || "").replace("T", " ").slice(0, 16);
      var cells = [when, "ch " + r.ch + (r.label ? " (" + r.label + ")" : ""),
                   (r.drive_pct === null || r.drive_pct === undefined ? pctOf(r.drv) : r.drive_pct) + " %",
                   hzText(r.pwm_hz),
                   (r.trans === null ? "—" : r.trans) + (r.expected ? " (" + r.expected + ")" : ""),
                   pctText(r.clean_pct === null || r.clean_pct === undefined ? cleanPct(r.trans, r.clean) : r.clean_pct),
                   r.max_edges === null ? "—" : String(r.max_edges),
                   r.max_burst_ms === null ? "—" : r.max_burst_ms + " ms",
                   (r.spurious === null ? "—" : String(r.spurious)) + (r.end ? " — " + r.end : "")];
      for (var k = 0; k < cells.length; k++) tr.appendChild(el("td", "", cells[k]));
      t.appendChild(tr);
    }
  }

  /* ---- one step at a time ---------------------------------------------------- */

  function later(v, ms, fn) {
    var tok = ++v.tok;
    setTimeout(function () { if (tok === v.tok) fn(); }, ms);
  }

  /* one align command, its ack awaited; "tower not quiet" / "too fast" are
     asked again every RETRY_MS for up to QUIET_WAIT_MS */
  function command(v, obj, what, next) {
    var t0 = Date.now();
    function go() {
      v.wait = { what: what, done: function (b) {
        v.wait = null;
        v.tok++;
        if (b.ok) { next(b); return; }
        if (retryable(b.why) && Date.now() - t0 < QUIET_WAIT_MS) {
          say(v, "Waiting for the tower to be quiet…");
          later(v, RETRY_MS, go);
          return;
        }
        fail(v, "Not changed: " + b.why);
      } };
      if (!v.api.send(obj)) { v.wait = null; fail(v, "Not connected to the concentrator."); return; }
      later(v, ACK_WAIT_MS, function () { v.wait = null; fail(v, "No answer from the concentrator."); });
    }
    go();
  }

  function begin(v, whole) {
    if (v.busy) return;
    if (v.card.drv === null || v.card.drv === undefined) {
      setMsg(v, "Waiting for this head's readings; try again in a moment.", true);
      return;
    }
    var runs;
    if (whole) {
      if (v.pos.value === BY_HAND) { setMsg(v, "“Run the set” needs sandtest connected and its position picked.", true); return; }
      runs = plan(v.opt);
    } else {
      runs = [{ pct: parseInt(v.drive.value, 10), hz: parseInt(v.speed.value, 10) }];
    }
    try { if (window.localStorage) window.localStorage.setItem("chatterPos" + v.card.ch, v.pos.value); } catch (e) { /* private mode */ }
    v.busy = true;
    v.stopping = false;
    v.counting = false;
    v.rigMoving = false;
    v.runs = runs;
    v.drv0 = v.card.drv;
    v.pwm0 = v.pwmHz === null ? (v.opt.pwmNow || 1000) : v.pwmHz;
    setMsg(v, "", false);
    refresh(v);
    if (v.pos.value === BY_HAND) { nextRun(v); return; }
    say(v, "Asking sandtest where the heads are…");
    rigStatus(v, function (rig) {
      if (!rig) { fail(v, "Sandtest is not answering; pick “Vane by hand” or check it."); return; }
      nextRun(v);
    });
  }

  function nextRun(v) {
    if (!v.runs.length) { restore(v, "Done."); return; }
    var r = v.runs.shift();
    var face = v.opt.face || "reflector";
    var run = { ch: v.card.ch, pct: r.pct, drv: dutyOf(r.pct), hz: r.hz, end: "",
                label: v.api.label ? v.api.label() : "" };
    if (v.pos.value !== BY_HAND) {
      var span = rigSpan(v.rig, v.pos.value, face, v.opt);
      if (span.error) { fail(v, span.error); return; }
      run.span = span;
      run.passes = v.opt.passes;
      run.face = face;
    }
    v.run = run;
    say(v, "Setting drive " + r.pct + " % and PWM " + hzText(r.hz) + "…");
    command(v, { cmd: "align", ch: run.ch, use: [run.drv, null] }, "use", function () {
      var then = function () { rigToStart(v); };
      if (v.pwmHz === r.hz) { then(); return; }
      command(v, { cmd: "align", ch: run.ch, pwm_hz: r.hz }, "pwm", then);
    });
  }

  function rigToStart(v) {
    var run = v.run;
    if (!run.span) { countStart(v); return; }
    say(v, "Sandtest: vane to its start position…");
    v.rigMoving = true;
    rigCmd(v, rigPrep(run.span, v.opt), function () {
      waitRig(v, RIG_START_MS, RIG_MOVE_WAIT_MS, function () { countStart(v); });
    });
  }

  /* done when sandtest is seen moving and then not, or not moving after
     minMs (it may have finished between two polls) */
  function waitRig(v, minMs, limit, then) {
    var t0 = Date.now();
    var seen = false;
    function poll() {
      later(v, RIG_POLL_MS, function () {
        rigStatus(v, function (rig) {
          if (!v.busy) return;
          if (rig && rigMoving(rig)) seen = true;
          else if (rig && (seen || Date.now() - t0 >= minMs)) { v.rigMoving = false; then(); return; }
          if (Date.now() - t0 > limit) { fail(v, "Sandtest did not finish in time."); return; }
          if (rig && v.counting) {
            var done = ((rig.sweep || {}).cycles_done) || 0;
            say(v, "Counting: pass " + Math.min(done + 1, v.run.passes) + " of " + v.run.passes + "…");
          }
          poll();
        });
      });
    }
    poll();
  }

  function countStart(v) {
    var run = v.run;
    command(v, { cmd: "align", ch: run.ch, chatter: "start" }, "chatter", function (b) {
      v.counting = true;
      run.pwmHz = typeof b.pwm_hz === "number" ? b.pwm_hz : v.pwmHz;
      if (!run.span) {
        say(v, "Counting.  Move the vane (or the bell) through the beam, then press Stop.");
        refresh(v);
        return;
      }
      say(v, "Counting: sandtest sweeping " + run.passes + " passes…");
      v.rigMoving = true;
      rigCmd(v, rigSweep(run.span, v.opt, run.passes), function () {
        waitRig(v, runMs(run.span, v.opt, run.passes), runLimitMs(run.span, v.opt, run.passes), function () {
          later(v, SETTLE_MS, function () { countStop(v, nextRun); });
        });
      });
    });
  }

  function countStop(v, then) {
    var run = v.run;
    v.waitReport = function (b) {
      v.waitReport = null;
      v.counting = false;
      v.tok++;
      logRun(v, rowFrom(b, run));
      then(v);
    };
    command(v, { cmd: "align", ch: run.ch, chatter: "stop" }, "chatter", function () {
      if (v.waitReport) later(v, ACK_WAIT_MS, function () { v.waitReport = null; v.counting = false; fail(v, "No count came back."); });
    });
  }

  function logRun(v, row) {
    var shown = { at: new Date().toISOString(), ch: row.ch, label: row.label, drv: row.drv,
                  drive_pct: pctOf(row.drv), pwm_hz: row.pwm_hz, passes: row.passes,
                  expected: row.passes ? row.passes * (v.opt.transPerPass || 4) : null,
                  trans: row.trans, clean: row.clean, clean_pct: cleanPct(row.trans, row.clean),
                  max_edges: row.max_edges, mean_x10: row.mean_x10, max_burst_ms: row.max_burst_ms,
                  spurious: row.spurious, end: row.end };
    v.rows.unshift(shown);
    render(v);
    if (v.urls.chatterLogUrl) {
      http(v, "POST", v.urls.chatterLogUrl, row, function (status, o) {
        if (status === 200 && o && o.row) { v.rows[v.rows.indexOf(shown)] = o.row; render(v); }
        else setMsg(v, "The result is on screen but was not kept (" + status + ").", true);
      });
    }
  }

  /* drive and PWM speed back as they were, then idle */
  function restore(v, text) {
    v.restoring = true;
    say(v, "Putting the drive and PWM speed back…");
    var fin = function () { v.restoring = false; v.busy = false; v.wait = null; say(v, text); refresh(v); };
    var drv = function () {
      if (v.drv0 === null || v.drv0 === undefined) { fin(); return; }
      command(v, { cmd: "align", ch: v.card.ch, use: [v.drv0, null] }, "use", fin);
    };
    if (v.pwmHz === v.pwm0) { drv(); return; }
    command(v, { cmd: "align", ch: v.card.ch, pwm_hz: v.pwm0 }, "pwm", drv);
  }

  function fail(v, why) {
    if (v.stopping) {                                 // the stop itself went wrong: still restore
      v.stopping = false;
      v.counting = false;
      setMsg(v, why, true);
      restore(v, "Stopped: " + why);
      return;
    }
    if (v.restoring) {
      v.restoring = false;
      v.busy = false;
      setMsg(v, why + "  The drive or PWM speed may not be back: check the readouts.", true);
      say(v, "");
      refresh(v);
      return;
    }
    setMsg(v, why, true);
    stop(v, why);
  }

  /* Stop (button or a failure): the vane, the count (a stopped run is still
     recorded), then the restore */
  function stop(v, why) {
    if (!v.busy || v.stopping) return;
    v.stopping = true;
    v.runs = [];
    v.wait = null;
    v.tok++;
    refresh(v);
    if (v.rigMoving && v.urls.sandtestCmdUrl) {
      http(v, "POST", v.urls.sandtestCmdUrl, { cmd: "stop" }, function () {});
      v.rigMoving = false;
    }
    var after = function () { v.stopping = false; restore(v, why === "stopped" ? "Stopped." : "Stopped: " + why); };
    if (v.counting) {
      v.run.end = v.run.span ? why : "";              // by hand: Stop is the end of the run
      countStop(v, after);
    } else {
      after();
    }
  }

  function ack(v, b) {
    note(v, b);
    if (v.wait && v.wait.what === b.what) v.wait.done(b);
  }

  function report(v, b) {
    if (v.waitReport && v.run && b.ch === v.run.ch) v.waitReport(b);
  }

  window.Chatter = { attach: attach, plan: plan, rigSpan: rigSpan, rigPrep: rigPrep, rigSweep: rigSweep, runMs: runMs,
                     runLimitMs: runLimitMs, dutyOf: dutyOf, cleanPct: cleanPct, rowFrom: rowFrom,
                     retryable: retryable, hzText: hzText };
})();
