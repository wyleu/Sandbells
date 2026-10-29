/* bell_feed.js -- tells the home page's bell display (bell_motion.js) about new stroke and
 * trigger events from Sandbells' own event feed, so the page does not need a WebSocket to
 * a Pico.  It polls the same endpoint the farm page's live list polls (events/live_list.js):
 *   GET /events/api/since/?type=&limit=N&after=<highest id seen>
 *
 *   BellFeed.create({
 *     url: "/events/api/since/", pollMs: 1000, limit: 50, timeoutMs: 4000,
 *     moveMs: 350, accept: BellMotion.isBellStroke, move: BellMotion.create(el, look),
 *     rd: ReconnectDelay.create(),
 *   }).start();
 *
 * What it does:
 *  - The first answer only learns the newest event id (limit=1), so the events already
 *    stored when the page opens do not play back.
 *  - Each later poll asks for ids above the highest one seen; an event for which accept()
 *    is true is handed to move() once.  Heartbeats are never stored; link, ingest and
 *    channel events, and strokes with no bell number, fail accept(), so they do nothing.
 *  - A burst (up to `limit` events in one answer) plays at most MAX_MOVES movements, one
 *    after another, moveMs apart (one movement's length, data-quiver-ms); the rest are dropped, so the work stays small.
 *  - A full answer (limit events) is followed at once by the next poll, to catch up.
 *  - A poll that fails or times out is ignored quietly and retried after the next delay
 *    of the shared ReconnectDelay schedule (1, 2, 4, 8, 15 s, jittered); the first good
 *    answer afterwards goes back to pollMs.
 *  - Hidden tab: no polling at all.  When it shows again the newest id is learnt afresh,
 *    so the events of the hidden time do not play back. */
(function (root) {
  "use strict";

  var MAX_MOVES = 3;      // at most this many movements per answer: 3 x moveMs (350 ms) is about one 1 s poll

  function create(o) {
    var env = o.env || root;
    var doc = env.document;
    var fetchFn = env.fetch ? env.fetch.bind(env) : null;
    var later = env.setTimeout.bind(env);
    var cancel = env.clearTimeout.bind(env);
    var rd = o.rd || null;

    var lastId = null;      // highest event id seen; null until the first answer
    var timer = null;       // the next poll
    var playTimer = null;   // the next queued movement
    var queue = [];         // events waiting to move, at most MAX_MOVES
    var down = false;       // the last poll failed
    var gen = 0;            // changes when the tab hides, so a late answer is dropped

    function hidden() { return !!doc && doc.visibilityState === "hidden"; }

    function playNext() {
      playTimer = null;
      if (!queue.length) return;
      o.move(queue.shift());
      if (queue.length) playTimer = later(playNext, o.moveMs);
    }

    function enqueue(events) {
      events.forEach(function (e) {
        if (queue.length >= MAX_MOVES || !o.accept(e)) return;
        queue.push(e);
      });
      if (queue.length && playTimer === null) playNext();
    }

    function pollUrl() {
      var q = o.url + "?type=";
      if (lastId === null) return q + "&limit=1";
      return q + "&limit=" + o.limit + "&after=" + lastId;
    }

    function schedule(ms) {
      if (timer !== null) cancel(timer);
      timer = later(poll, ms);
    }

    function answer(data, myGen) {
      if (myGen !== gen) return;
      if (down && rd) rd.opened();
      down = false;
      var events = data && Array.isArray(data.events) ? data.events : [];
      var first = lastId === null;
      if (data && typeof data.latest_id === "number") lastId = data.latest_id;
      else if (first) lastId = 0;                   // nothing stored yet
      if (!first) enqueue(events);
      schedule(!first && events.length >= o.limit ? 0 : o.pollMs);
    }

    function failed(myGen) {
      if (myGen !== gen) return;
      down = true;                                  // quiet: no message anywhere
      schedule(rd ? rd.closed() : o.pollMs);
    }

    function poll() {
      timer = null;
      if (hidden() || !fetchFn) return;
      var myGen = gen;
      var ctl = env.AbortController ? new env.AbortController() : null;
      var guard = ctl ? later(function () { ctl.abort(); }, o.timeoutMs) : null;
      var p;
      try {
        p = fetchFn(pollUrl(), { cache: "no-store", signal: ctl ? ctl.signal : undefined });
      } catch (e) {
        if (guard !== null) cancel(guard);
        failed(myGen);
        return;
      }
      p.then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }).then(function (data) {
        if (guard !== null) cancel(guard);
        answer(data, myGen);
      }, function () {
        if (guard !== null) cancel(guard);
        failed(myGen);
      });
    }

    function onVisibility() {
      if (hidden()) {
        gen += 1;                                   // ignore an answer still on its way
        if (timer !== null) cancel(timer);
        timer = null;
        queue.length = 0;
        lastId = null;                              // learn the newest id again on return
        down = false;
      } else if (timer === null) {
        poll();
      }
    }

    function start() {
      if (doc && doc.addEventListener) doc.addEventListener("visibilitychange", onVisibility);
      poll();
    }

    return { start: start, poll: poll, lastId: function () { return lastId; } };
  }

  var api = { create: create, MAX_MOVES: MAX_MOVES };
  if (typeof module === "object" && module.exports) { module.exports = api; return; }
  root.BellFeed = api;
})(typeof window !== "undefined" ? window : this);
