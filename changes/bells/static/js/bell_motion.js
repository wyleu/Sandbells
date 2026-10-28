/* bell_motion.js -- a small diagonal movement (bell_motion.css) of an element each time
 * a stroke or trigger event arrives from the Pico, so a ringing bell shows quietly.
 *
 *   var move = BellMotion.create(document.getElementById("bell-circle"));
 *   sock.onmessage = function (ev) { move(JSON.parse(ev.data)); };
 *
 * What counts: a sand.event/v1 "stroke" frame (a real stroke, and a trigger plug test
 * stroke, which is a stroke with body {ch, test: true, src: "trigger"}).  Heartbeats
 * (sand.panel/v1), link and channel events do not move anything.
 * Restart: the element gets bell-motion-0 or bell-motion-1, alternating, so an event
 * during the movement starts it again at once. */
(function (root) {
  "use strict";

  var PANEL = "sand.panel/v1";

  function isStrokeOrTrigger(m) {
    if (!m || m.schema === PANEL) return false;
    return m.type === "stroke" || (m.body || m).src === "trigger";
  }

  function create(el) {
    var n = 0;
    return function (m) {
      if (!el || !isStrokeOrTrigger(m)) return;
      el.classList.remove("bell-motion-" + n);
      n = 1 - n;
      el.classList.add("bell-motion-" + n);
    };
  }

  var api = { create: create, isStrokeOrTrigger: isStrokeOrTrigger };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  root.BellMotion = api;
})(typeof window !== "undefined" ? window : this);
