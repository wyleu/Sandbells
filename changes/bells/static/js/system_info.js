// static/js/system_info.js
// Status overlay under the clock + live screen / iframe widths

document.addEventListener('DOMContentLoaded', function () {
  const infoGroup = document.getElementById("posinfo");
  if (!infoGroup) return;

  function addRow(label, value, index) {
    const y = 800 + (index * 22);

    const lab = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lab.setAttribute("x", "30");
    lab.setAttribute("y", y);
    lab.setAttribute("fill", "red");
    lab.setAttribute("stroke", "black");
    lab.setAttribute("font-size", "14");
    lab.textContent = label;
    infoGroup.appendChild(lab);

    const val = document.createElementNS("http://www.w3.org/2000/svg", "text");
    val.setAttribute("x", "95");
    val.setAttribute("y", y);
    val.setAttribute("fill", "red");
    val.setAttribute("stroke", "black");
    val.setAttribute("font-size", "13");
    val.textContent = value;
    infoGroup.appendChild(val);
  }

  function clearRows() {
    while (infoGroup.firstChild) {
      infoGroup.removeChild(infoGroup.firstChild);
    }
  }

  function render(d, screenW, screenH, iframeW, iframeH) {
    clearRows();
    const rows = [
      ["Screen:",   `${screenW} × ${screenH}`],
      ["Iframe:",   `${iframeW} × ${iframeH}`],
      ["Host:",     d.hostname],
      ["IP:",       d.ip],
      ["Git:",      `${d.git_branch} (${d.git_hash})`],
      ["Pi:",       d.pi_model.replace("Raspberry Pi ", "Pi ")],
      ["Arch:",     d.arch],
      ["Mem:",      d.memory],
      ["DEBUG:",    d.debug ? "True" : "False"],
      ["Nginx:",    d.nginx],
      ["Gcorn:",    d.gunicorn],
      ["Kiosk:",    d.kiosk],
    ];
    rows.forEach(([lab, val], i) => addRow(lab, val, i));
  }

  function refresh() {
    const screenW = window.innerWidth  || document.documentElement.clientWidth;
    const screenH = window.innerHeight || document.documentElement.clientHeight;

    const iframe = document.getElementById("ishow");
    let iframeW = "—", iframeH = "—";
    if (iframe) {
      iframeW = iframe.getAttribute("width")  || iframe.clientWidth  || "—";
      iframeH = iframe.getAttribute("height") || iframe.clientHeight || "—";
    }

    fetch("/api/system-status/")
      .then(r => r.json())
      .then(d => render(d, screenW, screenH, iframeW, iframeH))
      .catch(() => {
        clearRows();
        addRow("Status:", "unavailable", 0);
        addRow("Screen:", `${screenW} × ${screenH}`, 1);
      });
  }

  refresh();
  window.addEventListener("resize", refresh);
});
