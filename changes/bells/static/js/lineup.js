/* lineup.js -- "Find best brightness" on the sandheads page: the line-up of a
 * head in the channel with the PT wire (sandswing sweep.py / head_store.py).
 *
 * One big button sweeps the laser drive from full down to the floor; the
 * curve (drive % across, PT level up) fills in as the points arrive, with the
 * laser current written by the full-drive and suggested points.  At the end
 * it suggests the lowest drive whose PT level is within plateau_frac of the
 * full-drive level, plus margin_frac, and the threshold kept in the same
 * proportion to the PT level as now.  Nothing changes until "Use this" (live
 * only) or "Save for channel N" (kept on the concentrator, used at every
 * start).  Errors stay on screen until the next press.
 *
 * align.js owns the connection: it calls Lineup.attach(card, api) for each
 * head's card, then .refresh(state), .point(body), .ack(body) and
 * Lineup.slot(body).  Lineup.suggest is plain arithmetic (tested in node).
 */
(function () {
  "use strict";

  var FULL = 65535;
  var PCT = 100;
  var MIN_POINTS = 3;             // fewer: nothing to judge a curve by
  var LOCK_MS = 400;              // one press, one command
  var PAD = 8;                    // canvas padding, px
  var DOT = 4;                    // a point's square, px
  var DONE = [null, "near threshold"];   // sweep_end reasons that are a finish

  var slots = {};                 // ch -> {saved, drv, thr, label}: the concentrator's saved values
  var views = [];                 // every attached card's line-up view

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function pct(d) { return d === null || d === undefined ? "—" : (d * PCT / FULL).toFixed(1) + " %"; }
  function mA(v) { return v === null || v === undefined ? "—" : v.toFixed(1) + " mA"; }
  function V(v) { return v === null || v === undefined ? "—" : v.toFixed(2) + " V"; }

  function sorted(points) {
    var p = [];
    for (var i = 0; i < points.length; i++) {
      if (points[i] && typeof points[i].pt === "number" && typeof points[i].drv === "number") p.push(points[i]);
    }
    p.sort(function (a, b) { return b.drv - a.drv; });
    return p;
  }

  /* linear in drive between the two points either side (p: full drive first) */
  function interp(p, drv, key) {
    for (var k = 0; k + 1 < p.length; k++) {
      var a = p[k], b = p[k + 1];
      if (drv <= a.drv && drv >= b.drv) {
        if (a[key] === null || b[key] === null || a[key] === undefined || b[key] === undefined) return null;
        if (a.drv === b.drv) return a[key];
        return b[key] + (a[key] - b[key]) * (drv - b.drv) / (a.drv - b.drv);
      }
    }
    return p.length ? p[0][key] : null;
  }

  /* -> {drv, thr, ma, pt, top, topMa, good} or {drv: null, why} */
  function suggest(points, opt, thrNow) {
    var p = sorted(points);
    if (p.length < MIN_POINTS) return { drv: null, why: "Too few readings to judge (" + p.length + ")." };
    var lo = p[0].pt, hi = p[0].pt;
    for (var i = 1; i < p.length; i++) { lo = Math.min(lo, p[i].pt); hi = Math.max(hi, p[i].pt); }
    if (hi - lo < opt.min_range_v) {
      return { drv: null, why: "The PT level hardly changed (" + (hi - lo).toFixed(2) +
               " V over the whole sweep), so the PT may not be seeing this laser. Nothing suggested." };
    }
    var top = p[0].pt;
    var band = Math.abs(top) * opt.plateau_frac;
    var good = p[0];
    for (var k = 1; k < p.length; k++) {
      if (Math.abs(p[k].pt - top) <= band) good = p[k];
      else break;
    }
    var drv = Math.min(FULL, Math.max(good.drv, Math.round(good.drv * (1 + opt.margin_frac))));
    var pt = interp(p, drv, "pt");
    var thr = null;
    if (typeof thrNow === "number" && top && pt !== null) {
      thr = Math.max(0, Math.min(FULL, Math.round(thrNow * pt / top)));
    }
    return { drv: drv, thr: thr, ma: interp(p, drv, "ma"), pt: pt, top: top, topMa: p[0].ma,
             good: good.drv };
  }

  function draw(v) {
    var c = v.canvas;
    var W = c.clientWidth || 300, H = c.clientHeight || 140;
    if (c.width !== W) c.width = W;
    if (c.height !== H) c.height = H;
    var g = c.getContext && c.getContext("2d");
    if (!g) return;
    g.fillStyle = "#17140f";
    g.fillRect(0, 0, W, H);
    var p = sorted(v.points);
    g.fillStyle = "#b9a97f";
    g.fillText("drive % →", W - 70, H - 2);
    g.fillText("PT level", 2, 10);
    if (!p.length) return;
    var lo = p[0].pt, hi = p[0].pt;
    for (var i = 1; i < p.length; i++) { lo = Math.min(lo, p[i].pt); hi = Math.max(hi, p[i].pt); }
    if (hi - lo < 0.01) { lo -= 0.05; hi += 0.05; }
    function x(d) { return PAD + d / FULL * (W - 2 * PAD); }
    function y(pt) { return H - PAD - (pt - lo) / (hi - lo) * (H - 2 * PAD); }
    g.strokeStyle = "#6fdc7f";
    g.beginPath();
    for (var j = 0; j < p.length; j++) {
      if (j) g.lineTo(x(p[j].drv), y(p[j].pt));
      else g.moveTo(x(p[j].drv), y(p[j].pt));
    }
    g.stroke();
    g.fillStyle = "#f1e3c2";
    for (var k = 0; k < p.length; k++) g.fillRect(x(p[k].drv) - DOT / 2, y(p[k].pt) - DOT / 2, DOT, DOT);
    g.fillText(V(hi), 2, PAD + 10);
    g.fillText(V(lo), 2, H - PAD);
    if (v.sug && v.sug.drv !== null) {
      g.strokeStyle = "#fc3";
      g.beginPath();
      g.moveTo(x(v.sug.drv), 0);
      g.lineTo(x(v.sug.drv), H);
      g.stroke();
    }
  }

  function attach(card, api) {
    var opt = api.cfg || {};
    var nSlots = opt.slots || 8;
    var v = { card: card, api: api, points: [], state: "idle", sug: null, thr0: null, drv0: null,
              locked: false, forgetArm: 0, end: null };
    var box = el("div", "lineup");
    box.appendChild(el("h3", "", "Line up this head"));
    box.appendChild(el("p", "lnote",
      "Keep the tower quiet: nobody ringing while this runs (about 10 seconds). " +
      "Nothing is changed until you press “Use this” or “Save”."));
    var lab = el("label", "llabel", "Number written on the head ");
    v.label = el("input", "ltext");
    v.label.type = "text";
    v.label.value = "";
    v.label.setAttribute("maxlength", String(opt.labelMax || 8));
    v.label.setAttribute("size", String(opt.labelMax || 8));
    lab.appendChild(v.label);
    box.appendChild(lab);
    v.go = el("button", "big", "Find best brightness");
    v.go.type = "button";
    v.go.addEventListener("click", function () { press(v); });
    box.appendChild(v.go);
    v.canvas = el("canvas", "curve");
    v.canvas.setAttribute("aria-label", "PT level against laser drive");
    box.appendChild(v.canvas);
    v.status = el("div", "lstatus", "");
    box.appendChild(v.status);
    v.msg = el("div", "msg", "");
    box.appendChild(v.msg);
    var act = el("div", "lacts");
    v.use = el("button", "big", "Use this");
    v.use.type = "button";
    v.use.addEventListener("click", function () { use(v); });
    act.appendChild(v.use);
    v.slotSel = el("select", "lslot");
    for (var s = 1; s <= nSlots; s++) {
      var o = el("option", "", "channel " + s);
      o.value = String(s);
      v.slotSel.appendChild(o);
    }
    v.slotSel.value = "1";
    v.slotSel.addEventListener("change", function () { refresh(v); });
    v.save = el("button", "big", "Save for channel 1");
    v.save.type = "button";
    v.save.addEventListener("click", function () { save(v); });
    act.appendChild(v.save);
    act.appendChild(v.slotSel);
    box.appendChild(act);
    box.appendChild(el("p", "lnote", "“Save” keeps the drive and threshold this head is using now, " +
      "for the channel you pick, with its number."));
    box.appendChild(el("h3", "", "Saved on the concentrator (used at every start)"));
    v.table = el("div", "lsaved");
    box.appendChild(v.table);
    v.box = box;
    v.st = {};
    views.push(v);
    var view = {
      box: box,
      refresh: function (st) { v.st = st || {}; refresh(v); },
      point: function (b) { point(v, b); },
      ack: function (b) { ack(v, b); },
      suggestion: function () { return v.sug; },
      v: v
    };
    renderSlots(v);
    refresh(v);
    return view;
  }

  function setMsg(v, text, bad) {
    v.msg.textContent = text;
    v.msg.className = "msg" + (bad ? " refused" : "");
  }

  function lock(v) {
    v.locked = true;
    refresh(v);
    setTimeout(function () { v.locked = false; refresh(v); }, LOCK_MS);
  }

  function slotN(v) { return parseInt(v.slotSel.value, 10) || 1; }

  function refresh(v) {
    var st = v.st;
    var show = !!st.active && st.ptCh === v.card.ch;
    v.box.className = "lineup" + (show ? "" : " hidden");
    var running = v.state === "running" || v.state === "starting";
    var quiet = !!st.quiet;
    v.go.textContent = running ? "Stop" : "Find best brightness";
    v.go.className = "big" + (running ? " stop" : "");
    v.go.disabled = v.locked || (!running && !quiet);
    v.use.disabled = v.locked || running || !quiet || !v.sug || v.sug.drv === null;
    v.save.disabled = v.locked || running || !quiet;
    v.save.textContent = "Save for channel " + slotN(v);
    if (!quiet && !running && show) {
      v.waiting = true;
      v.status.textContent = "Waiting for the tower to be quiet…";
    } else if (v.waiting) {
      v.waiting = false;
      v.status.textContent = v.result || "";
    }
    draw(v);
  }

  function press(v) {
    var running = v.state === "running" || v.state === "starting";
    var ch = v.card.ch;
    if (running) {
      if (!v.api.send({ cmd: "align", ch: ch, sweep: false })) setMsg(v, "Not connected to the concentrator.", true);
      lock(v);
      return;
    }
    if (!v.api.send({ cmd: "align", ch: ch, sweep: true })) {
      setMsg(v, "Not connected to the concentrator.", true);
      return;
    }
    v.points = [];
    v.sug = null;
    v.end = null;
    v.thr0 = v.card.thr;
    v.drv0 = v.card.drv;
    v.state = "starting";
    v.result = "";
    v.status.textContent = "Starting…";
    setMsg(v, "", false);
    lock(v);
  }

  function point(v, b) {
    if (v.state !== "running" && v.state !== "starting") return;
    v.state = "running";
    v.points.push({ i: b.i, drv: b.drv, ma: b.ma, pt: b.pt, span: b.pt_span });
    v.status.textContent = "Drive " + pct(b.drv) + ": PT " + V(b.pt) + ", " + mA(b.ma) +
      "  (" + v.points.length + " readings)";
    refresh(v);
  }

  function finish(v, why) {
    v.state = "idle";
    v.end = why;
    var done = DONE.indexOf(why) >= 0;
    if (done) {
      var noThr = !!v.st.noThr;
      v.sug = suggest(v.points, v.api.cfg || {}, noThr ? null : v.thr0);
      if (v.sug.drv === null) {
        v.status.textContent = v.result = v.sug.why;
      } else {
        var p = sorted(v.points);
        v.status.textContent = v.result = "Full drive: PT " + V(v.sug.top) + " at " + mA(v.sug.topMa) +
          ".  Suggested: drive " + pct(v.sug.drv) + " (PT about " + V(v.sug.pt) + ", about " +
          mA(v.sug.ma) + ")" + (v.sug.thr === null ? "" : ", threshold " + pct(v.sug.thr)) +
          ".  " + p.length + " readings.";
      }
      setMsg(v, why ? "Finished early: the beam came close to the threshold, so it stopped there." : "", false);
    } else {
      v.sug = null;
      v.status.textContent = v.result = "";
      setMsg(v, "The sweep stopped: " + why + ".  The laser drive is back as it was.", why !== "stopped");
    }
    if (v.points.length && v.api.log) {
      var sug = v.sug || {};
      v.api.log({ ch: v.card.ch, label: v.label.value || "", end: why,
                  points: sorted(v.points).map(function (q) { return [q.drv, q.ma, q.pt, q.span]; }),
                  drv_before: v.drv0, thr_before: v.thr0,
                  suggested_drv: sug.drv === undefined ? null : sug.drv,
                  suggested_thr: sug.thr === undefined ? null : sug.thr });
    }
    refresh(v);
  }

  function use(v) {
    if (!v.sug || v.sug.drv === null) return;
    if (!v.api.send({ cmd: "align", ch: v.card.ch, use: [v.sug.drv, v.sug.thr] })) {
      setMsg(v, "Not connected to the concentrator.", true);
      return;
    }
    lock(v);
  }

  function save(v) {
    var n = slotN(v);
    var cmd = { cmd: "align", ch: v.card.ch, save: n, label: (v.label.value || "").trim() };
    if (!v.api.send(cmd)) {
      setMsg(v, "Not connected to the concentrator.", true);
      return;
    }
    lock(v);
  }

  function forget(v, n) {
    if (v.forgetArm !== n) {          // two presses: a slip does not lose a line-up
      v.forgetArm = n;
      renderSlots(v);
      return;
    }
    v.forgetArm = 0;
    if (!v.api.send({ cmd: "align", forget: n })) setMsg(v, "Not connected to the concentrator.", true);
    renderSlots(v);
  }

  function ack(v, b) {
    var w = b.what;
    if (w === "sweep") {
      if (b.ok) {
        if (v.state === "starting") { v.state = "running"; v.status.textContent = "Measuring…"; }
      } else {
        v.state = "idle";
        setMsg(v, "Could not start: " + b.why, true);
      }
    } else if (w === "sweep_end") {
      if (v.state === "running" || v.state === "starting") finish(v, b.why === undefined ? null : b.why);
    } else if (w === "use") {
      if (b.ok) setMsg(v, "Now using drive " + pct(b.drv) + (b.thr === null || b.thr === undefined ? "" :
        ", threshold " + pct(b.thr)) + " (live: lost at the next start unless saved).", false);
      else setMsg(v, "Not changed: " + b.why, true);
    } else if (w === "save") {
      if (b.ok) setMsg(v, "Saved for channel " + slotN(v) + ".", false);
      else setMsg(v, "Not saved: " + b.why, true);
    } else if (w === "forget") {
      if (!b.ok) setMsg(v, "Not forgotten: " + b.why, true);
    } else if (w === "bad") {
      // refused before it was understood (a bad label; older firmware without a sweep)
      if (v.state === "starting") {
        v.state = "idle";
        setMsg(v, "Could not start: " + b.why + ".", true);
      } else {
        setMsg(v, "Refused: " + b.why + ".", true);
      }
    }
    refresh(v);
  }

  function renderSlots(v) {
    var t = v.table;
    t.innerHTML = "";
    var nSlots = (v.api.cfg || {}).slots || 8;
    var any = false;
    for (var n = 1; n <= nSlots; n++) {
      var s = slots[n];
      if (!s || !s.saved) continue;
      any = true;
      (function (n, s) {
        var row = el("div", "lrow");
        row.appendChild(el("span", "lch", "Channel " + n));
        row.appendChild(el("span", "llab", s.label ? "head " + s.label : "(no number)"));
        row.appendChild(el("span", "lval", "drive " + pct(s.drv) +
          (s.thr === null || s.thr === undefined ? "" : ", threshold " + pct(s.thr))));
        var f = el("button", "nudge", v.forgetArm === n ? "Press again to forget" : "Forget");
        f.type = "button";
        f.addEventListener("click", function () { forget(v, n); });
        row.appendChild(f);
        t.appendChild(row);
      })(n, s);
    }
    if (!any) t.appendChild(el("div", "lrow", "Nothing saved yet: every channel starts with the defaults."));
  }

  function slot(b) {
    if (!b || typeof b.ch !== "number") return;
    slots[b.ch] = { saved: !!b.saved, drv: b.drv, thr: b.thr, label: b.label };
    for (var i = 0; i < views.length; i++) renderSlots(views[i]);
  }

  window.Lineup = { attach: attach, suggest: suggest, slot: slot, slots: function () { return slots; } };
})();
