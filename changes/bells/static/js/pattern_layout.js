(function () {
  var UNEVEN = 1.35;

  function cfg() {
    var el = document.getElementById("sandbells-display");
    if (!el) return {};
    try { return JSON.parse(el.textContent); } catch (e) { return {}; }
  }

  function slots() {
    return {
      a: document.querySelector(".pattern-slot.slot-1"),
      b: document.querySelector(".pattern-slot.slot-2"),
      c: document.querySelector(".pattern-slot.slot-3"),
      box: document.querySelector(".frontpage_container.three-pattern")
        || document.querySelector(".frontpage_container")
    };
  }

  function applyShorter(box, a, b, c) {
    if (!box || !a || !b || !c) return;
    if (box.getAttribute("data-stacked") === "1") return;
    var ha = a.getBoundingClientRect().height;
    var hb = b.getBoundingClientRect().height;
    if (ha < hb * UNEVEN && hb < ha * UNEVEN) return;

    function col() {
      var d = document.createElement("div");
      d.className = "pattern-col";
      d.style.display = "flex";
      d.style.flexDirection = "column";
      d.style.alignItems = "center";
      d.style.gap = "16px";
      return d;
    }
    var left = col();
    var right = col();
    box.style.display = "flex";
    box.style.flexDirection = "row";
    box.style.alignItems = "flex-start";
    box.style.justifyContent = "center";
    if (ha <= hb) {
      left.appendChild(a);
      left.appendChild(c);
      right.appendChild(b);
    } else {
      left.appendChild(a);
      right.appendChild(b);
      right.appendChild(c);
    }
    box.appendChild(left);
    box.appendChild(right);
    box.setAttribute("data-stacked", "1");
  }

  window.fitThreePatterns = function () {
    var box = document.querySelector(".frontpage_container");
    if (!box) return;
    box.style.transformOrigin = "top center";
    box.style.transform = "none";
    var r = box.getBoundingClientRect();
    var availW = window.innerWidth - 8;
    var availH = window.innerHeight - 8;
    if (r.width < 1 || r.height < 1) return;
    var s = Math.min(availW / r.width, availH / r.height, 1);
    if (s < 0.99) box.style.transform = "scale(" + s + ")";
  };

  function layout() {
    var mode = cfg().pattern_position_mode || "centre";
    var s = slots();
    if (mode === "shorter") applyShorter(s.box, s.a, s.b, s.c);
    window.fitThreePatterns();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", layout);
  } else {
    layout();
  }
  window.addEventListener("load", layout);
  window.addEventListener("resize", window.fitThreePatterns);
})();
