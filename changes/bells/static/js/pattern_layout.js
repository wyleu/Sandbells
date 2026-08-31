(function () {
  var UNEVEN = 1.35; // "considerably larger"

  function layout() {
    var root = document.querySelector(".frontpage_container.three-pattern");
    if (!root) return;
    var a = root.querySelector(".slot-1");
    var b = root.querySelector(".slot-2");
    var c = root.querySelector(".slot-3");
    if (!a || !b || !c) return;

    var ha = a.getBoundingClientRect().height;
    var hb = b.getBoundingClientRect().height;

    c.style.gridColumn = "";
    if (ha > hb * UNEVEN) {
      c.style.gridColumn = "2";      // under the shorter (right)
    } else if (hb > ha * UNEVEN) {
      c.style.gridColumn = "1";      // under the shorter (left)
    } else {
      c.style.gridColumn = "1 / span 2"; // midpoint under both
    }

    var box = root.getBoundingClientRect();
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var scale = Math.min(vw / box.width, vh / box.height, 1);
    if (scale < 0.15) scale = 0.15;
    root.style.transformOrigin = "top center";
    root.style.transform = "scale(" + scale + ")";
  }

  window.addEventListener("load", layout);
  window.addEventListener("resize", layout);
  window.addEventListener("message", function (ev) {
    if (ev.data && ev.data.type === "sandbells-scale") layout();
  });
})();
