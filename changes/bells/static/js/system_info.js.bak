// static/js/system_info.js
document.addEventListener('DOMContentLoaded', function() {
  const systemInfo = [
    { label: "Memory:", value: "Calculating..." },
    { label: "DEBUG:", value: "{{ DEBUG|yesno:'True,False' }}" },
    { label: "Git Branch:", value: "{{ git_branch|default:'unknown' }}" },
    { label: "Arch:", value: "{{ arch|default:'unknown' }}" },
    { label: "Pi Model:", value: "{{ pi_model|default:'unknown' }}" },
    { label: "IP:", value: "{{ IPAddr|default:'unknown' }}" },
    { label: "Hostname:", value: "{{ hostname|default:'unknown' }}" },
  ];

  const infoGroup = document.getElementById("posinfo");
  if (!infoGroup) return;

  systemInfo.forEach((item, index) => {
    const y = 990 + (index * 30);

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", "50");
    label.setAttribute("y", y);
    label.setAttribute("fill", "red");
    label.setAttribute("stroke", "black");
    label.setAttribute("font-size", "20");
    label.textContent = item.label;
    infoGroup.appendChild(label);

    const value = document.createElementNS("http://www.w3.org/2000/svg", "text");
    value.setAttribute("x", "170");
    value.setAttribute("y", y);
    value.setAttribute("fill", "red");
    value.setAttribute("stroke", "black");
    value.setAttribute("font-size", "19");
    value.textContent = item.value;
    infoGroup.appendChild(value);
  });
});
