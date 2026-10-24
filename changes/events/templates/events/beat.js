/* beat.js -- where does this stroke fall against the current beat?
 *
 * Strokes of one bell (or trigger plug) alternate handstroke and backstroke,
 * and the gap after a handstroke is not the gap after a backstroke, so the
 * beat is kept as two series: the gaps ending on odd strokes and the gaps
 * ending on even strokes of the current run.  The beat for a new gap is the
 * median of the last WINDOW gaps of its own series (or of both pooled while
 * its own series is short).  A gap longer than the ring gap arrives as null
 * and starts a new run.
 *
 * observe(key, gapMs) -> null when there is no beat yet, otherwise
 *   { pos, beat }   pos 0..1: 0.5 is on the beat, left early, right late,
 *                   the ends are SPAN (50 %) of a beat out or more.
 * Included inline by events/live_list.js's page (live_panel.html); the
 * helpers are exported for node tests. */
(function () {
  "use strict";
  var WINDOW = 6;           // gaps kept per series
  var OWN_MIN = 2;          // gaps needed before a series stands alone
  var SPAN = 0.5;           // fraction of a beat that fills half the width
  var CENTRE = 0.5;

  function median(a) {
    var s = a.slice().sort(function (x, y) { return x - y; });
    var m = s.length >> 1;
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }

  function createBeat() {
    var runs = {};          // key -> { n, series: [[], []] }

    function observe(key, gapMs) {
      if (gapMs === null || gapMs === undefined || !(gapMs > 0)) {
        delete runs[key];
        return null;
      }
      var r = runs[key] || (runs[key] = { n: 0, series: [[], []] });
      var own = r.series[r.n % 2];
      var pool = r.series[0].concat(r.series[1]);
      var base = own.length >= OWN_MIN ? median(own)
               : pool.length ? median(pool) : null;
      own.push(gapMs);
      if (own.length > WINDOW) own.shift();
      r.n += 1;
      if (base === null) return null;
      return { pos: clamp01(CENTRE + (gapMs - base) / base * CENTRE / SPAN), beat: base };
    }

    return { observe: observe };
  }

  var api = { createBeat: createBeat, median: median, WINDOW: WINDOW, SPAN: SPAN };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  window.Beat = api;
})();
