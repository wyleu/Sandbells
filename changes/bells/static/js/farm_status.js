/**
 * farm_status.js
 * Shared logic for the Farm Status detail page.
 * Host view  → polls /api/system-status/
 * Sandsense  → WebSocket for live ticks + light poll for status fields
 */
(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function browserSizes() {
    var iframe = document.querySelector("iframe");
    return {
      screen: window.screen.width + "×" + window.screen.height,
      window: window.innerWidth + "×" + window.innerHeight,
      body: document.body
        ? document.body.clientWidth + "×" + document.body.clientHeight
        : "—",
      iframe: iframe
        ? iframe.clientWidth + "×" + iframe.clientHeight
        : "n/a (no iframe on farm status)",
    };
  }

  // ---------- host view ----------
  function startHostPoll(intervalMs) {
    var el = $("st-json");
    if (!el) return;

    function tick() {
      fetch("/api/system-status/", { cache: "no-store" })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          data.browser = browserSizes();
          el.textContent = JSON.stringify(data, null, 2);
        })
        .catch(function (e) {
          el.textContent = "Error: " + e;
        });
    }
    tick();
    setInterval(tick, intervalMs || 5000);
  }

  // ---------- sandsense view ----------
  function startSandsense(cfg) {
    var statusUrl = cfg.statusUrl || "";
    var wsUrl = cfg.wsUrl || "";          // e.g. "ws://sandsense-tower.local/ws"
    var pollInterval = cfg.interval || 3000;
    var lastSeq = null;
    var red = false;
    var ws = null;
    var reconnectDelay = 2000;

    function pulseOrb() {
      var el = $("ss-orb");
      if (!el) return;
      red = !red;
      el.className = "orb " + (red ? "orb-red" : "orb-green") + " orb-flash";
      setTimeout(function () {
        el.classList.remove("orb-flash");
      }, 150);
    }

    // --- WebSocket path (primary for the orb) ---
    function connectWs() {
      if (!wsUrl) {
        console.warn("No wsUrl – orb will only update from poll");
        return;
      }
      if (ws) {
        try { ws.close(); } catch (e) {}
      }

      ws = new WebSocket(wsUrl);

      ws.onopen = function () {
        console.log("Tick WebSocket connected");
        reconnectDelay = 2000;
      };

      ws.onmessage = function (event) {
        try {
          var data = JSON.parse(event.data);
          // every message is a tick → pulse immediately
          pulseOrb();
          // optional: keep lastSeq in sync so poll doesn’t double-pulse
          if (typeof data.tick === "number") {
            lastSeq = data.tick;
          }
        } catch (e) {
          console.warn("Bad WS payload", event.data);
        }
      };

      ws.onclose = function () {
        console.log("Tick WS closed – reconnecting in", reconnectDelay, "ms");
        setTimeout(connectWs, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.5, 15000);
      };

      ws.onerror = function (err) {
        console.error("Tick WS error", err);
        ws.close();
      };
    }

    // --- light status poll (IP, temp, PLL, lines, etc.) ---
    function pollStatus() {
      if (!statusUrl) {
        $("ss-lines").textContent = "No status_url";
        return;
      }
      var url = "/api/farm/device-status/?url=" + encodeURIComponent(statusUrl);

      fetch(url, { cache: "no-store" })
        .then(function (r) {
          if (!r.ok) throw new Error("HTTP " + r.status);
          return r.json();
        })
        .then(function (d) {
          if (!d || d.error || d.lines === undefined) {
            $("ss-lines").textContent =
              (d && d.error ? "Proxy/device: " + d.error : "Bad payload") +
              "\n\n" + ($("ss-lines").textContent || "");
            return;
          }

          $("ss-ip").textContent   = d.ip || "—";
          $("ss-ssid").textContent = d.ssid || "—";
          $("ss-temp").textContent = d.temp_c != null ? d.temp_c + " °C" : "—";
          $("ss-pll").textContent  =
            (d.pll_enabled ? "ON" : "OFF") +
            " locked=" + !!d.pll_locked +
            " misses=" + (d.misses != null ? d.misses : "—");
          $("ss-ticks").textContent =
            (d.ticks_this_period != null ? d.ticks_this_period : "—") +
            " / " + (d.report_interval_s != null ? d.report_interval_s : "—") + "s";
          $("ss-adc").textContent  = d.adc_avg != null ? d.adc_avg : "—";
          $("ss-last").textContent = d.last_line || "—";
          $("ss-lines").textContent = (d.lines || []).join("\n");

          // only pulse from poll if we have *no* WebSocket
          if (!wsUrl) {
            var seq = d.tick_seq;
            if (typeof seq === "number") {
              if (lastSeq !== null && seq > lastSeq) {
                var n = Math.min(seq - lastSeq, 4);
                for (var i = 0; i < n; i++) pulseOrb();
              }
              lastSeq = seq;
            }
          }
        })
        .catch(function (e) {
          $("ss-lines").textContent =
            "Offline: " + e + "\n\n" + ($("ss-lines").textContent || "");
        });
    }

    // start both
    connectWs();
    pollStatus();
    setInterval(pollStatus, pollInterval);
  }

  // ---------- public entry point ----------
  window.FarmStatus = {
    start: function (cfg) {
      cfg = cfg || {};
      if (cfg.kind === "host") {
        startHostPoll(cfg.interval);
      } else if (cfg.family === "sandsense") {
        startSandsense(cfg);
      }
    },
  };
})();