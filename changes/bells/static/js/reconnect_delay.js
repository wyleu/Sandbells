/* reconnect_delay.js -- how long the display waits before it opens a WebSocket
 * again.  One place for every page that reconnects (farm_status.js, align.js,
 * kiosk_bells.js, tick-ws.js).
 *
 * Why: a Pico that is dropping us (a replay that cannot be sent, a send path in
 * backoff) used to be asked again after a fixed 2 s, and farm_status.js and
 * align.js reset their delay the moment a socket opened, so a connection that
 * lived a second and was dropped restarted the cycle at 2 s: a reconnect storm
 * on a device that needs quiet.  Here the delay grows 1, 2, 4, 8, 15 s (capped),
 * each with up to 30 % jitter off so several displays do not retry together,
 * and goes back to 1 s only after a connection has stayed up for 30 s.
 *
 *   var rd = ReconnectDelay.create();
 *   sock.onopen  = function () { rd.opened(); ... };
 *   sock.onclose = function () { setTimeout(connect, rd.closed()); };
 *   // page visible again, or the user asked: rd.reset();
 *
 * closed() is also the call for a socket that never opened (a 503 from the
 * Pico, or no route): the delay still grows.
 */
(function (root) {
  "use strict";

  var DEFAULTS = {
    baseMs: 1000,        // first delay
    factor: 2,           // each failure doubles it
    capMs: 15000,        // and it never goes above this
    jitter: 0.3,         // the delay is cut by a random 0..30 %
    stableMs: 30000,     // a connection up this long makes the next failure start again
  };

  function create(opts) {
    var o = {};
    var k;
    for (k in DEFAULTS) o[k] = DEFAULTS[k];
    for (k in (opts || {})) if (opts[k] !== undefined) o[k] = opts[k];
    var now = o.now || Date.now;
    var random = o.random || Math.random;
    var tries = 0;               // failures since the last stable connection
    var upAt = null;             // when the current connection opened

    return {
      opened: function () { upAt = now(); },
      closed: function () {
        if (upAt !== null && now() - upAt >= o.stableMs) tries = 0;
        upAt = null;
        var d = o.baseMs * Math.pow(o.factor, tries);
        if (d > o.capMs) d = o.capMs;
        tries += 1;
        return Math.round(d * (1 - o.jitter * random()));
      },
      reset: function () { tries = 0; upAt = null; },
      attempts: function () { return tries; },
    };
  }

  var api = { create: create, DEFAULTS: DEFAULTS };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  root.ReconnectDelay = api;
})(typeof window !== "undefined" ? window : this);
