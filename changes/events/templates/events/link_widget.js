/* link_widget.js -- page 3 "Concentrator link" strip: the six panel LEDs as
 * the Pico last reported them (sand.panel/v1 heartbeat, kept by the ingest),
 * a connected / STALE / LOST verdict (or MIDI, cyan, when the Pico's USB
 * MIDI is live: api.midi_verdict), time since the last packet and
 * heartbeat, reconnects, last drop reason and the time-sync state (with the
 * stratum sandmon answered, so a GPS NO Lock shows here).  Polls
 * /events/api/link/ (a tmpfs file, no DB).  Goes grey after stale_ms with no
 * heartbeat, red after lost_ms or when the ingest is down.  Included inline by
 * events/live_panel.html; pure helpers exported for node tests.
 * When the Wi-Fi heartbeat is not fresh, the Pico's USB serial one stands in
 * (data.via "usb serial", api.serial_link) and the text says "via usb serial";
 * the LEDs show whenever the heartbeat behind them is live (v.live). */
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
  /* survey kinds (sandswing socket_classify / panel states) -> short words */
  var KIND_WORDS = {
    head_new: "new head", head_old: "old head", loopback: "loopback",
    trigger: "trigger", empty: "empty", fault: "FAULT", no_board: "no board",
    unknown: "?", examining: "checking", surveying: "checking", response: "stroke"
  };
  var NOTE_KINDS = { fault: "bad", trigger: "trig" };   // why shown for these
  var PANEL_CHANNELS = 4;                              // LEDs 2-5 = ch 1-4
  var VIA_SERIAL = "usb serial";                       // api.serial_link
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

  /* ch 1-4 kind words under the LEDs, and a why line for every fault or
   * trigger channel (body.chan = [[kind, why|null], ...], newer firmware;
   * older firmware: the panel_state names only). */
  function channels(body) {
    var chan = body && body.chan ? body.chan : null;
    var states = body && body.panel_state ? body.panel_state : [];
    var kinds = [], notes = [];
    for (var i = 0; i < PANEL_CHANNELS; i++) {
      var k = chan && chan[i] ? chan[i][0] : states[i + 1];
      kinds.push(k ? KIND_WORDS[k] || k : "");
    }
    (chan || []).forEach(function (c, i) {
      if (c && NOTE_KINDS[c[0]]) {
        notes.push({ cls: NOTE_KINDS[c[0]],
                     text: "ch " + (i + 1) + " " + (KIND_WORDS[c[0]] || c[0]) +
                           (c[1] ? ": " + c[1] : "") });
      }
    });
    return { kinds: kinds, notes: notes };
  }

  function view(data) {
    var ing = data.ingest || {};
    var pico = data.pico || null;
    var body = pico ? pico.body || {} : null;
    var net = body ? body.net || {} : {};
    var headline = { ok: "CONNECTED", stale: "STALE", lost: "LOST", midi: "MIDI",
                     no_ingest: "INGEST DOWN" }[data.verdict] || "?";
    if (data.verdict === "midi") return midiView(data);
    var parts = data.via === VIA_SERIAL
      ? ["via usb serial", "heartbeat " + ago(data.hb_age_ms) + " ago",
         "Wi-Fi " + (data.wifi_verdict || "?") + ", packet " + ago(data.rx_age_ms) + " ago"]
      : ["packet " + ago(data.rx_age_ms) + " ago",
         "heartbeat " + ago(data.hb_age_ms) + " ago",
         "reconnects " + (ing.reconnects || 0)];
    if (net.drops) parts.push("Pico drops " + net.drops);
    if (body && body.wifi && body.wifi.rssi !== null && body.wifi.rssi !== undefined) {
      parts.push("RSSI " + body.wifi.rssi);
    }
    var drop = ing.last_drop_reason || net.last_drop_reason || null;
    var ch = channels(body);
    return {
      cls: data.verdict === "ok" ? "ok" : data.verdict === "stale" ? "stale" : "lost",
      live: data.verdict === "ok", via: data.via || "",
      headline: headline, why: data.why || "",
      detail: parts.join(" · "),
      drop: drop ? "last drop: " + drop : "",
      time: timeLine(body), timeCls: syncClass(body),
      leds: (body && body.panel ? body.panel : []).map(cssColour),
      states: body && body.panel_state ? body.panel_state : [],
      kinds: ch.kinds, notes: ch.notes
    };
  }

  /* MIDI: the LEDs, heads and time line show while the heartbeat behind
   * them is fresh (data.hb_live, api.link: Wi-Fi or USB serial); an old one
   * is not shown */
  function midiView(data) {
    var m = data.midi || {}, st = m.stamp || {};
    var v = {
      cls: "midi", live: false, via: data.via || "", headline: "MIDI", why: data.why || "",
      detail: "strokes " + (m.strokes || 0) + " · stamped " + (st.stamped || 0) +
              " · unstamped " + (st.unstamped || 0) + " · clocks " + (st.clocks || 0),
      drop: "", time: "", timeCls: "", leds: [], states: [], kinds: [], notes: []
    };
    var body = data.hb_live && data.pico ? data.pico.body || null : null;
    if (body) {
      var ch = channels(body);
      v.live = true;
      v.detail += " · " + (data.via === VIA_SERIAL ? "status via usb serial, " : "") +
                  "heartbeat " + ago(data.hb_age_ms) + " ago";
      v.time = timeLine(body);
      v.timeCls = syncClass(body);
      v.leds = (body.panel || []).map(cssColour);
      v.states = body.panel_state || [];
      v.kinds = ch.kinds;
      v.notes = ch.notes;
    }
    return v;
  }

  var api = { midiView: midiView, cssColour: cssColour, ago: ago, timeLine: timeLine, view: view,
              syncClass: syncClass, channels: channels };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }

  var box = document.getElementById("link-widget");
  if (!box) return;
  var cfg = { url: box.dataset.url, poll: +box.dataset.poll, timeout: +box.dataset.timeout };
  var leds = box.querySelectorAll(".lw-led");
  var kindEls = box.querySelectorAll(".lw-kind");
  function el(id) { return document.getElementById(id); }
  function text(id, s) { var e = el(id); if (e && e.textContent !== s) e.textContent = s; }

  function show(v) {
    box.className = "lw " + v.cls;
    var panel = document.getElementById("live-events");
    if (panel) panel.setAttribute("data-link", v.cls);   // the clock takes its colour from this
    text("lw-head", v.headline);
    text("lw-why", v.why);
    text("lw-detail", v.detail);
    text("lw-drop", v.drop);
    text("lw-time", v.time);
    el("lw-time").className = "lw-time " + v.timeCls;
    for (var i = 0; i < leds.length; i++) {
      leds[i].style.background = v.live && v.leds[i] ? v.leds[i] : DARK;
      leds[i].title = LED_NAMES[i] + ": " + (STATE_WORDS[v.states[i]] || v.states[i] || "?");
    }
    for (var j = 0; j < kindEls.length; j++) {
      var kw = v.live && v.kinds ? v.kinds[j] || "" : "";
      if (kindEls[j].textContent !== kw) kindEls[j].textContent = kw;
      kindEls[j].className = "lw-kind" + (kw === "FAULT" ? " bad" : kw === "trigger" ? " trig" : "");
    }
    var notes = el("lw-chans");
    if (notes) {                               // stale/lost: say nothing old
      var html = (v.live && v.notes ? v.notes : []).map(function (n) {
        var d = document.createElement("div");
        d.className = "lw-note " + n.cls;
        d.textContent = n.text;
        return d.outerHTML;
      }).join("");
      if (notes.innerHTML !== html) notes.innerHTML = html;
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
        show({ cls: "lost", live: false, headline: "?", why: "Sandbells not answering: " + e.message,
               detail: "", drop: "", time: "", timeCls: "", leds: [], states: [],
               kinds: [], notes: [] });
      })
      .then(function () { setTimeout(poll, cfg.poll); });
  }
  poll();
})();
