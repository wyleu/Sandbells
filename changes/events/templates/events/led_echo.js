/* led_echo.js -- the concentrator panel as the Pico paints it, shared by the
 * Strokes page strip (link_widget.js) and the sandswing farm page Panel
 * (bells/farm_leds.js).  Included inline (no /static, so no cache to bust).
 *
 *   cssColour(rgb)        panel rgb (dim on purpose, 0..~48) -> CSS colour:
 *                         brightest channel to FULL, black DARK (the same
 *                         rule as bells.status_schema.panel_css; a test
 *                         checks they agree)
 *   ledEcho(reply)        /events/api/leds/ reply -> {leds, states} or null
 *   ledFrames(reply, n)   the lines not yet shown since line n, oldest first
 *   create(o)             the fast poll of /events/api/leds/: o.url, o.pollMs,
 *                         o.max (lines queued), o.timeoutMs, o.paint(frame |
 *                         null).  want(true) starts it (it stops by itself
 *                         when the echo is not live or the page is hidden);
 *                         frame() is what is shown now.  Every line the Pico
 *                         sent is shown for at least one poll, so a 0.25 s
 *                         stroke flash between two polls is not missed.
 */
(function (root) {
  "use strict";
  var FULL = 255, DARK = "#222";

  function cssColour(rgb) {
    if (!rgb || rgb.length < 3) return DARK;
    var m = Math.max(rgb[0], rgb[1], rgb[2]);
    if (m <= 0) return DARK;
    var k = FULL / m;
    return "rgb(" + Math.round(rgb[0] * k) + "," + Math.round(rgb[1] * k) + "," +
           Math.round(rgb[2] * k) + ")";
  }

  function ledEcho(d) {
    if (!d || !d.live || !d.panel) return null;
    return { leds: d.panel.map(cssColour), states: d.panel_state || [] };
  }

  /* First reply, or n went back (Pico rebooted): just the newest. */
  function ledFrames(d, lastN) {
    if (!ledEcho(d)) return { frames: [], lastN: null };
    var cur = { n: d.n, p: d.panel, s: d.panel_state };
    var rec = (d.recent || []).filter(function (r) { return r && r.p && r.n !== null; });
    if (!rec.length || rec[rec.length - 1].n !== d.n) rec = rec.concat([cur]);
    var fresh = lastN === null || lastN === undefined || d.n === null || d.n < lastN
      ? [cur] : rec.filter(function (r) { return r.n > lastN; });
    return { frames: fresh.map(function (r) {
               return { n: r.n, leds: r.p.map(cssColour), states: r.s || [] }; }),
             lastN: d.n };
  }

  function create(o) {
    var on = false, running = false, frame = null, queue = [], lastN = null;

    function off() {
      queue = [];
      lastN = null;
      if (frame) { frame = null; o.paint(null); }
    }

    function step() {
      if (!on || document.hidden || !o.url) { running = false; off(); return; }
      var ctl = root.AbortController ? new root.AbortController() : null;
      var guard = ctl ? setTimeout(function () { ctl.abort(); }, o.timeoutMs) : null;
      fetch(o.url, { cache: "no-store", signal: ctl ? ctl.signal : undefined })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function (d) {
          clearTimeout(guard);
          var got = ledFrames(d, lastN);
          if (got.lastN === null) { on = false; off(); return; }
          lastN = got.lastN;
          queue = queue.concat(got.frames).slice(-o.max);
          if (queue.length) frame = queue.shift();   // one line per poll: each one seen
        })
        .catch(function () { clearTimeout(guard); on = false; off(); })
        .then(function () { o.paint(frame); setTimeout(step, o.pollMs); });
    }

    return {
      want: function (v) {
        on = !!v;
        if (on && !running) { running = true; step(); }
      },
      frame: function () { return frame; }
    };
  }

  var api = { FULL: FULL, DARK: DARK, cssColour: cssColour, ledEcho: ledEcho,
              ledFrames: ledFrames, create: create };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.LedEcho = api;
})(this);
