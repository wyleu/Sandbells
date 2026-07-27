// static/js/system_info.js
// Status overlay under the clock + live screen / iframe widths
// Polls /api/system-status/ so Network (and the rest) tracks hot-plug changes.
// "Run" is a seconds counter (not wall clock) so you can see the API path is alive.

document.addEventListener('DOMContentLoaded', function () {
  const infoGroup = document.getElementById("posinfo");
  if (!infoGroup) return;

  const POLL_MS = 2000;
  let pollCount = 0;

  function addRow(label, value, index) {
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
    val.textContent = value;
    infoGroup.appendChild(val);
  }

  function clearRows() {
    while (infoGroup.firstChild) {
      infoGroup.removeChild(infoGroup.firstChild);
    }
  }

  function render(d, screenW, screenH, bodyW, bodyH, iframeW, iframeH) {
    clearRows();

    const rows = [
      ["— Browser —", ""],
      ["Screen:",   `${screenW} × ${screenH}`],
      ["Body:",     `${bodyW}×${bodyH}`],
      ["Iframe:",   `${iframeW} × ${iframeH}`],

      ["— Network —", ""],
      ["WiFi:",  `${d.wifi_state || "—"}${d.wifi_ssid ? " (" + d.wifi_ssid + ")" : ""}${d.wifi_ip ? " " + d.wifi_ip : ""}`],
      ["Wired:", `${d.wired_state || "—"}${d.wired_cidr ? " " + d.wired_cidr : ""}${d.wired_method ? " (" + d.wired_method + ")" : ""}`],
      ["IPs:",   d.ip_list || d.ip || "—"],
      ["Addr:",  d.using_fallback ? "fallback" : (d.wired_method || d.wifi_method || "—")],
      ["Expect:", d.fallback_ip ? `${d.fallback_ip}/${d.fallback_prefix || 24}` : "—"],

      ["— Server —", ""],
      ["Host:",     d.hostname_local || (d.hostname + ".local")],
      ["Git:",      `${d.git_branch} (${d.git_hash})`],
      ["Nginx:",    d.nginx],
      ["Gunicorn:", d.gunicorn],
      ["Kiosk:",    d.kiosk],

      ["— Hardware —", ""],
      ["Pi:",       (d.pi_model || "").replace("Raspberry Pi ", "Pi ")],
      ["Arch:",     d.arch],
      ["Mem:",      d.memory],
      ["Temp:",     d.temp || "—"],
      ["Fan:",      d.fan || "—"],

      ["— Status —", ""],
      ["Run:",      `${d._run_s || 0}s`],

      ["— Time —", ""],
      ["NTP:",      d.time_label || "NO LOCK"],
    ];

    rows.forEach(([lab, val], i) => addRow(lab, val, i));
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
        clearRows();
        addRow("Status:", "unavailable", 0);
        addRow("Run:", `${pollCount * (POLL_MS / 1000)}s`, 1);
        addRow("Screen:", `${screenW} × ${screenH}`, 2);
      });
  }

  refresh();
  setInterval(refresh, POLL_MS);
  window.addEventListener("resize", refresh);
});
