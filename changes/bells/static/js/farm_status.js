/**
 * farm_status.js — one device page, one poll (optional one WS).
 * Renders sand.status/v1 sections into the full viewport.
 * Items with "color" draw a circular lamp; WS ticks flip Encoder LEDs.
 * A failed poll keeps the last good document and only marks the header stale.
 */
(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function setLevel(el, level) {
    if (!el) return;
    level = level || "unknown";
    el.className = "level level-" + level;
    el.textContent = level;
  }

  var CFG = {};          // the page's config, for button presses
  var pollNow = null;    // set by startPoll: fetch again now

  function csrfToken() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]*)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  /* An item's "actions" ([{id, label}]) become small buttons beside its value.
   * A press POSTs {device, key, action}; Sandbells decides who carries it out. */
  function actionButton(it, act) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "act";
    b.textContent = act.label || act.id;
    b.title = (it.label || it.key) + ": " + (act.label || act.id);
    b.addEventListener("click", function () {
      b.disabled = true;
      fetch("/api/farm/action/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ device: CFG.id || "", key: it.key, action: act.id }),
      })
        .then(function (r) { return r.json(); })
        .then(function (res) {
          b.textContent = res.ok ? "sent" : "failed";
          if (!res.ok) b.title = res.error || "";
        })
        .catch(function () { b.textContent = "failed"; })
        .then(function () {
          setTimeout(function () { if (pollNow) pollNow(); }, 2500);
        });
    });
    return b;
  }

  function render(doc) {
    var main = $("farm-main");
    if (!main) return;
    if ($("farm-ident")) {
      $("farm-ident").textContent =
        (doc.family || "") + " · " + (doc.name || doc.id || "");
    }
    if ($("farm-summary")) {
      $("farm-summary").textContent = doc.summary || "";
    }
    setLevel($("farm-level"), doc.level);

    var sections = doc.sections || [];
    if (!sections.length) {
      main.innerHTML = "<p id='farm-wait'>No sections in status document.</p>";
      return;
    }

    main.innerHTML = "";
    sections.forEach(function (sec) {
      var box = document.createElement("section");
      box.className = "farm-section";
      var h = document.createElement("h2");
      h.textContent = sec.title || sec.id || "";
      box.appendChild(h);
      var dl = document.createElement("dl");
      (sec.items || []).forEach(function (it) {
        var dt = document.createElement("dt");
        dt.textContent = it.label || it.key || "";
        var dd = document.createElement("dd");
        if (it.color) {
          var sw = document.createElement("span");
          sw.className = "swatch";
          sw.style.background = it.color;
          sw.setAttribute("data-key", it.key || "leds");
          sw.setAttribute("data-color", it.color);
          if (it.color_alt) {
            sw.setAttribute("data-color-alt", it.color_alt);
          }
          sw.setAttribute("data-now", "main");
          sw.title = it.value || "";
          dd.appendChild(sw);
        } else {
          dd.textContent = it.value || "—";
        }
        if (it.level) {
          dd.className = "val-" + it.level;
        }
        if (it.hint && !it.color) {
          dd.title = it.hint;
        }
        (it.actions || []).forEach(function (act) {
          dd.appendChild(document.createTextNode(" "));
          dd.appendChild(actionButton(it, act));
        });
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      box.appendChild(dl);
      main.appendChild(box);
    });
  }

  function renderError(msg) {
    var main = $("farm-main");
    if (main) {
      main.innerHTML = "<p id='farm-wait'></p>";
      main.firstChild.textContent = msg;
    }
    setLevel($("farm-level"), "error");
  }

  function statusFetchUrl(cfg) {
    if (cfg.statusUrl) {
      return "/api/farm/device-status/?url=" + encodeURIComponent(cfg.statusUrl);
    }
    return "/api/system-status/";
  }

  function startPoll(cfg) {
    var interval = cfg.interval || 15000;
    if (interval < 3000) interval = 3000;
    if (interval > 30000) interval = 30000;
    var url = statusFetchUrl(cfg);
    var timer = null;
    var lastDoc = null;

    function setStale(msg) {
      setLevel($("farm-level"), "warn");
      if ($("farm-summary")) {
        $("farm-summary").textContent = msg || "stale";
      }
    }

    function setHeld(doc) {
      setLevel($("farm-level"), doc.level || "ok");
      if ($("farm-summary")) {
        $("farm-summary").textContent = "Ringing (" + (doc.tower || doc.held) +
          "): status paused, showing the last full status";
      }
    }

    function tick() {
      if (document.visibilityState === "hidden") return;
      fetch(url, { cache: "no-store" })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (data) {
          if (data && data.error) throw new Error(data.error);
          if (data && data.held) {
            // the Pico is ringing (sandswing StatusGate): it answers with a
            // tiny held document so strokes have the link.  Not offline:
            // keep the last full status on screen and say why it is paused.
            if (lastDoc) {
              setHeld(data);
              return;
            }
            render(data);
            return;
          }
          lastDoc = data;
          render(data);
        })
        .catch(function (e) {
          if (lastDoc) {
            setStale("Offline: " + e.message);
            return;
          }
          renderError("Offline: " + e.message);
        });
    }

    pollNow = tick;
    tick();
    timer = setInterval(tick, interval);

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && timer) {
        clearInterval(timer);
        timer = null;
      } else if (document.visibilityState === "visible" && !timer) {
        tick();
        timer = setInterval(tick, interval);
      }
    });
  }

  function flipLedSwatch() {
    var sw = document.querySelector('.swatch[data-key="leds"]');
    if (!sw) return;
    var a = sw.getAttribute("data-color");
    var b = sw.getAttribute("data-color-alt");
    if (!a || !b) return;
    var useAlt = sw.getAttribute("data-now") !== "alt";
    sw.style.background = useAlt ? b : a;
    sw.setAttribute("data-now", useAlt ? "alt" : "main");
  }

  /* Link health: every HELLO_MS a small text frame, so the Pico can drop
   * this socket if the page (or Luakit) goes away without a close; and once
   * the Pico has sent a sand.panel/v1 heartbeat on this socket, SILENT_MS
   * with nothing from it means a dead link: close, and onclose reconnects. */
  var HELLO_MS = 5000;
  var SILENT_MS = 20000;
  var HELLO = '{"schema":"sand.hello/v1","type":"heartbeat","src":"sandbells-page"}';

  function startWs(cfg) {
    // wsUrls: every address of the device (home, tower); a socket that never
    // opens moves on to the next, and the one that worked is tried first.
    var urls = (cfg.wsUrls && cfg.wsUrls.length) ? cfg.wsUrls : (cfg.wsUrl ? [cfg.wsUrl] : []);
    if (!urls.length) return null;
    var which = 0;
    var ws = null;
    var rd = window.ReconnectDelay.create();     // reconnect_delay.js: 1, 2, 4, 8, 15 s, jittered
    var timer = null;

    function stopTimer() {
      if (timer) clearInterval(timer);
      timer = null;
    }

    function connect() {
      if (document.visibilityState === "hidden") return;
      try {
        if (ws) ws.close();
      } catch (e) {}
      stopTimer();
      var sock = new WebSocket(urls[which]);
      var lastRx = Date.now();
      var heardHb = false;
      var opened = false;
      ws = sock;
      sock.onopen = function () {
        opened = true;
        rd.opened();                       // the delay only resets after 30 s up
        timer = setInterval(function () {
          if (sock.readyState !== 1) return;
          try { sock.send(HELLO); } catch (e) {}
          if (heardHb && Date.now() - lastRx > SILENT_MS) {
            try { sock.close(); } catch (e) {}
          }
        }, HELLO_MS);
      };
      sock.onmessage = function (ev) {
        lastRx = Date.now();
        if (typeof ev.data === "string" && ev.data.indexOf("sand.panel/v1") >= 0) {
          heardHb = true;        // heartbeat: not a stroke, no LED flip
          return;
        }
        flipLedSwatch();
      };
      sock.onclose = function () {
        if (sock !== ws) return;           // an older socket we replaced
        stopTimer();
        if (document.visibilityState === "hidden") return;
        if (!opened && urls.length > 1) {   // never connected: try the next address
          which = (which + 1) % urls.length;
          setTimeout(connect, which ? 0 : rd.closed());
          return;
        }
        setTimeout(connect, rd.closed());
      };
    }

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && ws) {
        stopTimer();
        try {
          ws.close();
        } catch (e) {}
        ws = null;
      } else if (document.visibilityState === "visible") {
        rd.reset();
        connect();
      }
    });
    connect();
    return ws;
  }

  window.FarmStatus = {
    start: function (cfg) {
      cfg = cfg || {};
      CFG = cfg;
      startPoll(cfg);
      startWs(cfg);
    },
  };
})();
