(function () {
  var HOST = null;
  var WS_PATH = "/ws/bells/";

  function sizeAndDraw() {
    var el = document.getElementById("bell-circle");
    if (!el || !window.BellBand) return;
    HOST = el;
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
    if (!HOST || !m || m.bell == null) return;
    if (m.u != null) {
      BellBand.setTape(HOST, m.bell, m.u, m.amp);
      return;
    }
    if (m.pose) BellBand.setPose(HOST, m.bell, m.pose, m);
  }

  function connectWs() {
    var proto = location.protocol === "https:" ? "wss:" : "ws:";
    var url = proto + "//" + location.host + WS_PATH;
    var ws;
    try { ws = new WebSocket(url); } catch (e) { return; }
    ws.onmessage = function (ev) { handleMsg(ev.data); };
    ws.onclose = function () { setTimeout(connectWs, 3000); };
  }

  window.addEventListener("load", function () {
    setTimeout(function () {
      sizeAndDraw();
      connectWs();
    }, 150);
  });
})();
