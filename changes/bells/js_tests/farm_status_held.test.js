// node --test changes/bells/js_tests/  -- farm_status.js: a sandswing that is ringing answers
// /status with a tiny "held" sand.status/v1 document; the page must not call it offline.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "static", "js");
const SRC = fs.readFileSync(path.join(JS, "farm_status.js"), "utf8");
const RD_SRC = fs.readFileSync(path.join(JS, "reconnect_delay.js"), "utf8");

const FULL = { schema: "sand.status/v1", family: "sandswing", name: "Sandswing", level: "ok",
  summary: "all well", sections: [{ id: "net", title: "Network", items: [{ key: "ip", label: "IP", value: "192.168.0.81" }] }] };
const HELD = { schema: "sand.status/v1", family: "sandswing", held: "ringing", tower: "active",
  retry_after_s: 15, level: "ok", summary: "Ringing (active): full status paused so strokes have the link",
  sections: [{ id: "tower", title: "Tower", items: [{ key: "tower", label: "Tower", value: "active", level: "ok" }] }] };

function el(id) {
  return { id, textContent: "", className: "", innerHTML: "", children: [], style: {},
    appendChild(c) { this.children.push(c); }, setAttribute() {}, addEventListener() {},
    get firstChild() { return this.children[0] || { textContent: "" }; } };
}

function rig(answers) {
  const els = { "farm-main": el("farm-main"), "farm-summary": el("farm-summary"),
    "farm-level": el("farm-level"), "farm-ident": el("farm-ident") };
  const ticks = [];
  const document = {
    visibilityState: "visible", cookie: "",
    getElementById: (id) => els[id] || null,
    querySelector: () => null,
    createElement: (t) => el(t),
    createTextNode: (t) => ({ textContent: t }),
    addEventListener() {},
  };
  const win = {};
  let n = 0;
  const sandbox = {
    window: win, document, console,
    WebSocket: class { send() {} close() {} },
    fetch: () => { const a = answers[Math.min(n++, answers.length - 1)];
      return Promise.resolve({ ok: a.status === 200, status: a.status, json: () => Promise.resolve(a.body) }); },
    setInterval: (fn) => { ticks.push(fn); return 1; },
    setTimeout: () => 1, clearTimeout() {}, clearInterval() {},
    Date, JSON, Math, parseInt, String, Error, Promise, encodeURIComponent, decodeURIComponent,
    location: { pathname: "/", protocol: "http:", host: "h" },
  };
  vm.createContext(sandbox);
  vm.runInContext(RD_SRC, sandbox);
  vm.runInContext(SRC, sandbox);
  win.FarmStatus.start({ kind: "sandswing", id: "x", statusUrl: "http://192.168.0.81/status", wsUrls: [] });
  const settle = () => new Promise((r) => setImmediate(r));
  return { els, tick: async () => { ticks[0](); await settle(); await settle(); }, settle };
}

test("a held answer after a full one keeps the full status and says ringing, not offline", async () => {
  const r = rig([{ status: 200, body: FULL }, { status: 200, body: HELD }, { status: 200, body: FULL }]);
  await r.settle(); await r.settle();                      // the first poll: full
  const shown = r.els["farm-main"].children.length;
  assert.ok(shown > 0);
  await r.tick();                                          // held
  assert.equal(r.els["farm-main"].children.length, shown); // not replaced
  assert.match(r.els["farm-summary"].textContent, /^Ringing \(active\): status paused/);
  assert.doesNotMatch(r.els["farm-summary"].textContent, /Offline/);
  assert.doesNotMatch(r.els["farm-level"].className, /error|warn/);
  await r.tick();                                          // tower inactive: full again
  assert.equal(r.els["farm-summary"].textContent, "all well");
});

test("a held answer with nothing before it renders the Tower section", async () => {
  const r = rig([{ status: 200, body: HELD }]);
  await r.settle(); await r.settle();
  assert.equal(r.els["farm-main"].children.length, 1);
  assert.match(r.els["farm-summary"].textContent, /Ringing/);
});
