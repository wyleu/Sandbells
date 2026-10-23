/* link_widget.js -- page 3 "Concentrator link" strip: the six panel LEDs as
 * the Pico last reported them (sand.panel/v1 heartbeat, kept by the ingest),
 * a connected / STALE / LOST verdict, time since the last packet and
 * heartbeat, reconnects, last drop reason and the time-sync state (with the
 * stratum sandmon answered, so a GPS NO Lock shows here).  Polls
 * /events/api/link/ (a tmpfs file, no DB).  Goes grey after stale_ms with no
 * heartbeat, red after lost_ms or when the ingest is down.  Included inline by
 * events/live_panel.html; pure helpers exported for node tests. */
(function () {
  "use strict";
  var MS_PER_S = 1000, S_PER_MIN = 60;
  var FULL = 255, DARK = "#222";
  var LED_NAMES = ["link", "ch1", "ch2", "ch3", "ch4", "beat"];
  var STATE_WORDS = {
    ws_client: "Sandbells connected", wifi_only: "Wi-Fi, no Sandbells",
    no_wifi: "no Wi-Fi", error: "link error",
    heartbeat: "time synced", heartbeat_nosync: "NOT synced",
    heartbeat_holdover: "holdover (time server lost)", ringing: "ringing",
    ringing_down: "ringing down", watchdog_reset: "after watchdog reset"
  };
  var SYNC_WORDS = { synced: "synced", stale: "holdover", held: "held (ringing)",
                     unsynced: "NOT synced" };

  /* panel rgb (0..~48, dim on purpose) -> a CSS colour bright enough to see */
  function cssColour(rgb) {
    if (!rgb || rgb.length < 3) return DARK;
    var m = Math.max(rgb[0], rgb[1], rgb[2]);
    if (m <= 0) return DARK;
    var k = FULL / m;
    return "rgb(" + Math.round(rgb[0] * k) + "," + Math.round(rgb[1] * k) + "," +
           Math.round(rgb[2] * k) + ")";
  }

  function ago(ms) {
    if (ms === null || ms === undefined) return "never";
    var s = Math.floor(ms / MS_PER_S);
    if (s < S_PER_MIN) return s + " s";
    return Math.floor(s / S_PER_MIN) + " min " + (s % S_PER_MIN) + " s";
  }

  /* sandmon's lock as the Pico saw it: the last reply's stratum and leap */
  function timeLine(body) {
    if (!body) return "time: —";
    var sync = SYNC_WORDS[body.sync] || body.sync || "?";
    var t = body.time || {};
    var peer = t.peer || null;
    var src = peer && peer.srv ? peer.srv : (t.srv || "time server");
    var lock = "";
    if (peer && (peer.stratum === 0 || peer.stratum >= 16 || peer.leap === 3)) {
      lock = " · " + src + " NOT LOCKED (stratum " + peer.stratum + ")";
    } else if (peer) {
      lock = " · " + src + " stratum " + peer.stratum;
    }
    var why = t.last && t.last.ok === false && t.last.why ? " · last: " + t.last.why : "";
    return "time: " + sync + lock + why;
  }

  function syncClass(body) {
    var s = body && body.sync;
    return s === "synced" || s === "held" ? "ok" : s === "stale" ? "warn" : "bad";
  }

  function view(data) {
    var ing = data.ingest || {};
    var pico = data.pico || null;
    var body = pico ? pico.body || {} : null;
    var net = body ? body.net || {} : {};
    var headline = { ok: "CONNECTED", stale: "STALE", lost: "LOST",
                     no_ingest: "INGEST DOWN" }[data.verdict] || "?";
    var parts = ["packet " + ago(data.rx_age_ms) + " ago",
                 "heartbeat " + ago(data.hb_age_ms) + " ago",
                 "reconnects " + (ing.reconnects || 0)];
    if (net.drops) parts.push("Pico drops " + net.drops);
    if (body && body.wifi && body.wifi.rssi !== null && body.wifi.rssi !== undefined) {
      parts.push("RSSI " + body.wifi.rssi);
    }
    var drop = ing.last_drop_reason || net.last_drop_reason || null;
    return {
      cls: data.verdict === "ok" ? "ok" : data.verdict === "stale" ? "stale" : "lost",
      headline: headline, why: data.why || "",
      detail: parts.join(" · "),
      drop: drop ? "last drop: " + drop : "",
      time: timeLine(body), timeCls: syncClass(body),
      leds: (body && body.panel ? body.panel : []).map(cssColour),
      states: body && body.panel_state ? body.panel_state : []
    };
  }

  var api = { cssColour: cssColour, ago: ago, timeLine: timeLine, view: view,
              syncClass: syncClass };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }

  var box = document.getElementById("link-widget");
  if (!box) return;
  var cfg = { url: box.dataset.url, poll: +box.dataset.poll, timeout: +box.dataset.timeout };
  var leds = box.querySelectorAll(".lw-led");
  function el(id) { return document.getElementById(id); }
  function text(id, s) { var e = el(id); if (e && e.textContent !== s) e.textContent = s; }

  function show(v) {
    box.className = "lw " + v.cls;
    text("lw-head", v.headline);
    text("lw-why", v.why);
    text("lw-detail", v.detail);
    text("lw-drop", v.drop);
    text("lw-time", v.time);
    el("lw-time").className = "lw-time " + v.timeCls;
    for (var i = 0; i < leds.length; i++) {
      leds[i].style.background = v.cls === "ok" && v.leds[i] ? v.leds[i] : DARK;
      leds[i].title = LED_NAMES[i] + ": " + (STATE_WORDS[v.states[i]] || v.states[i] || "?");
    }
    var word = v.states[0] ? STATE_WORDS[v.states[0]] || v.states[0] : "";
    var beat = v.states[5] ? STATE_WORDS[v.states[5]] || v.states[5] : "";
    text("lw-leds", word + (beat ? " · " + beat : ""));
  }

  function poll() {
    var ctl = window.AbortController ? new AbortController() : null;
    var guard = ctl ? setTimeout(function () { ctl.abort(); }, cfg.timeout) : null;
    fetch(cfg.url, { cache: "no-store", signal: ctl ? ctl.signal : undefined })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) { clearTimeout(guard); show(view(data)); })
      .catch(function (e) {
        clearTimeout(guard);
        show({ cls: "lost", headline: "?", why: "Sandbells not answering: " + e.message,
               detail: "", drop: "", time: "", timeCls: "", leds: [], states: [] });
      })
      .then(function () { setTimeout(poll, cfg.poll); });
  }
  poll();
})();
