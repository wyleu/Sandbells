// static/js/system_info.js
// Status overlay under the clock + live screen / iframe widths
// Polls /api/system-status/ so Network (and the rest) tracks hot-plug changes.
// "Run" is a seconds counter (not wall clock) so you can see the API path is alive.
//
// Optimised for luakit / Pi 3: create the SVG <text> nodes once, then only
// update textContent on subsequent polls (no clear + rebuild).

document.addEventListener('DOMContentLoaded', function () {
  const infoGroup = document.getElementById("posinfo");
  if (!infoGroup) return;

  const POLL_MS = 2000;
  let pollCount = 0;
  let valueEls = null;   // array of the value <text> elements

  // Fixed list of labels (same order as before)
  const LABELS = [
    "— Browser —",
    "Screen:",
    "Body:",
    "Iframe:",
    "— Network —",
    "WiFi:",
    "Wired:",
    "IPs:",
    "Addr:",
    "Expect:",
    "— Server —",
    "Host:",
    "Git:",
    "Nginx:",
    "Gunicorn:",
    "Kiosk:",
    "— Hardware —",
    "Pi:",
    "Arch:",
    "Mem:",
    "Temp:",
    "Fan:",
    "— Status —",
    "Run:",
    "— Time —",
    "NTP:",
  ];

  function createRows() {
    valueEls = [];
    LABELS.forEach((label, index) => {
      const y = 620 + (index * 18);

      const lab = document.createElementNS("http://www.w3.org/2000/svg", "text");
      lab.setAttribute("x", "18");
      lab.setAttribute("y", y);
      lab.setAttribute("fill", "red");
      lab.setAttribute("stroke", "black");
      lab.setAttribute("font-size", "16");
      lab.textContent = label;
      infoGroup.appendChild(lab);

      const val = document.createElementNS("http://www.w3.org/2000/svg", "text");
      val.setAttribute("x", "100");
      val.setAttribute("y", y);
      val.setAttribute("fill", "red");
      val.setAttribute("stroke", "black");
      val.setAttribute("font-size", "15");
      val.textContent = "—";
      infoGroup.appendChild(val);

      valueEls.push(val);
    });
  }

  function updateValues(values) {
    if (!valueEls) return;
    for (let i = 0; i < valueEls.length; i++) {
      valueEls[i].textContent = values[i] != null ? values[i] : "—";
    }
  }

  function render(d, screenW, screenH, bodyW, bodyH, iframeW, iframeH) {
    const values = [
      "",                                          // — Browser —
      `${screenW} × ${screenH}`,
      `${bodyW}×${bodyH}`,
      `${iframeW} × ${iframeH}`,
      "",                                          // — Network —
      `${d.wifi_state || "—"}${d.wifi_ssid ? " (" + d.wifi_ssid + ")" : ""}${d.wifi_ip ? " " + d.wifi_ip : ""}`,
      `${d.wired_state || "—"}${d.wired_cidr ? " " + d.wired_cidr : ""}${d.wired_method ? " (" + d.wired_method + ")" : ""}`,
      d.ip_list || d.ip || "—",
      d.using_fallback ? "fallback" : (d.wired_method || d.wifi_method || "—"),
      d.fallback_ip ? `${d.fallback_ip}/${d.fallback_prefix || 24}` : "—",
      "",                                          // — Server —
      d.hostname_local || (d.hostname + ".local"),
      `${d.git_branch} (${d.git_hash})`,
      d.nginx,
      d.gunicorn,
      d.kiosk,
      "",                                          // — Hardware —
      (d.pi_model || "").replace("Raspberry Pi ", "Pi "),
      d.arch,
      d.memory,
      d.temp || "—",
      d.fan || "—",
      "",                                          // — Status —
      `${d._run_s || 0}s`,
      "",                                          // — Time —
      d.time_label || "NO LOCK",
    ];
    updateValues(values);
  }

  function refresh() {
    const screenW = window.innerWidth || document.documentElement.clientWidth;
    const screenH = window.innerHeight || document.documentElement.clientHeight;
    const bodyW = document.body ? document.body.clientWidth : "—";
    const bodyH = document.body ? document.body.clientHeight : "—";
    const iframe = document.getElementById("ishow");
    let iframeW = "—", iframeH = "—";
    if (iframe) {
      iframeW = iframe.getAttribute("width") || iframe.clientWidth || "—";
      iframeH = iframe.getAttribute("height") || iframe.clientHeight || "—";
    }

    fetch("/api/system-status/")
      .then(r => r.json())
      .then(d => {
        pollCount += 1;
        d._run_s = pollCount * (POLL_MS / 1000);
        render(d, screenW, screenH, bodyW, bodyH, iframeW, iframeH);
      })
      .catch(() => {
        updateValues([
          "", "unavailable", `${pollCount * (POLL_MS / 1000)}s`,
          `${screenW} × ${screenH}`, "", "", "", "", "", "", "", "", "", "", "", "",
          "", "", "", "", "", "", "", "", "", ""
        ]);
      });
  }

  // Create the nodes once, then start polling
  createRows();
  refresh();
  setInterval(refresh, POLL_MS);
  window.addEventListener("resize", refresh);
});
