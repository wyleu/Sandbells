/* bell_motion.js -- on the home page's bell circle (bell_band.js), each stroke or trigger event
 * with a bell number (from the event feed, bell_feed.js) gives THAT bell the same clapper
 * movement as pressing its pad: kiosk_bells.js hands in its press function, strike(bell),
 * which is BellBand.settleDemo (the coloured clapper swings and dies away; visual only).
 * The bell itself, the other bells and the circle stay still.
 *
 *   var move = BellMotion.create(document.getElementById("bell-circle"), strike);
 *   move(event);                       // an event from /events/api/since/
 *
 * Which bell: the event's "bell" field, which /events/api/since/ fills in from the event's
 * channel (body.ch) through the channel map (events/mapping.py).
 * No bell number (a channel with no mapping, or an older {ch, test, src} frame with no bell),
 * or a bell not drawn on the page: nothing moves at all, rather than a guessed bell.
 * isBellStroke() refuses such an event, so the feed does not queue it.
 * What counts: a sand.event/v1 "stroke" (a real stroke, and a trigger plug test stroke,
 * body {ch, test: true, src: "trigger"}).  Heartbeats (sand.panel/v1), link and channel
 * events do not move anything. */
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

  function create(host, strike) {
    return function (m) {
      if (!host || !strike || !isBellStroke(m)) return;
      var bell = bellOf(m);
      if (!host.querySelector('.bell-pad[data-bell="' + bell + '"]')) return;   // not drawn here
      strike(bell);
    };
  }

  var api = { create: create, isStrokeOrTrigger: isStrokeOrTrigger, isBellStroke: isBellStroke,
              bellOf: bellOf };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  root.BellMotion = api;
})(typeof window !== "undefined" ? window : this);
