/* sandtest.js -- the Sandtest rig page.
 *
 * Talks only to Sandbells (/sandtest/status and /sandtest/cmd); Django passes
 * on to the rig.  No libraries.  The status is polled once a second, and only
 * while the page is visible: a hidden tab, or a kiosk showing another page,
 * never wakes the rig.
 *
 * The pure helpers (formatting, building command JSON) are exported for the
 * node tests in sandtest/js_tests/.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Sandtest = api;
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", api.start);
    else api.start();
  }
})(this, function () {
  "use strict";

  var STALE_MS = 3500;          // a status older than this is shown as stale
  var MAX_LOG = 8;
  var FETCH_TIMEOUT_MS = 4000;  // a little over the proxy's own 2 s

  // ---- pure helpers ------------------------------------------------------

  function fmtAge(ms) {
    if (ms === null || ms === undefined) return "never";
    if (ms < 10000) return (Math.max(0, ms) / 1000).toFixed(1) + " s";
    if (ms < 60000) return Math.round(ms / 1000) + " s";
    var s = Math.round(ms / 1000);
    return Math.floor(s / 60) + " min " + (s % 60) + " s";
  }

  /* -> {cls: "ok"|"busy"|"wait", text, stale}: the connection pill.
   * lastGood: ms timestamp of the last good status or null; err: the reason
   * the latest poll failed, or "" when it succeeded. */
  function connState(now, lastGood, err) {
    if (lastGood === null || lastGood === undefined) {
      if (err) return { cls: "wait", text: "not reachable: " + err, stale: false };
      return { cls: "wait", text: "waiting for the rig…", stale: false };
    }
    var age = now - lastGood;
    if (err || age > STALE_MS) {
      return { cls: "busy", stale: true,
               text: "NO ANSWER · last good status " + fmtAge(age) + " ago" + (err ? " · " + err : "") };
    }
    return { cls: "ok", text: "connected · status " + fmtAge(age) + " old", stale: false };
  }

  function num(v, digits) {
    if (v === null || v === undefined || v === "" || isNaN(Number(v))) return "–";
    return digits === undefined ? String(Number(v)) : Number(v).toFixed(digits);
  }

  /* The heads table rows from a status' sweep block. */
  function headRows(sweep) {
    if (!sweep || !sweep.heads) return [];
    var faces = sweep.faces || {};
    var inwin = sweep.in_window || [];
    return Object.keys(sweep.heads).map(Number).sort(function (a, b) { return a - b; }).map(function (n) {
      var h = sweep.heads[String(n)] || {};
      var a = Number(h.angle_deg);
      return {
        head: n, angle: h.angle_deg, width: h.width_deg,
        mirrorAt: "mirror" in faces ? a + Number(faces.mirror) : null,
        reflectorAt: "reflector" in faces ? a + Number(faces.reflector) : null,
        inWindow: inwin.indexOf(n) >= 0
      };
    });
  }

  /* The head-window flag: {cls: "none"|"clear"|"hit", text}. */
  function windowFlag(sweep) {
    if (!sweep) return { cls: "none", text: "–" };
    if (sweep.hit) {
      var w = (sweep.in_window || []).join(", ");
      return { cls: "hit", text: "IN WINDOW: head " + w + (sweep.window_face ? " (" + sweep.window_face + ")" : "") };
    }
    return { cls: "clear", text: "clear of every head" };
  }

  // ---- command building --------------------------------------------------
  // Each spec: the rig's cmd (and sweep mode), and for each form field its
  // type.  An empty field is left out so the rig's own default applies.

  var INT = "int", NUM = "num", STR = "str", BOOL = "bool", FACE = "face";
  var SPECS = {
    press: { cmd: "press", f: { channel: [INT, 1, 8, true], press_ms: [INT, 1] } },
    play: { cmd: "play", f: { pattern: [STR, 0, 0, true], interval_ms: [INT, 1], press_ms: [INT, 1], repeat: [INT, 1] } },
    stress: { cmd: "stress", f: { seed: [INT, 0, 4294967295], seconds: [INT, 1, 86400] } },
    sweep: { cmd: "sweep", mode: "sweep", f: { from_deg: [NUM, -36000, 36000, true], to_deg: [NUM, -36000, 36000, true],
             speed_dps: [NUM, 0.05, 3600], dwell_ms: [INT, 0], cycles: [INT, 0] } },
    scan: { cmd: "sweep", mode: "scan", f: { speed_dps: [NUM, 0.05, 3600], dwell_ms: [INT, 0], cycles: [INT, 0], face: [FACE] } },
    visit: { cmd: "sweep", mode: "visit", f: { head: [INT, 1, 8, true], dwell_ms: [INT, 0], face: [FACE] } },
    menace: { cmd: "sweep", mode: "menace", f: { seed: [INT, 0, 4294967295], seconds: [INT, 0, 86400],
              face: [FACE], allow_hits: [BOOL] } },
    profile: { cmd: "sweep", mode: "profile", f: { head: [INT, 1, 8, true], face: [FACE, 0, 0, true], span_deg: [NUM, 0, 360],
               step_deg: [NUM, 0.01, 360], dwell_ms: [INT, 1], passes: [INT, 1, 10000] } }
  };
  var FACES = ["mirror", "reflector"];

  /* kind: a key of SPECS; values: {field: string | boolean}.
   * -> {cmd: {...}} or {error: "..."}. */
  function buildCommand(kind, values) {
    var spec = SPECS[kind];
    if (!spec) return { error: "unknown command " + kind };
    var out = { cmd: spec.cmd };
    if (spec.mode) out.mode = spec.mode;
    var names = Object.keys(spec.f);
    for (var i = 0; i < names.length; i++) {
      var name = names[i], t = spec.f[name], type = t[0], lo = t[1], hi = t[2], req = !!t[3];
      var raw = values[name];
      if (type === BOOL) { if (raw === true) out[name] = true; else if (raw === false && kind === "menace") out[name] = false; continue; }
      raw = (raw === undefined || raw === null) ? "" : String(raw).trim();
      if (raw === "") {
        if (req) return { error: name.replace(/_/g, " ") + " is needed" };
        continue;
      }
      if (type === STR) {
        var p = raw.toLowerCase() === "rounds" ? "rounds" : raw.replace(/\s+/g, " ");
        if (p !== "rounds" && !/^[1-8]+( [1-8]+)*$/.test(p)) {
          return { error: "pattern must be bell numbers 1-8 like 13425678 (rows split by spaces), or rounds" };
        }
        out[name] = p;
      } else if (type === FACE) {
        if (FACES.indexOf(raw) < 0) return { error: "face must be mirror or reflector" };
        out[name] = raw;
      } else {
        var v = Number(raw);
        if (!isFinite(v)) return { error: name.replace(/_/g, " ") + " must be a number" };
        if (type === INT && Math.floor(v) !== v) return { error: name.replace(/_/g, " ") + " must be a whole number" };
        if (lo !== undefined && v < lo) return { error: name.replace(/_/g, " ") + " must be at least " + lo };
        if (hi !== undefined && hi !== 0 && v > hi) return { error: name.replace(/_/g, " ") + " must be at most " + hi };
        out[name] = v;
      }
    }
    return { cmd: out };
  }

  // ---- the page ----------------------------------------------------------

  function start() {
    var rootEl = document.getElementById("sandtest-root");
    if (!rootEl || rootEl.getAttribute("data-started")) return;
    rootEl.setAttribute("data-started", "1");

    var STATUS_URL = rootEl.getAttribute("data-status-url");
    var CMD_URL = rootEl.getAttribute("data-cmd-url");
    var POLL_MS = parseInt(rootEl.getAttribute("data-poll-ms"), 10) || 1000;

    var $ = function (id) { return document.getElementById(id); };
    var lastGood = null, lastErr = "", fails = 0;
    var inflight = false, pollTimer = null, connTimer = null;

    var ukTime = (function () {
      try {
        var f = new Intl.DateTimeFormat("en-GB", { timeZone: "Europe/London", hourCycle: "h23",
                                                   hour: "2-digit", minute: "2-digit", second: "2-digit" });
        return function (d) { return f.format(d); };
      } catch (e) {
        return function (d) { return d.toTimeString().slice(0, 8); };
      }
    })();

    function csrfToken() {
      var m = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
      return m ? decodeURIComponent(m[1]) : "";
    }
    function visible() { return !document.hidden; }
    function text(id, v) { var n = $(id); if (n) n.textContent = (v === null || v === undefined || v === "") ? "–" : String(v); }

    // -- talking to Sandbells
    function fetchJson(url, opts) {
      var ctl = window.AbortController ? new AbortController() : null;
      var guard = ctl ? setTimeout(function () { ctl.abort(); }, FETCH_TIMEOUT_MS) : null;
      opts = opts || {};
      opts.cache = "no-store";
      if (ctl) opts.signal = ctl.signal;
      return fetch(url, opts)
        .then(function (r) {
          return r.json().catch(function () { return { ok: false, error: "Sandbells answered HTTP " + r.status + " without JSON" }; });
        })
        .catch(function (e) {
          return { ok: false, error: "Sandbells not answering (" + (e && e.name === "AbortError" ? "timed out" : (e && e.message) || "network") + ")" };
        })
        .then(function (res) { if (guard) clearTimeout(guard); return res; });
    }

    function send(cmd) {
      return fetchJson(CMD_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify(cmd)
      });
    }

    // -- drawing
    function renderConn() {
      var c = connState(Date.now(), lastGood, lastErr);
      var pill = $("st-conn");
      pill.className = "pill pill-" + c.cls;
      pill.textContent = c.text;
      rootEl.className = c.stale ? "stale" : "";
    }

    function renderStatus(rig) {
      var pl = rig.player || {}, sw = rig.sweep || {};
      text("st-version", rig.version ? rig.version + (rig.device ? " · " + rig.device : "") : null);
      text("st-player-state", pl.state);
      text("st-presses", pl.presses_sent);
      text("st-pressed", (pl.pressed && pl.pressed.length) ? pl.pressed.join(" ") : "none");
      text("st-late", pl.max_late_ms);
      text("st-loop", rig.loop_max_ms);
      text("st-mem", rig.mem_free_kb);
      text("st-mode", sw.mode ? sw.mode + (sw.phase ? " · " + sw.phase : "") : null);
      text("st-angle", sw.angle_deg !== undefined ? num(sw.angle_deg, 2) + "°" : null);
      text("st-beam", sw.beam_deg !== undefined ? num(sw.beam_deg, 2) + "°" : null);
      text("st-face", sw.face);
      text("st-speed", sw.speed_dps !== undefined ? num(sw.speed_dps, 2) + " °/s" : null);
      text("st-target", sw.target_deg !== undefined ? num(sw.target_deg, 2) + "°" : "none");
      text("st-limits", sw.limits_deg ? num(sw.limits_deg[0], 1) + "° … " + num(sw.limits_deg[1], 1) + "°" : "none set");
      var f = windowFlag(sw), fl = $("st-window");
      fl.textContent = "";
      var span = document.createElement("span");
      span.className = "flag flag-" + f.cls;
      span.textContent = f.text;
      fl.appendChild(span);

      var extra = [];
      if (sw.profile) extra.push("profile: head " + sw.profile.head + " " + sw.profile.face + " point " + sw.profile.point + "/" + sw.profile.points +
                                 " pass " + sw.profile.pass + "/" + sw.profile.passes);
      if (sw.mode === "menace") extra.push("menace seed " + sw.seed + (sw.allow_hits ? " · HITS ALLOWED" : " · avoiding every head"));
      if (pl.run) extra.push("run: " + (typeof pl.run === "string" ? pl.run : JSON.stringify(pl.run)));
      text("st-extra", extra.join(" · "));
      if (!extra.length) $("st-extra").textContent = "";

      var wl = $("st-warnings");
      wl.textContent = "";
      (sw.warnings || []).forEach(function (w) {
        var li = document.createElement("li");
        li.textContent = String(w);
        wl.appendChild(li);
      });

      var tb = $("st-heads").tBodies[0];
      tb.textContent = "";
      var rows = headRows(sw);
      if (!rows.length) {
        var tr0 = document.createElement("tr"), td0 = document.createElement("td");
        td0.colSpan = 6; td0.className = "muted"; td0.textContent = "no heads configured on the rig";
        tr0.appendChild(td0); tb.appendChild(tr0);
      }
      rows.forEach(function (r) {
        var tr = document.createElement("tr");
        if (r.inWindow) tr.className = "inwin";
        [[r.head, ""], [num(r.angle, 2), "num"], [num(r.width, 2), "num"], [num(r.mirrorAt, 2), "num"],
         [num(r.reflectorAt, 2), "num"], [r.inWindow ? "IN WINDOW" : "", ""]].forEach(function (c) {
          var td = document.createElement("td");
          td.textContent = c[0];
          if (c[1]) td.className = c[1];
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });

      var fb = document.querySelectorAll(".facebtn");
      for (var i = 0; i < fb.length; i++) {
        fb[i].setAttribute("aria-pressed", fb[i].getAttribute("data-face") === sw.face ? "true" : "false");
      }
    }

    // -- polling, only while visible
    function pollNow() {
      if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
      if (!visible() || inflight) return;
      inflight = true;
      fetchJson(STATUS_URL).then(function (res) {
        inflight = false;
        if (res && res.ok && res.rig) {
          lastGood = Date.now(); lastErr = ""; fails = 0;
          renderStatus(res.rig);
        } else {
          lastErr = (res && res.error) || "no status"; fails += 1;
        }
        renderConn();
        schedule();
      });
    }
    function schedule() {
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = null;
      if (!visible()) return;
      // while the rig is not answering, ask less often (up to every 5 s)
      var wait = fails ? Math.min(5000, POLL_MS * (1 + fails)) : POLL_MS;
      pollTimer = setTimeout(pollNow, wait);
    }
    function pollSoon() {
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = setTimeout(pollNow, 150);
    }
    function onVisibility() {
      if (visible()) {
        startConnTimer();
        pollNow();
      } else {
        if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
        if (connTimer) { clearInterval(connTimer); connTimer = null; }
      }
    }
    function startConnTimer() {
      if (!connTimer) connTimer = setInterval(renderConn, 1000);
    }

    // -- commands
    var logEl = $("st-log"), logRows = [];
    function addLog(cmd, ok, why) {
      logRows.unshift({ t: ukTime(new Date()), cmd: JSON.stringify(cmd), ok: ok, why: why || "" });
      logRows.length = Math.min(logRows.length, MAX_LOG);
      logEl.textContent = "";
      logRows.forEach(function (r) {
        var li = document.createElement("li");
        if (!r.ok) li.className = "bad";
        var code = document.createElement("code");
        code.textContent = r.cmd;
        li.appendChild(document.createTextNode(r.t + " "));
        li.appendChild(code);
        li.appendChild(document.createTextNode(r.ok ? " ✓" : " ✗ " + r.why));
        logEl.appendChild(li);
      });
    }

    function sendAndReport(cmd, msgEl, done) {
      return send(cmd).then(function (res) {
        var ok = !!(res && res.ok);
        var why = ok ? "" : ((res && res.error) || "failed");
        addLog(cmd, ok, why);
        if (msgEl) { msgEl.textContent = ok ? "sent" : why; msgEl.className = ok ? "msg" : "msg bad"; }
        if (ok) pollSoon();
        if (done) done(ok, why);
        return res;
      });
    }

    function formValues(form) {
      var v = {};
      for (var i = 0; i < form.elements.length; i++) {
        var el = form.elements[i];
        if (!el.name) continue;
        v[el.name] = el.type === "checkbox" ? el.checked : el.value;
      }
      return v;
    }

    var forms = document.querySelectorAll("form[data-cmd]");
    Array.prototype.forEach.call(forms, function (form) {
      var msg = form.querySelector(".msg");
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var built = buildCommand(form.getAttribute("data-cmd"), formValues(form));
        if (built.error) { msg.textContent = built.error; msg.className = "msg bad"; return; }
        msg.textContent = "sending…"; msg.className = "msg";
        sendAndReport(built.cmd, msg);
      });
      var risky = form.querySelector('input[name="allow_hits"]');
      if (risky) {
        var btn = form.querySelector('button[type="submit"]');
        risky.addEventListener("change", function () {
          form.className = risky.checked ? "hits-on" : "";
          btn.textContent = risky.checked ? "Menace (HITS ALLOWED)" : "Menace";
        });
      }
    });

    Array.prototype.forEach.call(document.querySelectorAll(".facebtn"), function (b) {
      b.addEventListener("click", function () {
        sendAndReport({ cmd: "face", face: b.getAttribute("data-face") }, $("st-face-msg"));
      });
    });
    $("st-park").addEventListener("click", function () {
      sendAndReport({ cmd: "park" }, $("st-face-msg"));
    });

    // -- STOP: never disabled; one automatic retry; says plainly if it failed
    var stopMsg = $("st-stopmsg");
    $("st-stop").addEventListener("click", function () {
      var cmd = { cmd: "stop" };
      stopMsg.textContent = "stopping…";
      sendAndReport(cmd, null, function (ok, why) {
        if (ok) { stopMsg.textContent = "stop sent " + ukTime(new Date()); return; }
        stopMsg.textContent = "STOP NOT CONFIRMED (" + why + ") · trying again";
        setTimeout(function () {
          sendAndReport(cmd, null, function (ok2, why2) {
            stopMsg.textContent = ok2 ? "stop sent " + ukTime(new Date())
              : "STOP FAILED: " + why2 + " · press again, or switch the rig off";
          });
        }, 400);
      });
    });

    document.addEventListener("visibilitychange", onVisibility);
    renderConn();
    if (visible()) { startConnTimer(); pollNow(); }
  }

  return { fmtAge: fmtAge, connState: connState, headRows: headRows, windowFlag: windowFlag,
           buildCommand: buildCommand, num: num, start: start, STALE_MS: STALE_MS };
});
