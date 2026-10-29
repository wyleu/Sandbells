// node --test changes/bells/js_tests/  -- farm_status.js: sandswing /status deltas
// (?since=<status_version>&boot=<boot_id>): merged into the last full document.
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "static", "js");
const SRC = fs.readFileSync(path.join(JS, "farm_status.js"), "utf8");
const RD_SRC = fs.readFileSync(path.join(JS, "reconnect_delay.js"), "utf8");

const sec = (id, v) => ({ id, title: id, items: [{ key: "v", label: "V", value: v }] });
const FULL = { schema: "sand.status/v1", family: "sandswing", name: "Sandswing", level: "ok",
  summary: "one", status_version: 4, boot_id: "b007", full: true,
  sections: [sec("network", "a"), sec("time", "b"), sec("tower", "inactive")] };
const DELTA = { schema: "sand.status/v1", delta: true, since: 4, status_version: 5, boot_id: "b007",
  full: false, order: ["network", "tower", "extra"], head: { summary: "two", level: "warn" },
  sections: [sec("tower", "active"), sec("extra", "new")], removed: ["time"] };

function el(id) {
  return { id, textContent: "", className: "", children: [], style: {},
    set innerHTML(v) { this.children = []; }, get innerHTML() { return ""; },
    appendChild(c) { this.children.push(c); }, setAttribute() {}, addEventListener() {},
    get firstChild() { return this.children[0] || { textContent: "" }; } };
}

function rig(answers) {
  const els = { "farm-main": el("farm-main"), "farm-summary": el("farm-summary"),
    "farm-level": el("farm-level"), "farm-ident": el("farm-ident") };
  const ticks = [];
  const urls = [];
  const document = {
    visibilityState: "visible", cookie: "",
    getElementById: (id) => els[id] || null, querySelector: () => null,
    createElement: (t) => el(t), createTextNode: (t) => ({ textContent: t }), addEventListener() {},
  };
  const win = {};
  let n = 0;
  const sandbox = {
    window: win, document, console, WebSocket: class { send() {} close() {} },
    fetch: (u) => { urls.push(u); const a = answers[Math.min(n++, answers.length - 1)];
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(JSON.parse(JSON.stringify(a))) }); },
    setInterval: (fn) => { ticks.push(fn); return 1; },
    setTimeout: () => 1, clearTimeout() {}, clearInterval() {},
    Date, JSON, Math, parseInt, String, Error, Promise, encodeURIComponent, decodeURIComponent,
    location: { pathname: "/", protocol: "http:", host: "h" },
  };
  vm.createContext(sandbox);
  vm.runInContext(RD_SRC, sandbox);
  vm.runInContext(SRC, sandbox);
  win.FarmStatus.start({ kind: "sandswing", id: "x", statusUrl: "http://192.168.0.81/status", wsUrls: [] });
  const settle = async () => { for (let i = 0; i < 6; i++) await new Promise((r) => setImmediate(r)); };
  return { els, urls, win, settle, tick: async () => { ticks[0](); await settle(); } };
}

const titles = (r) => r.els["farm-main"].children.map((c) => c.children[0].textContent);

test("mergeStatus: head fields, changed sections, order and removed", () => {
  const r = rig([FULL]);
  const m = r.win.FarmStatus.merge(FULL, DELTA);
  assert.equal(m.summary, "two");
  assert.equal(m.level, "warn");
  assert.equal(m.status_version, 5);
  assert.deepEqual(m.sections.map((s) => s.id), ["network", "tower", "extra"]);
  assert.equal(m.sections[1].items[0].value, "active");
  assert.equal(m.sections[0], FULL.sections[0]);           // unchanged section kept as it was
  assert.equal(r.win.FarmStatus.merge(FULL, Object.assign({}, DELTA, { since: 3 })), null);
  assert.equal(r.win.FarmStatus.merge(FULL, Object.assign({}, DELTA, { boot_id: "other" })), null);
});

test("the page asks since=0 first, then since=<version>&boot=<id>, and shows the merged doc", async () => {
  const r = rig([FULL, DELTA]);
  await r.settle();
  assert.match(r.urls[0], /&since=0&boot=$/);
  await r.tick();
  assert.match(r.urls[1], /&since=4&boot=b007$/);
  assert.deepEqual(titles(r), ["network", "tower", "extra"]);
  assert.equal(r.els["farm-summary"].textContent, "two");
});

test("a delta that does not follow on (Pico restarted) fetches the whole document at once", async () => {
  const restarted = Object.assign({}, DELTA, { boot_id: "c0ffee" });
  const fresh = Object.assign({}, FULL, { boot_id: "c0ffee", status_version: 1, summary: "fresh" });
  const r = rig([FULL, restarted, fresh]);
  await r.settle();
  await r.tick();
  assert.equal(r.urls.length, 3);
  assert.match(r.urls[2], /&since=0&boot=b007$/);           // version forgotten: whole document
  assert.equal(r.els["farm-summary"].textContent, "fresh");
});

test("a held 'again' answer keeps the doc and says why", async () => {
  const r = rig([FULL, { schema: "sand.status/v1", held: "again", tower: "inactive", level: "ok",
    sections: [sec("tower", "inactive")] }]);
  await r.settle();
  await r.tick();
  assert.deepEqual(titles(r), ["network", "time", "tower"]);
  assert.match(r.els["farm-summary"].textContent, /^Status paused \(again\)/);
});
