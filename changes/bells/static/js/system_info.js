// static/js/system_info.js - tighter layout for narrow SVG

document.addEventListener('DOMContentLoaded', function() {
  const infoGroup = document.getElementById("posinfo");
  if (!infoGroup) return;

  function addRow(label, value, index) {
    const y = 990 + (index * 26);   // tighter vertical spacing

    const lab = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lab.setAttribute("x", "40");
    lab.setAttribute("y", y);
    lab.setAttribute("fill", "red");
    lab.setAttribute("stroke", "black");
    lab.setAttribute("font-size", "17");
    lab.textContent = label;
    infoGroup.appendChild(lab);

    const val = document.createElementNS("http://www.w3.org/2000/svg", "text");
    val.setAttribute("x", "155");
    val.setAttribute("y", y);
    val.setAttribute("fill", "red");
    val.setAttribute("stroke", "black");
    val.setAttribute("font-size", "16");
    val.textContent = value;
    infoGroup.appendChild(val);
  }

  fetch("/api/system-status/")
    .then(r => r.json())
    .then(d => {
      const rows = [
        ["Host:", d.hostname],
        ["IP:", d.ip],
        ["Git:", `${d.git_branch} (${d.git_hash})`],
        ["Pi:", d.pi_model],
        ["Arch:", d.arch],
        ["Mem:", d.memory],
        ["DEBUG:", d.debug ? "True" : "False"],
        ["Nginx:", d.nginx],
        ["Gunicorn:", d.gunicorn],
        ["Kiosk:", d.kiosk],
      ];
      rows.forEach(([lab, val], i) => addRow(lab, val, i));
    })
    .catch(() => {
      addRow("Status:", "unavailable", 0);
    });
});
