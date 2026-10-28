// node --test changes/bells/js_tests/  -- farm_status.js: how the page's WebSocket reconnects
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "static", "js");
const SRC = fs.readFileSync(path.join(JS, "farm_status.js"), "utf8");
const RD_SRC = fs.readFileSync(path.join(JS, "reconnect_delay.js"), "utf8");

function rig(wsUrls) {
  const sockets = [];
  const timers = [];
  const clock = { t: 1000000 };
  const listeners = {};
  class WS {
    constructor(url) { this.url = url; this.readyState = 0; this.sent = []; sockets.push(this); }
    send(t) { this.sent.push(t); }
    close() { if (this.readyState === 3) return; this.readyState = 3; if (this.onclose) this.onclose(); }
    open() { this.readyState = 1; this.onopen(); }
  }
  const document = {
    visibilityState: "visible", cookie: "",
    getElementById: () => null,
    createElement: () => ({ style: {}, addEventListener() {}, appendChild() {}, setAttribute() {} }),
    addEventListener: (ev, fn) => { listeners[ev] = fn; },
  };
  const win = {};
  const sandbox = {
    window: win, document, WebSocket: WS, console,
    fetch: () => new Promise(() => {}),                    // the status poll never answers
    setInterval: (fn, ms) => { timers.push({ fn, ms, kind: "i" }); return timers.length; },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, kind: "t" }); return timers.length; },
    clearTimeout() {}, clearInterval() {},
    Date: { now: () => clock.t }, JSON, Math, parseInt, String, Error, Promise, encodeURIComponent,
    decodeURIComponent, location: { pathname: "/", protocol: "http:", host: "h" },
  };
  vm.createContext(sandbox);
  vm.runInContext(RD_SRC, sandbox);                        // the page loads reconnect_delay.js first
  vm.runInContext(SRC, sandbox);
  win.FarmStatus.start({ kind: "sandswing", id: "x", statusUrl: "", wsUrls });
  const retry = () => timers.filter((t) => t.kind === "t").pop();
  return { sockets, timers, clock, retry, document, listeners };
}

test("a Pico that opens the socket and drops it at once is retried more and more slowly", () => {
  const r = rig(["ws://pico/ws"]);
  const waits = [];
  for (let i = 0; i < 6; i++) {
    const s = r.sockets[r.sockets.length - 1];
    s.open();
    r.clock.t += 1000;                                     // up for a second, then dropped
    s.close();
    const t = r.retry();
    waits.push(t.ms);
    t.fn();
  }
  const exp = [1000, 2000, 4000, 8000, 15000, 15000];
  waits.forEach((w, i) => assert.ok(w >= exp[i] * 0.7 - 1 && w <= exp[i], `${i}: ${w}`));
});

test("a connection that lived 30 s starts the schedule again at about 1 s", () => {
  const r = rig(["ws://pico/ws"]);
  for (let i = 0; i < 3; i++) {                            // three quick drops: 4 s next
    const s = r.sockets[r.sockets.length - 1];
    s.open(); s.close(); r.retry().fn();
  }
  const s = r.sockets[r.sockets.length - 1];
  s.open();
  r.clock.t += 31000;
  s.close();
  const w = r.retry().ms;
  assert.ok(w >= 700 && w <= 1000, w);
});

test("two addresses: the other is tried at once, the pause comes after a full round", () => {
  const r = rig(["ws://home/ws", "ws://tower/ws"]);
  r.sockets[0].close();                                    // never opened (503 / no route)
  assert.equal(r.retry().ms, 0);
  r.retry().fn();
  assert.equal(r.sockets[1].url, "ws://tower/ws");
  r.sockets[1].close();
  const w1 = r.retry().ms;
  assert.ok(w1 >= 700 && w1 <= 1000, w1);
  r.retry().fn();
  r.sockets[2].close(); r.retry().fn();
  r.sockets[3].close();
  const w2 = r.retry().ms;
  assert.ok(w2 >= 1400 && w2 <= 2000, w2);                 // the second round waits longer
});

test("page hidden then visible again starts from the first delay", () => {
  const r = rig(["ws://pico/ws"]);
  for (let i = 0; i < 4; i++) { const s = r.sockets[r.sockets.length - 1]; s.open(); s.close(); r.retry().fn(); }
  r.document.visibilityState = "hidden";
  r.listeners.visibilitychange();
  r.document.visibilityState = "visible";
  const n = r.sockets.length;
  r.listeners.visibilitychange();                          // connects again at once
  assert.equal(r.sockets.length, n + 1);
  r.sockets[n].close();
  const w = r.retry().ms;
  assert.ok(w >= 700 && w <= 1000, w);
});
