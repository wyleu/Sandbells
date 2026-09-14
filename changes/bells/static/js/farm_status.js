/**
 * farm_status.js — one device page, one poll (optional one WS).
 * Renders sand.status/v1 sections into the full viewport.
 * Items with "color" draw a circular lamp; WS ticks flip Encoder LEDs.
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
    var interval = cfg.interval || 5000;
    if (interval < 3000) interval = 3000;
    if (interval > 15000) interval = 15000;
    var url = statusFetchUrl(cfg);
    var timer = null;

    function tick() {
      if (document.visibilityState === "hidden") return;
      fetch(url, { cache: "no-store" })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (data) {
          if (data && data.error) throw new Error(data.error);
          render(data);
        })
        .catch(function (e) {
          renderError("Offline: " + e);
        });
    }

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

  function startWs(cfg) {
    if (!cfg.wsUrl) return null;
    var ws = null;
    var delay = 2000;

    function connect() {
      if (document.visibilityState === "hidden") return;
      try {
        if (ws) ws.close();
      } catch (e) {}
      ws = new WebSocket(cfg.wsUrl);
      ws.onmessage = function () {
        flipLedSwatch();
      };
      ws.onclose = function () {
        if (document.visibilityState === "hidden") return;
        setTimeout(connect, delay);
        delay = Math.min(delay * 1.5, 15000);
      };
    }

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && ws) {
        try {
          ws.close();
        } catch (e) {}
        ws = null;
      } else if (document.visibilityState === "visible") {
        delay = 2000;
        connect();
      }
    });
    connect();
    return ws;
  }

  window.FarmStatus = {
    start: function (cfg) {
      cfg = cfg || {};
      startPoll(cfg);
      startWs(cfg);
    },
  };
})();

