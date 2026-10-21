/* clock.js -- UK wall clock (HH:MM:SS, Europe/London, BST aware) at the top
 * right of the live stroke panel, for starting and stopping a toll on the
 * minute, quarter or half minute.  Uses the browser clock (the kiosk runs on
 * the Pi itself, chrony-synced).  Each tick is a setTimeout aimed just past
 * the next whole second, never a drifting setInterval; a tick only rewrites
 * a few text nodes and class names.  Included inline by
 * events/live_panel.html; the pure helpers are exported for node tests. */
(function () {
  "use strict";
  var MS_PER_S = 1000;
  var S_PER_MIN = 60;
  var QUARTER_S = 15;                     // marks at :00 :15 :30 :45
  var QUARTERS = S_PER_MIN / QUARTER_S;   // segments in the indicator
  var HOURS_PER_DAY = 24;
  var TICK_MARGIN_MS = 15;                // land just after the boundary
  var LEAD_IN_S = 3;                      // countdown turns bright this close
  var LOCALE = "en-GB";
  var DECIMAL = 10;

  function pad2(n) { return (n < DECIMAL ? "0" : "") + n; }

  function hms(h, m, s) { return pad2(h % HOURS_PER_DAY) + ":" + pad2(m) + ":" + pad2(s); }

  /* ms from nowMs to just after the next whole second */
  function delayToNextSecond(nowMs) {
    return MS_PER_S - (nowMs % MS_PER_S) + TICK_MARGIN_MS;
  }

  /* where second-of-minute sec sits among the quarter-minute marks */
  function quarter(sec) {
    var into = sec % QUARTER_S;
    var start = sec - into;
    return {
      index: start / QUARTER_S,                     // 0..3: current quarter
      toNext: QUARTER_S - into,                     // s to the next mark
      next: (start + QUARTER_S) % S_PER_MIN,        // its second: 15 30 45 0
      onMark: into === 0,
      onMinute: sec === 0
    };
  }

  function makeFormatter(tz) {
    try {
      var f = new Intl.DateTimeFormat(LOCALE, {
        timeZone: tz, hourCycle: "h23", hour: "2-digit", minute: "2-digit",
        second: "2-digit", timeZoneName: "short"
      });
      if (typeof f.formatToParts === "function") return f;
    } catch (err) { /* unknown zone: fall back to the Pi's local time */ }
    return null;
  }

  /* {h, m, s, zone} of date in the formatter's zone (local time without one) */
  function partsOf(fmt, date) {
    if (!fmt) return { h: date.getHours(), m: date.getMinutes(), s: date.getSeconds(), zone: "" };
    var out = { h: 0, m: 0, s: 0, zone: "" };
    fmt.formatToParts(date).forEach(function (p) {
      if (p.type === "hour") out.h = parseInt(p.value, DECIMAL);
      else if (p.type === "minute") out.m = parseInt(p.value, DECIMAL);
      else if (p.type === "second") out.s = parseInt(p.value, DECIMAL);
      else if (p.type === "timeZoneName") out.zone = p.value;
    });
    return out;
  }

  function nextLabel(q) {
    return q.next === 0 ? ":00" : ":" + pad2(q.next);
  }

  var api = { pad2: pad2, hms: hms, delayToNextSecond: delayToNextSecond,
              quarter: quarter, makeFormatter: makeFormatter, partsOf: partsOf,
              nextLabel: nextLabel, QUARTER_S: QUARTER_S, QUARTERS: QUARTERS,
              TICK_MARGIN_MS: TICK_MARGIN_MS, LEAD_IN_S: LEAD_IN_S };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }

  var box = document.getElementById("live-clock");
  if (!box) return;
  var fmt = makeFormatter(box.dataset.tz);
  var elHms = document.getElementById("clock-hms");
  var elZone = document.getElementById("clock-zone");
  var elNext = document.getElementById("clock-next");
  var segs = [];                              // one per quarter minute
  var segBox = document.getElementById("clock-segs");
  for (var k = 0; k < QUARTERS; k++) {
    segs.push(segBox.appendChild(document.createElement("span")));
  }
  var shown = { hms: "", zone: null, next: "", cls: null, seg: -1 };

  function set(node, key, text) {             // touch the DOM only on change
    if (shown[key] !== text) { node.textContent = text; shown[key] = text; }
  }

  function render() {
    var t = partsOf(fmt, new Date());
    var q = quarter(t.s);
    set(elHms, "hms", hms(t.h, t.m, t.s));
    set(elZone, "zone", t.zone);
    set(elNext, "next", q.onMark ? "now " + (q.onMinute ? ":00" : ":" + pad2(t.s))
                                 : nextLabel(q) + " in " + q.toNext + " s");
    var cls = q.onMinute ? "mark minute" : q.onMark ? "mark" :
              q.toNext <= LEAD_IN_S ? "soon" : "";
    if (shown.cls !== cls) { box.className = cls; shown.cls = cls; }
    if (shown.seg !== q.index) {
      for (var i = 0; i < segs.length; i++) {
        segs[i].className = "clock-seg" + (i < q.index ? " done" : i === q.index ? " now" : "");
      }
      shown.seg = q.index;
    }
  }

  function tick() {
    render();
    setTimeout(tick, delayToNextSecond(Date.now()));
  }

  tick();
})();
