// node --test changes/bells/js_tests/  -- lineup.js (the sandheads line-up) inside align.js, USB path
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "static", "js");
const read = (f) => fs.readFileSync(path.join(JS, f), "utf8");
const SCHEMA = "sand.panel/v1";
const FULL = 65535;
const OPT = { plateau_frac: 0.05, margin_frac: 0.2, min_range_v: 0.05, slots: 8, labelMax: 8 };

class Ctx { constructor() { this.calls = []; } }
for (const m of ["fillRect", "moveTo", "lineTo", "stroke", "beginPath", "fillText"]) {
  Ctx.prototype[m] = function (...a) { this.calls.push([m, ...a]); };
}
class El {
  constructor(tag) {
    this.tag = tag; this.children = []; this.className = ""; this.textContent = ""; this.value = "";
    this.attrs = {}; this.handlers = {}; this.disabled = false; this.id = "";
    this.clientWidth = 400; this.clientHeight = 140; this.width = 0; this.height = 0; this.ctx = new Ctx();
  }
  appendChild(c) { this.children.push(c); return c; }
  setAttribute(k, v) { this.attrs[k] = v; }
  addEventListener(ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); }
  fire(ev) { for (const f of this.handlers[ev] || []) f(); }
  click() { this.fire("click"); }
  getContext() { return this.ctx; }
  set innerHTML(v) { this.children = []; }
  find(pred, out = []) { if (pred(this)) out.push(this); for (const c of this.children) c.find(pred, out); return out; }
}

function rig() {
  const ids = {};
  for (const id of ["align-main", "align-heads", "align-link", "align-tower"]) ids[id] = new El("x");
  const xhrs = [];
  class XHR {
    constructor() { this.headers = {}; xhrs.push(this); }
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader(k, v) { this.headers[k] = v; }
    send(body) { this.body = body == null ? null : JSON.parse(body); }
    reply(status, obj) { this.status = status; this.responseText = JSON.stringify(obj); if (this.onload) this.onload(); }
  }
  const timers = [];
  const win = { XMLHttpRequest: XHR, addEventListener() {}, location: { hash: "" },
                sessionStorage: { getItem: () => null, setItem() {} }, history: { replaceState() {} } };
  const document = { visibilityState: "visible", cookie: "csrftoken=tok", getElementById: (id) => ids[id] || null,
                     createElement: (t) => new El(t), addEventListener() {} };
  const sandbox = { window: win, document, WebSocket: function () {}, console,
    setInterval: (fn, ms) => { timers.push({ fn, ms, kind: "i" }); return timers.length; },
    setTimeout: (fn, ms) => { timers.push({ fn, ms, kind: "t" }); return timers.length; },
    clearTimeout() {}, clearInterval() {}, Date, JSON, Math, parseInt, String };
  vm.createContext(sandbox);
  vm.runInContext(read("reconnect_delay.js"), sandbox);
  vm.runInContext(read("lineup.js"), sandbox);
  vm.runInContext(read("align.js"), sandbox);
  sandbox.window.Align.start({ via: "serial", activeKinds: ["head_new", "head_old"], lineup: OPT,
    serial: { cmdUrl: "/c/", pollUrl: "/p/", logUrl: "/l/", sweepLogUrl: "/s/", pollMs: 400, liveMs: 3000 } });
  const r = { ids, xhrs, timers, win: sandbox.window };
  r.poll = (items, extra) => {
    const gets = xhrs.filter((x) => x.method === "GET");
    gets[gets.length - 1].reply(200, Object.assign({ running: true, connected: true, n: 0, items: [],
      heartbeat: { schema: SCHEMA, type: "heartbeat", body: { tower: (extra || {}).tower || "inactive",
                   chan: [["head_new"], ["head_old"], ["empty"]], pt: [1, 2.1, 0.01] } },
      midi: { running: true, connected: true, n: (r.n = (r.n || 0) + (items || []).length), items: items || [] } }, {}));
    timers.filter((t) => t.ms === 400 && t.kind === "i")[0].fn();
  };
  r.posts = () => xhrs.filter((x) => x.method === "POST" && x.url === "/c/").map((x) => x.body);
  r.logs = () => xhrs.filter((x) => x.method === "POST" && x.url === "/s/").map((x) => x.body);
  r.card = () => ids["align-main"].find((e) => e.tag === "section")[0];
  r.lineup = () => r.card().find((e) => e.className.split(" ")[0] === "lineup")[0];
  r.btn = (label) => r.card().find((e) => e.tag === "button" && e.textContent.indexOf(label) === 0)[0];
  r.cls = (c) => r.lineup().find((e) => e.className.split(" ")[0] === c)[0];
  r.msg = (type, body) => ({ schema: SCHEMA, type, body });
  r.unlock = () => timers.filter((t) => t.kind === "t" && t.ms === 400).forEach((t) => t.fn());
  return r;
}

const curve = [65535, 50000, 38000, 29000, 22000, 17000, 13000, 10000, 7600, 5800, 4400, 3400, 2600, 2000, 1500, 1310];
// PT flattens above ~10000 (the plateau), falls off below
const ptOf = (d) => +(2.2 * d / (d + 1000)).toFixed(3);
const points = curve.map((d, i) => ({ i, drv: d, ma: +(30 * d / FULL).toFixed(2), pt: ptOf(d), pt_span: 0.01 }));

test("suggest: lowest drive within plateau_frac of the full-drive PT, plus the margin; threshold in proportion", () => {
  const r = rig();
  const L = r.win.Lineup;
  const s = L.suggest(points, OPT, 20000);
  const top = ptOf(65535);
  const good = curve.filter((d) => Math.abs(ptOf(d) - top) <= top * OPT.plateau_frac);
  const low = Math.min(...good);
  assert.equal(s.drv, Math.round(low * 1.2));
  assert.ok(s.drv < 65535 / 2, "well under full drive");
  assert.ok(s.thr < 20000 && s.thr > 18000, String(s.thr));        // PT a little under the top
  assert.ok(s.ma > 0 && s.ma < 30 * s.drv / FULL + 0.5);
  // flat: nothing suggested, and says why
  const flat = L.suggest(points.map((p) => Object.assign({}, p, { pt: 1.5 })), OPT, 20000);
  assert.equal(flat.drv, null);
  assert.match(flat.why, /hardly changed/);
  assert.equal(L.suggest(points.slice(0, 2), OPT, 1).drv, null);
  // an old head (no threshold): drive only
  assert.equal(L.suggest(points, OPT, null).thr, null);
});

test("the line-up shows only on the PT head; a sweep fills the curve, suggests, and nothing changes until Use this", () => {
  const r = rig();
  r.poll([]);
  assert.deepEqual(r.posts().slice(0, 3), [{ cmd: "align", info: true }, { cmd: "align", saved: true },
                                           { cmd: "align", ch: 1, scope: true }]);
  assert.equal(r.lineup().className, "lineup");                     // head 1 has the PT wire
  r.poll([r.msg("align", { ch: 1, n: 1, bits: "80", thr: 20000, drv: 65535, tower: "inactive" })]);
  const go = r.btn("Find best brightness");
  assert.equal(go.disabled, false);
  r.cls("ltext").value = "H5";
  go.click();
  assert.deepEqual(r.posts().pop(), { cmd: "align", ch: 1, sweep: true });
  r.unlock();
  r.poll([r.msg("align_ack", { what: "sweep", ch: 1, ok: true, why: null, thr: 20000, drv: 65535, tower: "inactive" })]);
  assert.ok(r.btn("Stop"), "the big button is Stop while it runs");
  r.poll(points.slice(0, 8).map((p) => r.msg("align_sweep", Object.assign({ ch: 1 }, p))));
  r.poll(points.slice(8).map((p) => r.msg("align_sweep", Object.assign({ ch: 1 }, p))));
  assert.match(r.cls("lstatus").textContent, /16 readings/);
  assert.ok(r.cls("curve").ctx.calls.filter((c) => c[0] === "fillRect").length >= 16);
  const before = r.posts().length;
  r.poll([r.msg("align_ack", { what: "sweep_end", ch: 1, ok: true, why: null, thr: 20000, drv: 65535, tower: "inactive" })]);
  assert.equal(r.posts().length, before, "nothing sent at the end");
  assert.match(r.cls("lstatus").textContent, /Suggested: drive/);
  const sug = r.win.Lineup.suggest(points, OPT, 20000);
  // logged once with the label
  const log = r.logs();
  assert.equal(log.length, 1);
  assert.equal(log[0].label, "H5");
  assert.equal(log[0].points.length, 16);
  assert.equal(log[0].suggested_drv, sug.drv);
  const use = r.btn("Use this");
  assert.equal(use.disabled, false);
  use.click();
  assert.deepEqual(r.posts().pop(), { cmd: "align", ch: 1, use: [sug.drv, sug.thr] });
  r.unlock();
  r.poll([r.msg("align_ack", { what: "use", ch: 1, ok: true, why: null, thr: sug.thr, drv: sug.drv, tower: "inactive" })]);
  assert.match(r.cls("msg").textContent, /Now using drive/);
});

test("save for a picked channel with the label; saved values listed; forget takes two presses", () => {
  const r = rig();
  r.poll([]);
  r.cls("ltext").value = "H5";
  const sel = r.cls("lslot");
  sel.value = "3";
  sel.fire("change");
  const save = r.btn("Save for channel 3");
  assert.ok(save && !save.disabled);
  save.click();
  assert.deepEqual(r.posts().pop(), { cmd: "align", ch: 1, save: 3, label: "H5" });
  r.unlock();
  r.poll([r.msg("align_ack", { what: "save", ch: 1, ok: true, why: null, tower: "inactive" }),
          r.msg("align_slot", { ch: 3, saved: true, drv: 9000, thr: 19000, label: "H5" })]);
  assert.match(r.cls("msg").textContent, /Saved for channel 3/);
  const rows = r.cls("lsaved").children;
  assert.equal(rows.length, 1);
  assert.match(rows[0].children[1].textContent, /head H5/);
  const f = rows[0].children[3];
  f.click();
  assert.equal(r.posts().filter((p) => "forget" in p).length, 0);
  r.cls("lsaved").children[0].children[3].click();
  assert.deepEqual(r.posts().pop(), { cmd: "align", forget: 3 });
  r.poll([r.msg("align_slot", { ch: 3, saved: false, drv: null, thr: null, label: null })]);
  assert.match(r.cls("lsaved").children[0].textContent, /Nothing saved yet/);
});

test("errors stay on screen; a stroke stops the sweep and says the drive is back", () => {
  const r = rig();
  r.poll([]);
  r.btn("Find best brightness").click();
  r.unlock();
  r.poll([r.msg("align_ack", { what: "sweep", ch: 1, ok: false, why: "tower not quiet: strokes in progress" })]);
  assert.match(r.cls("msg").textContent, /Could not start: tower not quiet/);
  assert.match(r.cls("msg").className, /refused/);
  r.btn("Find best brightness").click();
  r.unlock();
  r.poll([r.msg("align_ack", { what: "sweep", ch: 1, ok: true, why: null }),
          r.msg("align_sweep", Object.assign({ ch: 1 }, points[0])),
          r.msg("align_ack", { what: "sweep_end", ch: 1, ok: false, why: "beam broken" })]);
  assert.match(r.cls("msg").textContent, /stopped: beam broken.*back as it was/);
  assert.equal(r.btn("Use this").disabled, true);
  r.poll([r.msg("align", { ch: 1, n: 1, bits: "80", tower: "inactive" })]);
  assert.match(r.cls("msg").textContent, /beam broken/);           // still there
  // a bad label comes back as a refused command
  r.poll([r.msg("align_ack", { what: "bad", ch: null, ok: false, why: "bad label" })]);
  assert.match(r.cls("msg").textContent, /Refused: bad label/);
  // older firmware: the sweep command itself is refused; the button comes back
  r.btn("Find best brightness").click();
  r.unlock();
  r.poll([r.msg("align_ack", { what: "bad", ch: null, ok: false, why: "bad command" })]);
  assert.match(r.cls("msg").textContent, /Could not start: bad command/);
  assert.ok(r.btn("Find best brightness"));
});

test("tower not quiet: the buttons wait; another head has no line-up", () => {
  const r = rig();
  r.poll([], { tower: "active" });
  r.poll([r.msg("align", { ch: 1, n: 1, bits: "80", tower: "active" })]);
  assert.equal(r.btn("Find best brightness").disabled, true);
  assert.equal(r.btn("Save for channel").disabled, true);
  assert.match(r.cls("lstatus").textContent, /Waiting for the tower/);
  r.ids["align-heads"].children[1].click();                        // head 2: no PT wire
  assert.equal(r.card().attrs["data-ch"], "2");
  assert.match(r.lineup().className, /hidden/);
});
