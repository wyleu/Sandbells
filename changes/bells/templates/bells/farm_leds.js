/* farm_leds.js -- the sandswing farm page's Panel section, live: the six
 * Panel swatches (data-key led1..led6, bells.status_schema.PANEL_KEY) take
 * the panel as the Pico paints it from /events/api/leds/ (led_echo.js, the
 * same fast poll and colours as the Strokes page strip).  Not live: the
 * heartbeat's colour farm_status.js drew (data-color).  farm_status.js
 * redraws #farm-main on every status poll; a MutationObserver puts the echo
 * back.  While the echo is off it is looked for every probeMs.  Included
 * inline by farm_status.html only when the view passed a config (the Pico
 * whose status comes over USB serial).  FarmLeds.start(cfg, LedEcho). */
(function (root) {
  "use strict";

  function paintInto(main, keys, frame) {
    keys.forEach(function (key, i) {
      var sw = main.querySelector('.swatch[data-key="' + key + '"]');
      if (!sw) return;
      var c = frame && frame.leds[i] ? frame.leds[i] : sw.getAttribute("data-color");
      if (sw.getAttribute("data-shown") !== c) {
        sw.style.background = c;
        sw.setAttribute("data-shown", c);
      }
      if (!sw.hasAttribute("data-hb-title")) sw.setAttribute("data-hb-title", sw.title || "");
      var t = frame ? frame.states[i] || "" : sw.getAttribute("data-hb-title");
      if (sw.title !== t) sw.title = t;
    });
  }

  function start(cfg, LE) {
    var main = document.getElementById("farm-main");
    if (!main || !cfg || !LE) return null;
    var echo = LE.create({ url: cfg.url, pollMs: cfg.pollMs, max: cfg.max,
                           timeoutMs: cfg.timeoutMs,
                           paint: function (f) { paintInto(main, cfg.keys, f); } });
    if (root.MutationObserver) {
      new root.MutationObserver(function () { paintInto(main, cfg.keys, echo.frame()); })
        .observe(main, { childList: true });
    }
    echo.want(true);
    setInterval(function () { echo.want(true); }, cfg.probeMs);
    return echo;
  }

  var api = { paintInto: paintInto, start: start };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.FarmLeds = api;
})(this);
