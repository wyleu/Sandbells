/* bell_motion.js -- a small diagonal movement (bell_motion.css) of the ONE bell that struck,
 * on the home page's bell circle (bell_band.js), each time a stroke or trigger event with a
 * bell number arrives from the event feed (bell_feed.js).  The rest of the circle stays still.
 *
 *   var move = BellMotion.create(document.getElementById("bell-circle"), { ms: 350, px: 4 });
 *   move(event);                       // an event from /events/api/since/
 *
 * Which bell: the event's "bell" field, which /events/api/since/ fills in from the event's
 * channel (body.ch) through the channel map (events/mapping.py).  The element moved is that
 * bell's inner group, .bell-pad[data-bell="N"] .bell-quiver (the pad's own transform places
 * it on the circle, so it is not moved itself).
 * No bell number (a channel with no mapping, or an older {ch, test, src} frame with no bell),
 * or a bell not drawn on the page: nothing moves at all, rather than a guessed bell or the
 * whole circle.  isBellStroke() refuses such an event, so the feed does not queue it.
 * What counts: a sand.event/v1 "stroke" (a real stroke, and a trigger plug test stroke,
 * body {ch, test: true, src: "trigger"}).  Heartbeats (sand.panel/v1), link and channel
 * events do not move anything.
 * Size and length: { ms, px } (from data-quiver-ms / data-quiver-px on #bell-circle, i.e.
 * events.constants BELL_QUIVER_MS / BELL_QUIVER_PX) become --bell-motion-ms / --bell-motion-px
 * on the circle, which bell_motion.css uses.
 * Restart: each bell's group gets bell-motion-0 or bell-motion-1, alternating per bell, so
 * an event during its movement starts it again at once. */
(function (root) {
  "use strict";

  var PANEL = "sand.panel/v1";

  function isStrokeOrTrigger(m) {
    if (!m || m.schema === PANEL) return false;
    return m.type === "stroke" || (m.body || m).src === "trigger";
  }

  // the bell number of an event, or null (unmapped channel, or no such field)
  function bellOf(m) {
    var b = m ? m.bell : null;
    return typeof b === "number" && b === Math.floor(b) && b > 0 ? b : null;
  }

  function isBellStroke(m) {
    return isStrokeOrTrigger(m) && bellOf(m) !== null;
  }

  function create(host, look) {
    var turn = {};                       // bell -> 0 or 1, its last animation name
    if (host && host.style && look) {
      host.style.setProperty("--bell-motion-ms", look.ms + "ms");
      host.style.setProperty("--bell-motion-px", look.px + "px");
    }
    return function (m) {
      if (!host || !isBellStroke(m)) return;
      var bell = bellOf(m);
      var el = host.querySelector('.bell-pad[data-bell="' + bell + '"] .bell-quiver');
      if (!el) return;
      var n = turn[bell] || 0;
      el.classList.remove("bell-motion-" + n);
      n = 1 - n;
      turn[bell] = n;
      el.classList.add("bell-motion-" + n);
    };
  }

  var api = { create: create, isStrokeOrTrigger: isStrokeOrTrigger, isBellStroke: isBellStroke,
              bellOf: bellOf };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  root.BellMotion = api;
})(typeof window !== "undefined" ? window : this);
