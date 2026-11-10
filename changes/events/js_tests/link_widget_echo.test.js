/* link_widget.js in a fake page: the LED echo poll (api/leds/) starts when
 * api/link/ says leds_live, paints the echo, stops when it is not live and
 * while the page is hidden.  Run: node --test events/js_tests/ */
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = fs.readFileSync(path.join(__dirname, "..", "templates", "events", "link_widget.js"), "utf8");
const LINK = "/events/api/link/", LEDS = "/events/api/leds/";

function el() {
  return { textContent: "", className: "", title: "", innerHTML: "", style: {},
           setAttribute() {} };
}

function page(replies) {
  const leds = [0, 1, 2, 3, 4, 5].map(el);
  const ids = {};
  const box = Object.assign(el(), {
    dataset: { url: LINK, poll: "2000", timeout: "4000", ledsUrl: LEDS, ledPoll: "250" },
    querySelectorAll: (q) => (q === ".lw-led" ? leds : []),
  });
  const timers = [];
  const calls = [];
  const doc = {
    hidden: false,
    getElementById: (id) => (id === "link-widget" ? box : (ids[id] = ids[id] || el())),
    createElement: el,
  };
  const ctx = {
    document: doc, window: {}, console,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout() {},
    fetch: (url) => {
      calls.push(url);
      const body = replies[url]();
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    },
  };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  return { leds, timers, calls, doc,
           async settle() { for (let i = 0; i < 10; i++) await new Promise(setImmediate); },
           async run(ms) {           // fire the pending timers of this period
             const all = timers.splice(0);
             all.filter((t) => t.ms !== ms).forEach((t) => timers.push(t));
             all.filter((t) => t.ms === ms).forEach((t) => t.fn());
             await this.settle();
           } };
}

const HB = { verdict: "midi", via: "udp", hb_live: true, hb_age_ms: 3000, midi: {},
             pico: { body: { panel: [[0, 32, 0], [0, 0, 24], [0, 0, 24], [0, 0, 24], [0, 0, 24], [8, 8, 8]],
                             panel_state: ["ws_client", "loopback", "loopback", "loopback", "loopback", "heartbeat"] } } };
const ECHO = { live: true, panel: [[0, 32, 0], [48, 48, 48], [0, 0, 24], [0, 0, 24], [0, 0, 24], [8, 8, 8]],
               panel_state: ["ws_client", "response", "loopback", "loopback", "loopback", "heartbeat"] };

test("echo: polled while leds_live, its colours shown, stops when not live", async () => {
  let link = Object.assign({}, HB, { leds_live: true }), leds = ECHO;
  const p = page({ [LINK]: () => link, [LEDS]: () => leds });
  await p.settle();
  assert.deepEqual(p.calls, [LINK, LEDS]);
  assert.equal(p.leds[1].style.background, "rgb(255,255,255)");     // the stroke's white
  assert.match(p.leds[1].title, /response/);
  await p.run(250);
  assert.deepEqual(p.calls, [LINK, LEDS, LEDS]);
  leds = { live: false, panel: null };
  await p.run(250);
  assert.equal(p.leds[1].style.background, "rgb(0,0,255)");         // back to the heartbeat's
  await p.run(250);
  assert.equal(p.calls.filter((u) => u === LEDS).length, 3);        // stopped
  assert.equal(p.timers.filter((t) => t.ms === 250).length, 0);
  link = Object.assign({}, HB, { leds_live: false });
  await p.run(2000);
  assert.equal(p.calls.filter((u) => u === LEDS).length, 3);        // not restarted
});

test("echo: paused while the page is hidden, restarted by the next link poll", async () => {
  const p = page({ [LINK]: () => Object.assign({}, HB, { leds_live: true }), [LEDS]: () => ECHO });
  await p.settle();
  p.doc.hidden = true;
  await p.run(250);
  assert.equal(p.calls.filter((u) => u === LEDS).length, 1);
  assert.equal(p.leds[1].style.background, "rgb(0,0,255)");
  p.doc.hidden = false;
  await p.run(2000);
  assert.equal(p.calls.filter((u) => u === LEDS).length, 2);
  assert.equal(p.leds[1].style.background, "rgb(255,255,255)");
});

test("echo: never without leds_live (one poll, no fast loop)", async () => {
  const p = page({ [LINK]: () => HB, [LEDS]: () => ECHO });
  await p.settle();
  assert.deepEqual(p.calls, [LINK]);
  assert.equal(p.leds[0].style.background, "rgb(0,255,0)");
});
