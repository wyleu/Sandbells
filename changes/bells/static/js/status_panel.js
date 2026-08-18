window.StatusPanel = {
  fillLocal: function (root) {
    // Move existing status JS here:
    // fetch("/…/timedatestatus/") → #st-time
    // or fill from a small JSON status endpoint you already have
    var host = document.getElementById("st-hostname");
    if (host) host.textContent = root.dataset.name || location.hostname;
    // …same endpoints as current status display…
  }
};