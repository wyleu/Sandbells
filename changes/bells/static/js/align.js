/**
 * align.js -- the Alignment page.
 * Talks to the concentrator Pico's /ws directly (its own socket, like the farm
 * page; Django is not in the path).  A row of head buttons (one per channel
 * the survey reports; inactive ones are selectable but marked) and ONE head's
 * panel at a time.  The Pico scopes ONE head at a time, so only the selected
 * head is watched (switching stops the old scope and starts the new one; an
 * inactive head is not watched at all): the rolling comparator trace (a
 * canvas, no libraries), fresh readouts and the nudge buttons.  The selected
 * head is kept in the URL hash (#head=2) and sessionStorage, so it survives
 * a reload and coming back from another tab.  Adjustments are live only: the Pico never
 * writes them to settings.json.  Protocol: sandswing docs/align-scope.md.
 * Plain ES5 for Luakit/WebKit on a Pi 3.
 */
(function () {
  "use strict";

  var SCHEMA = "sand.panel/v1";
  var ACTIVE = ["head_new", "head_old"];
  var NO_THRESHOLD = ["head_old"];
  var HELLO_MS = 5000;           // a plain frame so the Pico knows we are alive
  var SILENT_MS = 20000;         // heartbeats heard, then nothing: dead link
  var CONNECT_MS = 5000;         // an address that never opens: try the next
  var DRAW_MS = 100;             // trace redraw (10 per second)
  var PRESS_LOCK_MS = 260;       // the Pico takes one step per head per 200 ms
  var VREF = 3.3;
  var STORE_KEY = "sandheadsHead";   // sessionStorage; the URL hash is #head=N
  var MAX_HEADS = 16;

  var CFG = { wsUrls: [], keepAliveMs: 2000, windowMs: 2000 };
  var S = {
    sock: null, urlIx: 0, rd: window.ReconnectDelay.create(), connectTimer: null, keepTimer: null,
    helloAt: 0, lastRx: 0, heardHb: 0,
    kinds: [], tower: "", gotInfo: false,
    sel: 0,                      // the head on show (1-based), active or not
    want: 0,                     // the head being watched: sel when it is active, else none
    shown: 0, cards: {}
  };

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function inList(v, list) {
    for (var i = 0; i < list.length; i++) if (list[i] === v) return true;
    return false;
  }

  function pct(v) { return v === null || v === undefined ? "—" : (v * 100 / 65535).toFixed(1) + " %"; }
  function volts(v) { return v === null || v === undefined ? "" : (v * VREF / 65535).toFixed(2) + " V"; }

  /* ---- decoding ---------------------------------------------------------- */

  /* hex string, oldest sample first, MSB first -> runs [from, to, bit] */
  function decodeRuns(hex, n) {
    var runs = [];
    var from = 0, cur = -1;
    for (var j = 0; j < n; j++) {
      var byte = parseInt(hex.substr((j >> 3) * 2, 2), 16) || 0;
      var bit = (byte >> (7 - (j & 7))) & 1;
      if (j === 0) {
        cur = bit;
      } else if (bit !== cur) {
        runs.push([from, j - 1, cur]);
        from = j;
        cur = bit;
      }
    }
    if (n > 0) runs.push([from, n - 1, cur]);
    return runs;
  }

  /* ---- heads: a selector and ONE panel ------------------------------------ */

  function kindOf(ch) { return S.kinds[ch - 1] || ""; }

  function isActive(ch) { return inList(kindOf(ch), ACTIVE); }

  function kindWord(kind) {
    if (kind === "head_new") return "new head";
    if (kind === "head_old") return "old head";
    if (kind === "trigger") return "trigger plug";
    if (kind === "loopback") return "loopback plug";
    if (kind === "no_board" || kind === "unknown" || kind === "") return "nothing found";
    return kind;                                   // empty, fault
  }

  function kindShort(kind) {
    if (kind === "head_new") return "new";
    if (kind === "head_old") return "old";
    if (kind === "no_board" || kind === "unknown" || kind === "") return "?";
    return kind;
  }

  function firstActive() {
    for (var i = 1; i <= S.kinds.length; i++) if (isActive(i)) return i;
    return 0;
  }

  function readout(label) {
    var d = el("div");
    d.appendChild(el("span", "lab", label));
    var v = el("span", "val", "—");
    var s = el("span", "sub", "");
    d.appendChild(v);
    d.appendChild(s);
    return { box: d, val: v, sub: s };
  }

  function pair(card, key, name) {
    var box = el("div", "pair");
    box.appendChild(el("span", "name", name));
    var dn = el("button", "nudge", "−");
    var up = el("button", "nudge", "+");
    dn.type = up.type = "button";
    dn.title = name + " down";
    up.title = name + " up";
    dn.addEventListener("click", function () { nudge(card, key, -1, dn, up); });
    up.addEventListener("click", function () { nudge(card, key, 1, dn, up); });
    box.appendChild(dn);
    box.appendChild(up);
    return { box: box, dn: dn, up: up };
  }

  function makeCard(ch) {
    var card = { ch: ch, runs: [], n: 0, dt: 20, rx: 0, thr: null, drv: null, locked: false };
    var root = el("section", "card off");
    root.setAttribute("data-ch", String(ch));
    var h = el("h2");
    h.appendChild(el("span", "", "Head " + ch));
    card.kindEl = el("span", "kind", "");
    h.appendChild(card.kindEl);
    card.stateEl = el("span", "state", "");
    h.appendChild(card.stateEl);
    root.appendChild(h);

    var body = el("div", "body");
    var left = el("div", "left");
    card.canvas = el("canvas", "scope");
    card.canvas.setAttribute("aria-label", "comparator output, last two seconds");
    left.appendChild(card.canvas);
    card.hint = el("div", "hint", "");
    left.appendChild(card.hint);
    card.msg = el("div", "msg", "");
    left.appendChild(card.msg);
    body.appendChild(left);

    var right = el("div", "right");
    var r = el("div", "readouts");
    card.ma = readout("Laser current");
    card.rb = readout("Threshold readback");
    card.thrR = readout("Threshold duty");
    card.drvR = readout("Laser drive duty");
    r.appendChild(card.ma.box);
    r.appendChild(card.rb.box);
    r.appendChild(card.thrR.box);
    r.appendChild(card.drvR.box);
    right.appendChild(r);

    var n = el("div", "nudges");
    card.thrB = pair(card, "thr", "Threshold");
    card.drvB = pair(card, "drive", "Laser drive");
    n.appendChild(card.thrB.box);
    n.appendChild(card.drvB.box);
    right.appendChild(n);
    body.appendChild(right);
    root.appendChild(body);
    card.root = root;
    return card;
  }

  function cardFor(ch) {
    if (!S.cards[ch]) S.cards[ch] = makeCard(ch);
    return S.cards[ch];
  }

  /* the row of head buttons: one per channel the survey reports */
  function renderTabs() {
    var bar = $("align-heads");
    if (!bar) return;
    bar.innerHTML = "";
    for (var ch = 1; ch <= S.kinds.length; ch++) {
      (function (ch) {
        var act = isActive(ch);
        var b = el("button", "headtab " + (act ? "act" : "inact") + (ch === S.sel ? " sel" : ""));
        b.type = "button";
        b.setAttribute("data-ch", String(ch));
        b.setAttribute("role", "tab");
        b.setAttribute("aria-selected", ch === S.sel ? "true" : "false");
        b.title = "Head " + ch + ": " + kindWord(kindOf(ch)) + (act ? "" : " (not active)");
        b.appendChild(el("span", "dot", ""));
        b.appendChild(el("span", "num", String(ch)));
        b.appendChild(el("span", "kw", kindShort(kindOf(ch))));
        b.addEventListener("click", function () { select(ch, true); });
        bar.appendChild(b);
      })(ch);
    }
  }

  /* the one panel on show */
  function renderPanel() {
    var main = $("align-main");
    if (!main) return;
    main.innerHTML = "";
    S.shown = 0;
    if (!S.kinds.length || !S.sel) {
      var p = el("p", "", S.gotInfo ? "No heads reported by this concentrator yet." : "Asking the concentrator which heads are fitted…");
      p.id = "align-wait";
      main.appendChild(p);
      return;
    }
    var card = cardFor(S.sel);
    main.appendChild(card.root);
    S.shown = S.sel;
    refreshCard(card);
  }

  function refreshCard(card) {
    var kind = kindOf(card.ch);
    var active = inList(kind, ACTIVE);
    var watching = S.want === card.ch;
    card.kindEl.textContent = kindWord(kind);
    card.root.className = "card" + (watching ? " watching" : " off") + (active ? "" : " inactive");
    card.stateEl.textContent = !active ? "not active" : (watching ? "watching" : "not watching");
    card.hint.textContent = active ? "" :
      "Nothing to watch or adjust: this channel is " + kindWord(kind) + ". Pick a head marked with a green dot.";
    var quiet = S.tower === "inactive";
    var noThr = inList(kind, NO_THRESHOLD);
    var busy = card.locked || !quiet || !active;
    card.thrB.dn.disabled = card.thrB.up.disabled = busy || noThr;
    card.drvB.dn.disabled = card.drvB.up.disabled = busy;
    card.thrB.box.title = noThr ? "old heads have no threshold" : "";
    card.thrR.val.textContent = noThr ? "n/a" : (active ? pct(card.thr) : "—");
    card.thrR.sub.textContent = card.thr === null || noThr || !active ? "" : String(card.thr);
    card.drvR.val.textContent = active ? pct(card.drv) : "—";
    card.drvR.sub.textContent = card.drv === null || !active ? "" : String(card.drv);
  }

  function refreshAll() {
    for (var k in S.cards) if (S.cards.hasOwnProperty(k)) refreshCard(S.cards[k]);
  }

  /* ---- which head, and keeping it across reloads -------------------------- */

  function parseHash(h) {
    var m = /(?:^#|[#&])head=(\d+)/.exec(h || "");
    return m ? parseInt(m[1], 10) : 0;
  }

  function storedHead() {
    var n = 0;
    try { n = parseHash(window.location.hash); } catch (e) {}
    if (!n) {
      try { n = parseInt(window.sessionStorage.getItem(STORE_KEY), 10) || 0; } catch (e) {}
    }
    return n > 0 && n <= MAX_HEADS ? n : 0;
  }

  function storeHead(ch) {
    try { window.sessionStorage.setItem(STORE_KEY, String(ch)); } catch (e) {}
    try {
      if (window.history && window.history.replaceState) window.history.replaceState(null, "", "#head=" + ch);
      else window.location.hash = "head=" + ch;
    } catch (e) {}
  }

  function validHead(ch) {
    return ch >= 1 && (S.kinds.length ? ch <= S.kinds.length : ch <= MAX_HEADS);
  }

  /* the head to show: the stored one if the survey has it, else the first active head */
  function select(ch, user) {
    if (!validHead(ch)) return;
    S.sel = ch;
    if (user) storeHead(ch);
    renderTabs();
    if (S.shown !== ch) renderPanel();
    sync();
  }

  /* watch the selected head (if it is active) and nothing else: stop the old
     one, start the new one */
  function sync() {
    var want = S.sel && isActive(S.sel) ? S.sel : 0;
    if (want !== S.want) {
      var old = S.want;
      S.want = want;
      if (old) send({ cmd: "align", ch: old, scope: false });
      if (want) {
        var c = cardFor(want);
        c.runs = [];
        c.n = 0;
        send({ cmd: "align", ch: want, scope: true });
      }
    }
    refreshAll();
  }

  function kindsChanged() {
    S.gotInfo = true;
    if (!S.sel || !validHead(S.sel)) S.sel = firstActive() || (S.kinds.length ? 1 : 0);
    renderTabs();
    if (S.shown !== S.sel || !S.sel) renderPanel();
    sync();
  }

  function setMsg(card, text, refused) {
    card.msg.textContent = text;
    card.msg.className = "msg" + (refused ? " refused" : "");
  }

  function setTower(t) {
    if (!t) return;
    S.tower = t;
    var pill = $("align-tower");
    if (!pill) return;
    if (t === "inactive") {
      pill.className = "pill pill-ok";
      pill.textContent = "tower quiet";
    } else {
      pill.className = "pill pill-busy";
      pill.textContent = "strokes in progress: adjusting paused";
    }
  }

  function setLink(cls, text) {
    var p = $("align-link");
    if (!p) return;
    p.className = "pill " + cls;
    p.textContent = text;
  }

  /* ---- talking to the Pico ------------------------------------------------ */

  function send(obj) {
    var sock = S.sock;
    if (!sock || sock.readyState !== 1) return false;
    try { sock.send(JSON.stringify(obj)); } catch (e) { return false; }
    return true;
  }

  function nudge(card, key, dir, dn, up) {
    var cmd = { cmd: "align", ch: card.ch };
    cmd[key] = dir;
    if (!send(cmd)) {
      setMsg(card, "Not connected to the concentrator.", true);
      return;
    }
    card.locked = true;
    refreshCard(card);
    setTimeout(function () { card.locked = false; refreshCard(card); }, PRESS_LOCK_MS);
  }

  function keepAlive() {
    var now = Date.now();
    if (S.want) {
      send({ cmd: "align", ch: S.want, scope: true });
    }
    if (now - S.helloAt >= HELLO_MS) {
      S.helloAt = now;
      send({ schema: "sand.hello/v1", type: "heartbeat", src: "sandbells-align" });
    }
    if (S.heardHb && now - S.lastRx > SILENT_MS && S.sock) {
      try { S.sock.close(); } catch (e) {}
    }
  }

  function onFrame(m) {
    var b = m.body || {};
    var card = S.cards[b.ch];
    setTower(b.tower);
    if (!card || b.ch !== S.want) return;       // a late frame of a head we stopped watching
    card.n = b.n || 0;
    card.dt = b.dt || 20;
    card.runs = decodeRuns(b.bits || "", card.n);
    card.rx = Date.now();
    card.thr = b.thr === undefined ? null : b.thr;
    card.drv = b.drv === undefined ? null : b.drv;
    card.ma.val.textContent = b.ma === null || b.ma === undefined ? "—" : b.ma.toFixed(1) + " mA";
    card.rb.val.textContent = b.rb === null || b.rb === undefined ? "—" : String(b.rb);
    card.rb.sub.textContent = volts(b.rb);
    card.ma.val.className = card.rb.val.className = "val" + (b.busy ? " stale" : "");
    refreshCard(card);
  }

  function onAck(m) {
    var b = m.body || {};
    var card = S.cards[b.ch];
    setTower(b.tower);
    if (b.what === "bad") return;
    if (!card) return;
    if (b.thr !== undefined) card.thr = b.thr;
    if (b.drv !== undefined) card.drv = b.drv;
    if (b.what === "scope") {
      if (!b.ok && S.want === card.ch) setMsg(card, "Scope off: " + b.why, true);
      refreshCard(card);
      return;
    }
    var name = b.what === "thr" ? "Threshold" : "Laser drive";
    if (b.ok) {
      setMsg(card, name + " now " + pct(b.what === "thr" ? b.thr : b.drv) + " (live, not saved)", false);
    } else {
      setMsg(card, "Not changed: " + b.why, true);
    }
    refreshCard(card);
  }

  function onInfo(m) {
    var b = m.body || {};
    S.kinds = b.kinds || [];
    setTower(b.tower);
    kindsChanged();
  }

  function onHeartbeat(m) {
    var b = m.body || {};
    S.heardHb = 1;
    setTower(b.tower);
    if (b.chan && b.chan.length) {
      var kinds = [];
      for (var i = 0; i < b.chan.length; i++) kinds.push(b.chan[i][0]);
      var same = kinds.length === S.kinds.length;
      for (var j = 0; same && j < kinds.length; j++) if (kinds[j] !== S.kinds[j]) same = false;
      if (!same) {
        S.kinds = kinds;
        kindsChanged();
      }
    }
  }

  function onMessage(ev) {
    S.lastRx = Date.now();
    var text = ev.data;
    if (typeof text !== "string" || text.indexOf(SCHEMA) < 0) return;
    var m;
    try { m = JSON.parse(text); } catch (e) { return; }
    if (!m || m.schema !== SCHEMA) return;
    if (m.type === "align") onFrame(m);
    else if (m.type === "align_ack") onAck(m);
    else if (m.type === "align_info") onInfo(m);
    else if (m.type === "heartbeat") onHeartbeat(m);
  }

  function stopTimers() {
    if (S.connectTimer) clearTimeout(S.connectTimer);
    if (S.keepTimer) clearInterval(S.keepTimer);
    S.connectTimer = S.keepTimer = null;
  }

  function connect() {
    if (document.visibilityState === "hidden") return;
    var urls = CFG.wsUrls || [];
    if (!urls.length) { setLink("pill-busy", "no address for this device"); return; }
    stopTimers();
    try { if (S.sock) S.sock.close(); } catch (e) {}
    var url = urls[S.urlIx % urls.length];
    var sock;
    try { sock = new WebSocket(url); } catch (e) { retry(); return; }
    S.sock = sock;
    setLink("pill-wait", "connecting…");
    S.connectTimer = setTimeout(function () {
      if (sock.readyState !== 1) { try { sock.close(); } catch (e) {} }
    }, CONNECT_MS);
    sock.onopen = function () {
      if (S.connectTimer) clearTimeout(S.connectTimer);
      S.connectTimer = null;
      S.rd.opened();                           // reconnect_delay.js: resets only after 30 s up
      S.lastRx = Date.now();
      S.heardHb = 0;
      setLink("pill-ok", "live");
      send({ cmd: "align", info: true });
      if (S.want) send({ cmd: "align", ch: S.want, scope: true });
      S.keepTimer = setInterval(keepAlive, CFG.keepAliveMs || 2000);
    };
    sock.onmessage = onMessage;
    sock.onclose = function () {
      if (sock !== S.sock) return;            // an older socket we replaced
      stopTimers();
      retry();
    };
  }

  function retry() {
    setLink("pill-wait", "retrying…");
    S.urlIx += 1;                              // the other address (home / tower) next time
    if (document.visibilityState === "hidden") return;
    setTimeout(connect, S.rd.closed());
  }

  /* ---- the rolling trace -------------------------------------------------- */

  function sizeCanvas(c) {
    var w = c.clientWidth, h = c.clientHeight;
    if (w && (c.width !== w || c.height !== h)) { c.width = w; c.height = h; }
  }

  function drawCard(card, now) {
    var c = card.canvas;
    sizeCanvas(c);
    var W = c.width, H = c.height;
    if (!W || !H) return;
    var g = c.getContext("2d");
    var win = CFG.windowMs || 2000;
    g.fillStyle = "#17130c";
    g.fillRect(0, 0, W, H);

    // time grid every 0.5 s, scrolling with the data
    g.strokeStyle = "#3b3223";
    g.lineWidth = 1;
    g.beginPath();
    var t = Math.floor(now / 500) * 500;
    for (var k = 0; k < 6; k++, t -= 500) {
      var gx = Math.round(W - (now - t) / win * W) + 0.5;
      g.moveTo(gx, 0);
      g.lineTo(gx, H);
    }
    g.stroke();

    var yHi = Math.round(H * 0.2), yLo = Math.round(H * 0.8);
    g.fillStyle = "#b9a56f";
    g.font = "11px system-ui, sans-serif";
    g.fillText("high", 4, yHi - 4);
    g.fillText("low", 4, yLo + 12);

    if (S.want !== card.ch || !card.n || !card.runs.length) {
      g.fillStyle = "#d9c9a0";
      g.font = "13px system-ui, sans-serif";
      var why = S.want === card.ch ? "waiting for samples…" :
        (isActive(card.ch) ? "scope off" : "not an active head: nothing to show");
      g.fillText(why, W / 2 - 70, H / 2 + 4);
      return;
    }
    var age = now - card.rx;
    var per = card.dt / win * W;                // one sample's width
    function xOf(i) { return W - (age + (card.n - 1 - i) * card.dt) / win * W; }

    var prevY = null;
    for (var r = 0; r < card.runs.length; r++) {
      var run = card.runs[r];
      var x0 = xOf(run[0]);
      var x1 = xOf(run[1]) + per;
      var high = run[2] === 1;
      var y = high ? yHi : yLo;
      if (!high) {                              // beam broken / comparator low
        g.fillStyle = "rgba(150, 110, 220, 0.28)";
        g.fillRect(x0, 0, x1 - x0, H);
      }
      if (prevY !== null) {                     // the edge
        g.strokeStyle = "#ffd978";
        g.lineWidth = 1.5;
        g.beginPath();
        g.moveTo(x0, prevY);
        g.lineTo(x0, y);
        g.stroke();
      }
      g.strokeStyle = high ? "#6fdc7f" : "#b48cff";
      g.lineWidth = 2.5;
      g.beginPath();
      g.moveTo(x0, y);
      g.lineTo(x1, y);
      g.stroke();
      prevY = y;
    }
  }

  function drawAll() {
    var now = Date.now();
    var card = S.shown ? S.cards[S.shown] : null;      // only the head on show
    if (card) {
      try { drawCard(card, now); } catch (e) {}
    }
  }

  /* ---- start / visibility ------------------------------------------------- */

  function start(cfg) {
    for (var k in cfg) if (cfg.hasOwnProperty(k)) CFG[k] = cfg[k];
    if (CFG.activeKinds) ACTIVE = CFG.activeKinds;
    S.sel = storedHead();                       // #head=N, else sessionStorage, else the first active head
    setInterval(drawAll, DRAW_MS);
    window.addEventListener("hashchange", function () {
      var n = 0;
      try { n = parseHash(window.location.hash); } catch (e) {}
      if (n && n !== S.sel && validHead(n)) select(n, false);
    });
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        if (S.want) send({ cmd: "align", ch: S.want, scope: false });
        stopTimers();
        try { if (S.sock) S.sock.close(); } catch (e) {}
        S.sock = null;
      } else {
        S.rd.reset();
        connect();
      }
    });
    window.addEventListener("beforeunload", function () {
      if (S.want) send({ cmd: "align", ch: S.want, scope: false });
    });
    connect();
  }

  window.Align = { start: start, decodeRuns: decodeRuns, parseHash: parseHash };
})();
