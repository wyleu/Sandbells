// page_requests.js -- not a node --test file: a harness the Django test
// events/tests_strokes_page.py runs.  It reads a rendered page on stdin, runs
// every script on it (inline, and <script src="/static/..."> found under the
// static dirs given as arguments) against a small fake DOM, fake timers and a
// fake fetch / WebSocket / XMLHttpRequest / EventSource, for SECONDS of page
// time, and prints JSON: every URL fetched, every socket opened, script errors.
// Usage:  node page_requests.js [static_dir ...] < page.html
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SECONDS = 120;
const html = fs.readFileSync(0, "utf8");
const staticDirs = process.argv.slice(2);

// ---- fake DOM: elements by id (with their data-* attributes), classes counted
function attrsOf(tag) {
  const out = {};
  tag.replace(/([a-zA-Z_:][-a-zA-Z0-9_:.]*)="([^"]*)"/g, (_, k, v) => { out[k] = v; return ""; });
  return out;
}
function camel(s) { return s.replace(/-([a-z])/g, (_, c) => c.toUpperCase()); }
const idTags = {};
html.replace(/<[a-zA-Z][^>]*\sid="([^"]+)"[^>]*>/g, (tag, id) => { idTags[id] = attrsOf(tag); return ""; });

function makeEl(attrs) {
  attrs = attrs || {};
  const dataset = {};
  Object.keys(attrs).forEach((k) => { if (k.startsWith("data-")) dataset[camel(k.slice(5))] = attrs[k]; });
  const el = {
    dataset, style: {}, className: attrs.class || "", textContent: "", innerHTML: "", title: "",
    hidden: false, colSpan: 1, children: [], attributes: Object.assign({}, attrs),
    get rows() { return this.children; },
    get firstChild() { return this.children[0] || null; },
    get outerHTML() { return "<div>" + this.textContent + "</div>"; },
    appendChild(c) { this.children.push(c); return c; },
    insertBefore(c, ref) {
      const i = this.children.indexOf(ref);
      if (i < 0) this.children.push(c); else this.children.splice(i, 0, c);
      return c;
    },
    removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); return c; },
    deleteRow(i) { this.children.splice(i, 1); },
    setAttribute(k, v) { this.attributes[k] = String(v); },
    getAttribute(k) { return k in this.attributes ? this.attributes[k] : null; },
    addEventListener() {}, removeEventListener() {},
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; },
    querySelectorAll(sel) {
      const m = /^\.([-\w]+)$/.exec(sel);
      if (!m) return [];
      const n = (html.match(new RegExp('class="[^"]*\\b' + m[1] + '\\b', "g")) || []).length;
      return Array.from({ length: n }, () => makeEl({ class: m[1] }));
    },
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
  };
  return el;
}
const byId = {};
const document = {
  visibilityState: "visible", hidden: false,
  getElementById(id) {
    if (!(id in idTags)) return null;
    return byId[id] || (byId[id] = makeEl(idTags[id]));
  },
  createElement(tag) { return makeEl({}); },
  createTextNode(t) { return makeEl({}); },
  querySelector(sel) { return makeEl({}).querySelector(sel); },
  querySelectorAll(sel) { return makeEl({}).querySelectorAll(sel); },
  addEventListener() {}, removeEventListener() {},
  body: makeEl({}),
};

// ---- fake time
let now = Date.UTC(2026, 9, 29, 15, 0, 0);
const RealDate = Date;
class FakeDate extends RealDate {
  constructor(...a) { if (a.length) super(...a); else super(now); }
  static now() { return now; }
}
let timers = [], nextId = 1;
function addTimer(fn, ms, every) {
  const id = nextId++;
  timers.push({ id, at: now + Math.max(0, +ms || 0), fn, every: every ? Math.max(1, +ms || 1) : 0 });
  return id;
}
function clearTimer(id) { timers = timers.filter((t) => t.id !== id); }

// ---- fake network
const fetches = [], sockets = [], errors = [];
let seq = 0;
function strokeEvent(i) {
  return { id: i, type: "stroke", src: "sandswing", boot_id: "b1", ch: 1, seq: i,
           at_ms: now - 50, at_hms_ms: "15:00:00.000", time_ok: true, bell_label: "Bell 1",
           interval_ms: i === 1 ? null : 2000 + ((i * 37) % 300) - 150,
           acc: "ms", sync: "synced", err_ms: 0.4 };
}
function answer(url) {
  const p = new URL(url, "http://sandbells.local").pathname;
  if (p === "/events/api/since/") {
    const evs = [];
    for (let k = 0; k < 2; k++) evs.push(strokeEvent(++seq));
    return { status: 200, body: { server_ms: now, latest_id: seq, events: evs,
             ring: { strokes: seq, start_hms: "15:00:00", channels: [],
                     bells: [{ bell: 1, per_ch: { 1: seq } }] } } };
  }
  if (p === "/events/api/link/") {
    return { status: 200, body: { verdict: "ok", why: "connected", rx_age_ms: 100, hb_age_ms: 900,
             ingest: { reconnects: 0 }, pico: null } };
  }
  return { status: 404, body: { error: "not in the harness" } };
}
function fakeFetch(url) {
  fetches.push(String(url));
  const a = answer(String(url));
  return Promise.resolve({ ok: a.status === 200, status: a.status,
                           json: () => Promise.resolve(a.body) });
}
function FakeSocket(url) { sockets.push({ kind: "WebSocket", url: String(url) }); this.readyState = 0;
  this.send = () => {}; this.close = () => {}; }
function FakeES(url) { sockets.push({ kind: "EventSource", url: String(url) }); this.close = () => {}; }
function FakeXHR() { this.open = (m, url) => sockets.push({ kind: "XMLHttpRequest", url: String(url) });
  this.send = () => {}; this.setRequestHeader = () => {}; this.abort = () => {}; }

const sandbox = {
  document, console: { log() {}, warn() {}, error() {}, info() {}, debug() {} },
  Date: FakeDate, Math, JSON, Intl, URL, Promise, AbortController,
  setTimeout: (f, ms) => addTimer(f, ms, false), clearTimeout: clearTimer,
  setInterval: (f, ms) => addTimer(f, ms, true), clearInterval: clearTimer,
  requestAnimationFrame: (f) => addTimer(() => f(now), 16, false), cancelAnimationFrame: clearTimer,
  fetch: fakeFetch, WebSocket: FakeSocket, EventSource: FakeES, XMLHttpRequest: FakeXHR,
  navigator: { sendBeacon: (url) => { fetches.push(String(url)); return true; } },
  sessionStorage: { getItem() { return null; }, setItem() {} },
  localStorage: { getItem() { return null; }, setItem() {} },
  location: { href: "http://sandbells.local/", reload() {} },
  JSON_parse: JSON.parse,
};
sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.addEventListener = () => {};
vm.createContext(sandbox);

// ---- the page's scripts, in order
const scripts = [], srcs = [];
html.replace(/<script([^>]*)>([\s\S]*?)<\/script>/g, (_, attrs, body) => {
  const src = attrsOf(attrs).src;
  if (src) {
    srcs.push(src);
    const rel = src.split("?")[0].replace(/^\/static\//, "");
    const file = staticDirs.map((d) => path.join(d, rel)).find((f) => fs.existsSync(f));
    if (file) scripts.push({ name: src, code: fs.readFileSync(file, "utf8") });
    else errors.push("script not found: " + src);
  } else {
    scripts.push({ name: "inline", code: body });
  }
  return "";
});

function run(name, fn) {
  try { fn(); } catch (e) { errors.push(name + ": " + (e && e.stack ? e.stack.split("\n")[0] : e)); }
}
const flush = () => new Promise((r) => setImmediate(r));
process.on("unhandledRejection", (e) => errors.push("unhandled: " + e));

(async () => {
  scripts.forEach((s) => run(s.name, () => vm.runInContext(s.code, sandbox, { filename: s.name })));
  const end = now + SECONDS * 1000;
  for (let guard = 0; guard < 100000; guard++) {
    for (let k = 0; k < 5; k++) await flush();
    if (!timers.length) break;
    timers.sort((a, b) => a.at - b.at || a.id - b.id);
    const t = timers[0];
    if (t.at > end) break;
    now = t.at;
    if (t.every) t.at = now + t.every; else timers.shift();
    run("timer", t.fn);
  }
  const rows = byId["live-rows"] ? byId["live-rows"].children.length : 0;
  process.stdout.write(JSON.stringify({ fetches, sockets, srcs, errors, rows }));
})();
