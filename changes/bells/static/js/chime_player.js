/* Chimes player: Play / Stop / tempo, the MIDI out and HDMI audio switches,
 * and a dot that follows the music.
 *
 * The music plays on the Pi (aplaymidi and/or fluidsynth, started by the
 * server; with both switches off the dot runs silently), so this
 * page only asks the server what is playing (state: tune, start time on
 * the server clock, tempo factor) and works out from its own clock where
 * the music is: the dot moves every tick, not every poll.  When the music
 * reaches another page, the page for it is opened (the player carries on).
 * A switch is kept on the server (it survives a reload); changed while
 * this tune plays, the tune is started again from where it is.
 * Same code in the full-screen view.  Plain ES5 for Luakit.
 */
var ChimePlayerHelpers = (function () {
  "use strict";
  var PORT_AUTO = "port: automatic";

  // "(MIDI 20:0, HDMI)" / "(silent)": what the state says it is playing to
  function playingTo(to) {
    var parts = [];
    if (to && to.midi_out) { parts.push("MIDI " + to.midi_port); }
    if (to && to.hdmi_audio) { parts.push("HDMI"); }
    return parts.length ? "(" + parts.join(", ") + ")" : "(silent)";
  }

  // The port menu: automatic first, then each allowed port, then the saved
  // one if it is not plugged in now.  [[value, text], ...]
  function portChoices(ports, saved) {
    var out = [["", PORT_AUTO]], found = false, i;
    for (i = 0; i < ports.length; i += 1) {
      out.push([ports[i].id, ports[i].id + " " + ports[i].client]);
      if (ports[i].id === saved) { found = true; }
    }
    if (saved && !found) { out.push([saved, saved + " (not there now)"]); }
    return out;
  }

  // Index of the last event at or before sec (-1: before the first).
  function eventAt(events, sec) {
    var lo = 0, hi = events.length, mid;
    while (lo < hi) {
      mid = (lo + hi) >> 1;
      if (events[mid][0] <= sec) { lo = mid + 1; } else { hi = mid; }
    }
    return lo - 1;
  }

  return { PORT_AUTO: PORT_AUTO, playingTo: playingTo, portChoices: portChoices,
           eventAt: eventAt };
})();
if (typeof module !== "undefined" && module.exports) { module.exports = ChimePlayerHelpers; }

(function () {
  "use strict";
  if (typeof document === "undefined") { return; }
  var H = ChimePlayerHelpers;
  var MS_PER_S = 1000;
  var PERCENT = 100;
  var box = document.getElementById("chime-player");
  if (!box) { return; }

  var slug = box.getAttribute("data-slug");
  var page = parseInt(box.getAttribute("data-page"), 10);
  var img = document.getElementById(box.getAttribute("data-image-id"));
  var dot = document.getElementById("chime-dot");
  var playBtn = document.getElementById("chime-play");
  var stopBtn = document.getElementById("chime-stop");
  var tempo = document.getElementById("chime-tempo");
  var tempoLabel = document.getElementById("chime-tempo-label");
  var statusEl = document.getElementById("chime-status");
  var midiBtn = document.getElementById("chime-midi");
  var hdmiBtn = document.getElementById("chime-hdmi");
  var portSel = document.getElementById("chime-port");
  var outputs = {
    midi_out: midiBtn.getAttribute("aria-pressed") === "true",
    hdmi_audio: hdmiBtn.getAttribute("aria-pressed") === "true",
    midi_port: portSel.value
  };
  var pollMs = parseInt(box.getAttribute("data-state-poll-ms"), 10);
  var tickMs = parseInt(box.getAttribute("data-dot-tick-ms"), 10);
  var tempoKey = "chimeTempo:" + slug;

  var events = null;      // [[sec, page, fx, fy], ...] in playing order
  var bpm = null;
  var state = null;
  var clockOffset = 0;    // server clock minus this clock, seconds
  var leaving = false;

  function csrf() {
    var input = box.querySelector("input[name=csrfmiddlewaretoken]");
    if (input) { return input.value; }
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify(body || {})
    }).then(function (r) { return r.json(); });
  }

  function showTempo() {
    var pct = parseInt(tempo.value, 10);
    tempoLabel.textContent = pct + "%" + (bpm ? " (" + Math.round(bpm * pct / PERCENT) + " bpm)" : "");
  }

  function showOutputs() {
    midiBtn.setAttribute("aria-pressed", outputs.midi_out ? "true" : "false");
    midiBtn.querySelector("b").textContent = outputs.midi_out ? "on" : "off";
    hdmiBtn.setAttribute("aria-pressed", outputs.hdmi_audio ? "true" : "false");
    hdmiBtn.querySelector("b").textContent = outputs.hdmi_audio ? "on" : "off";
    portSel.disabled = !outputs.midi_out;
  }

  function addOption(value, text) {
    var o = document.createElement("option");
    o.value = value;
    o.textContent = text;
    portSel.appendChild(o);
    return o;
  }

  function showPorts(list) {
    var want = outputs.midi_port || "", choices = H.portChoices(list, want), i;
    while (portSel.firstChild) { portSel.removeChild(portSel.firstChild); }
    for (i = 0; i < choices.length; i += 1) { addOption(choices[i][0], choices[i][1]); }
    portSel.value = want;
  }

  function loadPorts() {
    fetch(box.getAttribute("data-ports-url"), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (j.outputs) { outputs = j.outputs; showOutputs(); }
        showPorts(j.ports || []);
        if (j.error) { portSel.title = j.error; }
      })
      .catch(function () { /* keep what the page had */ });
  }

  function mineAndPlaying() {
    return state && state.playing && state.slug === slug;
  }

  function setOutputs(change) {
    post(box.getAttribute("data-outputs-url"), change)
      .then(function (j) {
        if (!j.ok) { statusEl.textContent = j.error || "could not change the outputs"; return; }
        outputs = j.outputs;
        showOutputs();
        var sec = writtenNow();
        if (mineAndPlaying() && sec !== null) { play(Math.max(0, sec)); }   // live
      })
      .catch(function () { statusEl.textContent = "could not reach the player"; });
  }

  function pageUrl(n) {
    return box.getAttribute("data-page-url").replace(box.getAttribute("data-page-placeholder"), String(n));
  }

  function writtenNow() {
    if (!state || !state.playing || !state.started_at) { return null; }
    return (Date.now() / MS_PER_S + clockOffset - state.started_at) * state.tempo_factor;
  }


  function placeDot(fx, fy) {
    if (!img || !img.naturalWidth) { return; }
    var r = img.getBoundingClientRect();
    var nw = img.naturalWidth, nh = img.naturalHeight;
    var s = Math.min(r.width / nw, r.height / nh);          // object-fit: contain
    var left = r.left + (r.width - nw * s) / 2 + fx * nw * s;
    var top = r.top + (r.height - nh * s) / 2 + fy * nh * s;
    dot.style.left = left + "px";
    dot.style.top = top + "px";
    dot.hidden = false;
  }

  function tick() {
    var sec = writtenNow();
    if (sec === null || !events || state.slug !== slug || sec < 0) { dot.hidden = true; return; }
    var i = H.eventAt(events, sec);
    while (i >= 0 && events[i][1] === null) { i -= 1; }     // not on the sheet: stay put
    if (i < 0) { dot.hidden = true; return; }
    var ev = events[i];
    if (ev[1] !== page) {
      if (!leaving) { leaving = true; window.location.replace(pageUrl(ev[1])); }
      return;
    }
    placeDot(ev[2], ev[3]);
  }

  function showState() {
    var mine = state && state.slug === slug;
    playBtn.disabled = false;
    stopBtn.disabled = !(state && state.playing);
    if (state && state.playing) {
      statusEl.textContent = (state.phase === "loading" ? "Starting " : "Playing ") +
        (mine ? "" : state.title + " ") + H.playingTo(state.playing_to);
      if (mine && state.tempo_factor) {
        tempo.value = Math.round(state.tempo_factor * PERCENT);
        showTempo();
      }
    } else if (state && state.phase === "error") {
      statusEl.textContent = "Player: " + state.error;
    } else {
      statusEl.textContent = "";
    }
  }

  function poll() {
    var asked = Date.now();
    fetch(box.getAttribute("data-state-url"), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        state = j;
        if (j.outputs) { outputs.midi_out = j.outputs.midi_out; outputs.hdmi_audio = j.outputs.hdmi_audio; showOutputs(); }
        clockOffset = j.now - (asked + Date.now()) / 2 / MS_PER_S;
        showState();
      })
      .catch(function () { /* next poll */ });
  }

  function play(fromSec) {
    try { sessionStorage.setItem(tempoKey, tempo.value); } catch (e) { /* private mode */ }
    playBtn.disabled = true;
    post(box.getAttribute("data-play-url"),
         { slug: slug, tempo: parseInt(tempo.value, 10), from_sec: fromSec || 0 })
      .then(function (j) {
        if (!j.ok) { statusEl.textContent = j.error || "could not play"; }
        poll();
      })
      .catch(function () { statusEl.textContent = "could not reach the player"; playBtn.disabled = false; });
  }

  playBtn.addEventListener("click", function () { play(0); });
  stopBtn.addEventListener("click", function () {
    post(box.getAttribute("data-stop-url")).then(poll, poll);
  });
  midiBtn.addEventListener("click", function () { setOutputs({ midi_out: !outputs.midi_out }); });
  hdmiBtn.addEventListener("click", function () { setOutputs({ hdmi_audio: !outputs.hdmi_audio }); });
  portSel.addEventListener("change", function () { setOutputs({ midi_port: portSel.value }); });
  tempo.addEventListener("input", showTempo);
  tempo.addEventListener("change", function () {
    var sec = writtenNow();
    if (state && state.playing && state.slug === slug && sec !== null) { play(Math.max(0, sec)); }
    else { try { sessionStorage.setItem(tempoKey, tempo.value); } catch (e) { /* ignore */ } }
  });
  window.addEventListener("resize", tick);

  try {
    var saved = sessionStorage.getItem(tempoKey);
    if (saved) { tempo.value = saved; }
  } catch (e) { /* ignore */ }
  showTempo();
  showOutputs();
  loadPorts();

  var notemapUrl = box.getAttribute("data-notemap-url");
  if (notemapUrl) {
    fetch(notemapUrl, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (j) { events = j.events; bpm = j.bpm; showTempo(); })
      .catch(function () { events = null; });
  }
  poll();
  setInterval(poll, pollMs);
  setInterval(tick, tickMs);
})();
