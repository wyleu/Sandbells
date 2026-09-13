/**
 * farm_status.js — one device page, one poll (optional one WS).
 * Renders sand.status/v1 sections into the full viewport.
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
    $("farm-ident") && ($("farm-ident").textContent =
      (doc.family || "") + " · " + (doc.name || doc.id || ""));
    $("farm-summary") && ($("farm-summary").textContent = doc.summary || "");
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
        dd.textContent = it.value || "—";
        if (it.level) dd.className = "val-" + it.level;
        if (it.hint) dd.title = it.hint;
        dl.appendChild(dt);
        dl.appendChild(dd);
      });
      box.appendChild(dl);
      main.appendChild(box);
    });
  }

  function renderError(msg) {
    var main = $("farm-main");
    if (main) main.innerHTML = "<p id='farm-wait'>" + msg + "</p>";
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

  function startWs(cfg) {
    if (!cfg.wsUrl) return null;
    var ws = null;
    var delay = 2000;

    function connect() {
      if (document.visibilityState === "hidden") return;
      try { if (ws) ws.close(); } catch (e) {}
      ws = new WebSocket(cfg.wsUrl);
      ws.onmessage = function () {
        /* live tick only while this page is open; next HTTP poll refreshes rows */
      };
      ws.onclose = function () {
        if (document.visibilityState === "hidden") return;
        setTimeout(connect, delay);
        delay = Math.min(delay * 1.5, 15000);
      };
    }

    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden" && ws) {
        try { ws.close(); } catch (e) {}
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
