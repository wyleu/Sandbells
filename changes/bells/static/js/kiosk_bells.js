(function () {
  var HOST = null;
  var moveHost = null;             // bell_motion.js: a small diagonal movement per stroke or trigger
  var KIOSK_WS = "ws://192.168.0.198/ws";  // sandswing jabber
  // var KIOSK_WS = "ws://192.168.0.154/ws";  // sandsense ticks

  function sizeAndDraw() {
    var el = document.getElementById("bell-circle");
    if (!el || !window.BellBand) return;
    HOST = el;
    moveHost = window.BellMotion.create(el);
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
    moveHost(m);
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
