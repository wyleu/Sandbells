(function (global) {
  var CLAPPER_POS = {
    lu: { x: -0.35, y: -0.30 },
    ru: { x:  0.35, y: -0.30 },
    c:  { x:  0,    y:  0    },
    rl: { x:  0.35, y:  0.30 },
    ll: { x: -0.35, y:  0.30 }
  };
  var BELL_COLOURS = {
    1: "#ff2020", 2: "#ff8c00", 3: "#ffd000", 4: "#22c022",
    5: "#00d4d4", 6: "#2050ff", 7: "#e000e0", 8: "#8b0000"
  };
  var SIZE_SPREAD = 0.12;
  // 2-side = ll (short), 4-side = ru (long) — tape axis
  var TAPE_NEG = CLAPPER_POS.ll;
  var TAPE_POS = CLAPPER_POS.ru;
  var TAPE_MAX_NEG = 0.40;
  var TAPE_MAX_POS = 0.80;

  function colourFor(bell) { return BELL_COLOURS[bell] || "#888"; }

  function sizeScale(bell, n, spread) {
    if (n <= 1) return 1;
    var k = spread != null ? spread : SIZE_SPREAD;
    var t = (Number(bell) - 1) / (n - 1);
    return 1 + k * (2 * t - 1);
  }

  function layoutBellsOnCircle(bells, cx, cy, radius, theta0) {
    var n = bells.length;
    if (!n) return [];
    theta0 = theta0 != null ? theta0 : (Math.PI / n);
    var step = (2 * Math.PI) / n;
    return bells.map(function (bell, i) {
      var angle = theta0 + i * step;
      return {
        bell: bell, index: i, angle: angle,
        x: cx + radius * Math.sin(angle),
        y: cy - radius * Math.cos(angle)
      };
    });
  }

  function tapeT(u) {
    u = Number(u);
    if (isNaN(u)) return 0;
    if (u <= 2) return -1 + (u / 2);
    if (u <= 3) return 0;
    if (u >= 7) return 1;
    return (u - 3) / 4;
  }

  function tapeOffset(t, amp, mouthR) {
    amp = amp == null ? 1 : amp;
    t = t * amp;
    var side = t < 0 ? TAPE_NEG : TAPE_POS;
    var max = (t < 0 ? TAPE_MAX_NEG : TAPE_MAX_POS) * mouthR;
    var mag = Math.abs(t) * max;
    return { cx: side.x / 0.46 * mag, cy: side.y / 0.46 * mag };
  }

  function draw(container, opts) {
    opts = opts || {};
    var el = typeof container === "string" ? document.querySelector(container) : container;
    if (!el) return null;
    var bells = opts.bells && opts.bells.length ? opts.bells.slice() : [1,2,3,4,5,6,7,8];
    var n = bells.length;
    var w = opts.width || 250, h = opts.height || 250;
    var cx = w / 2, cy = h / 2;
    var radius = opts.radius != null ? opts.radius : Math.min(w, h) * 0.35;
    var padR = opts.padR != null ? opts.padR : Math.min(w, h) * 0.11;
    var baseMouth = padR * 0.9;
    var theta0 = opts.theta0 != null ? opts.theta0 : (Math.PI / n);
    var nodes = layoutBellsOnCircle(bells, cx, cy, radius, theta0);

    el.innerHTML = "";
    var NS = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", "100%");
    svg.setAttribute("class", "bell-band-svg");
    var defs = document.createElementNS(NS, "defs");
    svg.appendChild(defs);
    var mouthByBell = {};

    nodes.forEach(function (d) {
      var mouthR = baseMouth * sizeScale(d.bell, n, opts.sizeSpread);
      mouthByBell[d.bell] = mouthR;
      var clipId = "bell-mouth-clip-" + d.bell;
      var clip = document.createElementNS(NS, "clipPath");
      clip.setAttribute("id", clipId);
      var clipC = document.createElementNS(NS, "circle");
      clipC.setAttribute("cx", "0");
      clipC.setAttribute("cy", "0");
      clipC.setAttribute("r", String(mouthR));
      clip.appendChild(clipC);
      defs.appendChild(clip);

      var g = document.createElementNS(NS, "g");
      g.setAttribute("class", "bell-pad");
      g.setAttribute("data-bell", String(d.bell));
      g.setAttribute("transform", "translate(" + d.x + "," + d.y + ")");
      g.style.cursor = "pointer";

      var fill = document.createElementNS(NS, "circle");
      fill.setAttribute("r", String(mouthR));
      fill.setAttribute("fill", "#f5f5f5");

      var clipG = document.createElementNS(NS, "g");
      clipG.setAttribute("class", "bell-clapper-g");
      clipG.setAttribute("clip-path", "url(#" + clipId + ")");

      var clap = document.createElementNS(NS, "circle");
      clap.setAttribute("class", "bell-clapper");
      clap.setAttribute("cx", "0");
      clap.setAttribute("cy", "0");
      clap.setAttribute("r", String(mouthR * 0.4));
      clap.setAttribute("fill", colourFor(d.bell));

      var hiAng = 210 * Math.PI / 180;
      var hiR = mouthR * 0.4;
      var hi = document.createElementNS(NS, "circle");
      hi.setAttribute("class", "bell-highlight");
      hi.setAttribute("cx", String(hiR * Math.cos(hiAng) * 0.45));
      hi.setAttribute("cy", String(hiR * Math.sin(hiAng) * 0.45));
      hi.setAttribute("r", String(Math.max(1.1, mouthR * 0.07)));
      hi.setAttribute("fill", "#ffffff");
      hi.setAttribute("pointer-events", "none");

      clipG.appendChild(clap);
      clipG.appendChild(hi);


      var gap0 = (opts.ringGapStartDeg != null ? opts.ringGapStartDeg : 0) * Math.PI / 180;
      var gap1 = (opts.ringGapEndDeg != null ? opts.ringGapEndDeg : 60) * Math.PI / 180;
      var x3 = mouthR * Math.cos(gap0);
      var y3 = mouthR * Math.sin(gap0);
      var x5 = mouthR * Math.cos(gap1);
      var y5 = mouthR * Math.sin(gap1);

      var ring = document.createElementNS(NS, "path");
      ring.setAttribute(
        "d",
        "M " + x5 + " " + y5 +
        " A " + mouthR + " " + mouthR + " 0 1 1 " + x3 + " " + y3
      );
      ring.setAttribute("fill", "none");
      ring.setAttribute("stroke", colourFor(d.bell));
      ring.setAttribute("stroke-width", String(Math.max(2, mouthR * 0.12)));
      ring.setAttribute("stroke-linecap", "round");


      var num = document.createElementNS(NS, "text");
      var numAng = ((opts.numDeg != null ? opts.numDeg : 30) * Math.PI) / 180;
      var numR = mouthR * (opts.numR != null ? opts.numR : 1.05);

      num.setAttribute("class", "bell-num");
      num.setAttribute("x", String(numR * Math.cos(numAng)));
      num.setAttribute("y", String(numR * Math.sin(numAng)));
      num.setAttribute("text-anchor", "middle");
      num.setAttribute("dominant-baseline", "middle");
      num.setAttribute("fill", "#000");
      num.setAttribute("font-size", String(Math.max(9, mouthR * 0.55)));
      num.setAttribute("font-family", "sans-serif");
      num.setAttribute("font-weight", "700");
      num.setAttribute("pointer-events", "none");
      num.textContent = String(d.bell);

      g.appendChild(fill);
      g.appendChild(clipG)
      g.appendChild(ring);
      g.appendChild(num);

      if (opts.onPadClick) {
        g.addEventListener("click", function (ev) { opts.onPadClick(d.bell, d, ev); });
      }
      svg.appendChild(g);
    });

    el.appendChild(svg);
    el.__bellBand = { bells: bells, mouthByBell: mouthByBell, tape: {} };
    return { svg: svg, nodes: nodes };
  }

  function setTape(host, bell, u, amp) {
    var el = typeof host === "string" ? document.querySelector(host) : host;
    if (!el) return;
    var gClap = el.querySelector('.bell-pad[data-bell="' + bell + '"] .bell-clapper-g');
    if (!gClap) return;
    var mouthR = (el.__bellBand && el.__bellBand.mouthByBell && el.__bellBand.mouthByBell[bell]) || 20;
    var off = tapeOffset(tapeT(u), amp, mouthR);
    gClap.setAttribute("transform", "translate(" + off.cx + "," + off.cy + ")");
    if (el.__bellBand) {
      el.__bellBand.tape[bell] = { u: u, amp: amp };
    }
  }

  function setPose(host, bell, pose, opts) {
    opts = opts || {};
    if (pose === "down") return setTape(host, bell, 2.5, 0);
    if (pose === "stood") return setTape(host, bell, opts.dir === "ccw" ? 0.3 : 6.5, 1);
    if (pose === "swing" || pose === "settling") {
      return setTape(host, bell, opts.u != null ? opts.u : 5, opts.amp != null ? opts.amp : 1);
    }
    setTape(host, bell, 2.5, 0);
  }

  function settleDemo(host, bell, opts) {
    opts = opts || {};
    var amp = opts.amp != null ? opts.amp : 1;
    var omega = opts.omega != null ? opts.omega : 3.2;
    var decay = opts.decay != null ? opts.decay : 0.992;
    var t0 = null;
    function frame(ts) {
      if (t0 == null) t0 = ts;
      var t = (ts - t0) / 1000;
      amp *= decay;
      var u = 2.5 + amp * 2.4 * Math.sin(omega * t * Math.PI * 2);
      if (u < 0) u = 0;
      if (u > 7) u = 7;
      setTape(host, bell, u, 1);
      if (amp > 0.04) requestAnimationFrame(frame);
      else setTape(host, bell, 2.5, 0);
    }
    requestAnimationFrame(frame);
  }

  global.BellBand = {
    draw: draw,
    setTape: setTape,
    setPose: setPose,
    settleDemo: settleDemo,
    layoutBellsOnCircle: layoutBellsOnCircle,
    CLAPPER_POS: CLAPPER_POS
  };
})(window);
