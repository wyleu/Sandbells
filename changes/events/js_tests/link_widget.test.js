// node --test changes/events/js_tests/  -- pure helpers of link_widget.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const lw = require(path.join(__dirname, "..", "templates", "events", "link_widget.js"));

test("panel colours are scaled up, black stays dark", () => {
  assert.equal(lw.cssColour([0, 32, 0]), "rgb(0,255,0)");
  assert.equal(lw.cssColour([40, 20, 0]), "rgb(255,128,0)");
  assert.equal(lw.cssColour([0, 0, 0]), "#222");
  assert.equal(lw.cssColour(null), "#222");
});

test("ago", () => {
  assert.equal(lw.ago(null), "never");
  assert.equal(lw.ago(4999), "4 s");
  assert.equal(lw.ago(125000), "2 min 5 s");
});

test("sandmon NO Lock shows from the stratum the Pico saw", () => {
  const body = { sync: "stale", time: { srv: "10.42.0.1", stratum: 1,
    peer: { srv: "10.42.0.1", stratum: 16, leap: 3 },
    last: { ok: false, why: "server not synchronised (stratum 16, leap 3)" } } };
  const line = lw.timeLine(body);
  assert.match(line, /^time: holdover/);
  assert.match(line, /10\.42\.0\.1 NOT LOCKED \(stratum 16\)/);
  assert.equal(lw.syncClass(body), "warn");
  assert.equal(lw.syncClass({ sync: "unsynced" }), "bad");
  assert.match(lw.timeLine({ sync: "synced", time: { peer: { srv: "10.42.0.1", stratum: 1, leap: 0 } } }),
               /synced · 10\.42\.0\.1 stratum 1$/);
});

test("view: lost greys the LEDs' source and says why", () => {
  const v = lw.view({ verdict: "lost", why: "no heartbeat for 31 s", rx_age_ms: 31000,
    hb_age_ms: 31000, ingest: { reconnects: 2, last_drop_reason: "peer silent 20 s" },
    pico: { body: { panel: [[0, 32, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [0, 0, 0], [40, 0, 0]],
                    panel_state: ["ws_client", "empty", "empty", "empty", "empty", "heartbeat_nosync"],
                    sync: "unsynced", net: { drops: 1 } } } });
  assert.equal(v.cls, "lost");
  assert.equal(v.headline, "LOST");
  assert.match(v.detail, /reconnects 2/);
  assert.equal(v.drop, "last drop: peer silent 20 s");
  assert.equal(v.leds[0], "rgb(0,255,0)");
  assert.equal(v.leds[5], "rgb(255,0,0)");
});

test("channels: kind under ch 1-4 LEDs, why for fault and trigger", () => {
  const body = {
    panel_state: ["ws_client", "trigger", "fault", "empty", "head_new", "heartbeat"],
    chan: [["trigger", "trigger plug (test switch): Orange-Green/White link, switch open... (r50 0.99, l50 0.83)"],
           ["fault", "Orange shorted to ground or crossed onto Green/White (15 R)... (l50 0.12 < 0.20)"],
           ["empty", null], ["head_new", null], ["empty", null], ["fault", "partial loopback (B strap only)"],
           ["empty", null], ["empty", null]] };
  const c = lw.channels(body);
  assert.deepEqual(c.kinds, ["trigger", "FAULT", "empty", "new head"]);
  assert.equal(c.notes.length, 3);
  assert.deepEqual(c.notes[1], { cls: "bad",
    text: "ch 2 FAULT: Orange shorted to ground or crossed onto Green/White (15 R)... (l50 0.12 < 0.20)" });
  assert.equal(c.notes[0].cls, "trig");
  assert.match(c.notes[2].text, /^ch 6 FAULT: partial/);
  const v = lw.view({ verdict: "ok", pico: { body } });
  assert.deepEqual(v.kinds, c.kinds);
});

test("channels: older firmware (no chan) falls back to panel_state names", () => {
  const c = lw.channels({ panel_state: ["ws_client", "loopback", "response", "empty", "fault", "heartbeat"] });
  assert.deepEqual(c.kinds, ["loopback", "stroke", "empty", "FAULT"]);
  assert.deepEqual(c.notes, []);
  assert.deepEqual(lw.channels(null), { kinds: ["", "", "", ""], notes: [] });
});
