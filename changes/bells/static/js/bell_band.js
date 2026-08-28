(function (global) {
  var CLAPPER_POS = {
    lu: { x: -0.35, y: -0.30 },
    ru: { x:  0.35, y: -0.30 },
    c:  { x:  0,    y:  0    },
    rl: { x:  0.35, y:  0.30 },
    ll: { x: -0.35, y:  0.30 }
  };

  var BELL_COLOURS = {
      1: "#ff2020",  // light / bright red
      2: "#ff8c00",  // orange
      3: "#ffd000",  // yellow
      4: "#22c022",  // green
      5: "#00d4d4",  // cyan
      6: "#2050ff",  // blue
      7: "#e000e0",  // magenta
      8: "#8b0000"   // dark red
     };

   function colourFor(bell, n) {
      return BELL_COLOURS[bell] || "#888";
   }

  function layoutBellsOnCircle(bells, cx, cy, radius, theta0) {

    theta0 = theta0 != null ? theta0 : -Math.PI / 2;
    var n = bells.length;

    if (!n) return [];
    var step = (2 * Math.PI) / n;
    return bells.map(function (bell, i) {
      var angle = theta0 + i * step;
      return {
        bell: bell,
        index: i,
        angle: angle,
        x: cx + radius * Math.sin(angle),
        y: cy - radius * Math.cos(angle)
      };
    });
  }

  function clapperOffset(pos, R) {
    var p = CLAPPER_POS[pos] || CLAPPER_POS.c;
    return { cx: p.x * R, cy: p.y * R };
  }

  function draw(container, opts) {
    opts = opts || {};
    var el = typeof container === "string" ? document.querySelector(container) : container;
    if (!el) return null;

    var bells = opts.bells && opts.bells.length ? opts.bells.slice() : [1,2,3,4,5,6,7,8];
    var w = opts.width || el.clientWidth || 400;
    var h = opts.height || el.clientHeight || 400;
    var cx = w / 2, cy = h / 2;
    var radius = opts.radius != null ? opts.radius : Math.min(w, h) * 0.35;
    var padR = opts.padR != null ? opts.padR : Math.min(w, h) * 0.11;
    var mouthR = padR * 0.9;
     // In layoutBellsOnCircle call inside draw():
     // Centre the gap between last and first on the top → 1 and 8 flank the top

    var n = bells.length;

    var theta0 = opts.theta0 != null ? opts.theta0 : (-Math.PI / 2 - Math.PI / n);
    var nodes = layoutBellsOnCircle(bells, cx, cy, radius, theta0);

    el.innerHTML = "";
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");
    svg.setAttribute("class", "bell-band-svg");

    var defs = document.createElementNS(NS, "defs");
    var clip = document.createElementNS(NS, "clipPath");
    clip.setAttribute("id", "bell-mouth-clip");
    var clipC = document.createElementNS(NS, "circle");
    clipC.setAttribute("cx", "0");
    clipC.setAttribute("cy", "0");
    clipC.setAttribute("r", String(mouthR));
    clip.appendChild(clipC);
    defs.appendChild(clip);
    svg.appendChild(defs);

    nodes.forEach(function (d) {
      var g = document.createElementNS(NS, "g");
      g.setAttribute("class", "bell-pad");
      g.setAttribute("data-bell", String(d.bell));
      g.setAttribute("transform", "translate(" + d.x + "," + d.y + ")");
      g.style.cursor = "pointer";

      var fill = document.createElementNS(NS, "circle");
      fill.setAttribute("r", String(mouthR));
      fill.setAttribute("fill", "#f5f5f5");

      var clipped = document.createElementNS(NS, "g");
      clipped.setAttribute("clip-path", "url(#bell-mouth-clip)");
      var off = clapperOffset("c", mouthR);
      var clap = document.createElementNS(NS, "circle");
      clap.setAttribute("class", "bell-clapper");
      clap.setAttribute("data-pos", "c");
      clap.setAttribute("cx", String(off.cx));
      clap.setAttribute("cy", String(off.cy));
      clap.setAttribute("r", String(mouthR * 0.4));
      clap.setAttribute("fill", colourFor(d.bell, n));
      clipped.appendChild(clap);

      var ring = document.createElementNS(NS, "circle");
      var col = colourFor(d.bell, n);

      ring.setAttribute("r", String(mouthR));
      ring.setAttribute("fill", "none");
      ring.setAttribute("stroke", col);
      ring.setAttribute("stroke-width","3"); //   String(Math.max(2, mouthR * 0.18)));

      g.appendChild(fill);
      g.appendChild(clipped);
      g.appendChild(ring);

      if (opts.onPadClick) {
        g.addEventListener("click", function (ev) {
          opts.onPadClick(d.bell, d, ev);
        });
      }
      svg.appendChild(g);
    });

    el.appendChild(svg);
    el.__bellBand = { mouthR: mouthR, bells: bells };
    return { svg: svg, nodes: nodes };
  }

  function animateClapper(circleEl, mouthR, fromKey, toKey, durationMs, done) {
    var from = CLAPPER_POS[fromKey] || CLAPPER_POS.c;
    var to = CLAPPER_POS[toKey] || CLAPPER_POS.c;
    var x0 = from.x * mouthR, y0 = from.y * mouthR;
    var x1 = to.x * mouthR, y1 = to.y * mouthR;
    var t0 = null;
    durationMs = durationMs || 160;
    function ease(t) { return t * (2 - t); }
    function frame(ts) {
      if (t0 == null) t0 = ts;
      var t = Math.min(1, (ts - t0) / durationMs);
      var e = ease(t);
      circleEl.setAttribute("cx", x0 + (x1 - x0) * e);
      circleEl.setAttribute("cy", y0 + (y1 - y0) * e);
      if (t < 1) requestAnimationFrame(frame);
      else if (done) done();
    }
    requestAnimationFrame(frame);
  }

  function strike(host, bell, opts) {
     opts = opts || {};
     var el = typeof host === "string" ? document.querySelector(host) : host;
     if (!el) return;
     var circle = el.querySelector('.bell-pad[data-bell="' + bell + '"] .bell-clapper');
     if (!circle) return;
     var mouthR = (el.__bellBand && el.__bellBand.mouthR) || 20;
     var ms = opts.duration || 120;

     // rl → c → lu → c → rl (diagonal through centre)
     function go(a, b, next) {
        animateClapper(circle, mouthR, a, b, ms, next);
     }
     go("rl", "c", function () {
       go("c", "lu", function () {
         go("lu", "c", function () {
           go("c", "rl", function () {
             circle.setAttribute("data-pos", "rl");
             if (opts.onDone) opts.onDone(bell);
           });
         });
       });
     });
   }

  global.BellBand = {
    draw: draw,
    strike: strike,
    layoutBellsOnCircle: layoutBellsOnCircle,
    CLAPPER_POS: CLAPPER_POS
  };
})(window);
