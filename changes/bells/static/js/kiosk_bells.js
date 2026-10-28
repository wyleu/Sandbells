(function () {
  var HOST = null;
  // The small diagonal movement (bell_motion.js) is driven by Sandbells' own event feed
  // (bell_feed.js polling /events/api/since/), not by this WebSocket.
  // This WebSocket is kept only for the older {bell, u, amp} tape messages -> BellBand.setTape;
  // nothing the current sandswing sends is such a message, and the events feed does not carry them.
  var KIOSK_WS = "ws://192.168.0.198/ws";  // sandtest rig; the sandswing concentrator is 192.168.0.81
  // var KIOSK_WS = "ws://192.168.0.154/ws";  // sandsense ticks

  function startFeed(el) {
    var d = el.dataset;              // set by bells/home.html from events.constants
    if (!d.feedUrl || !window.BellFeed || !window.BellMotion) return;
    window.BellFeed.create({
      url: d.feedUrl,
      pollMs: +d.feedPollMs,         // the farm page's live list poll (LIVE_POLL_MS)
      limit: +d.feedLimit,           // events per answer (LIVE_LIMIT_DEFAULT)
      timeoutMs: +d.feedTimeoutMs,   // LIVE_FETCH_TIMEOUT_MS
      accept: window.BellMotion.isStrokeOrTrigger,
      move: window.BellMotion.create(el),
      rd: window.ReconnectDelay.create()   // reconnect_delay.js: the delay after a failed poll
    }).start();
  }

  function sizeAndDraw() {
    var el = document.getElementById("bell-circle");
    if (!el || !window.BellBand) return;
    HOST = el;
    startFeed(el);
    BellBand.draw(el, {
      width: 250,
      height: 250,
      bells: [1, 2, 3, 4, 5, 6, 7, 8],
      onPadClick: function (bell) {
        BellBand.settleDemo(el, bell);
      }
    });
  }

  function handleMsg(raw) {
    var m;
    try { m = JSON.parse(raw); } catch (e) { return; }
    if (!m || !HOST || !window.BellBand) return;
    var kind = m.type || (m.bell != null ? "bell" : (m.tick != null ? "tick" : ""));
    if (kind === "bell") {
      BellBand.setTape(HOST, m.bell, m.u, m.amp != null ? m.amp : 1);
    }
    // if (kind === "tick") { /* clock pulse later */ }
  }

  var rd = window.ReconnectDelay.create();      // reconnect_delay.js: 1, 2, 4, 8, 15 s, jittered

  function connectFarmWs() {
    var ws;
    try { ws = new WebSocket(KIOSK_WS); }
    catch (e) { console.log("WS construct", e); return; }
    ws.onopen = function () { rd.opened(); console.log("farm WS open", KIOSK_WS); };
    ws.onmessage = function (ev) { handleMsg(ev.data); };
    ws.onclose = function () { setTimeout(connectFarmWs, rd.closed()); };
    ws.onerror = function () { try { ws.close(); } catch (e2) {} };
  }

  window.addEventListener("load", function () {
    setTimeout(function () {
      sizeAndDraw();
      connectFarmWs();
    }, 150);
  });
})();
