// node --test changes/sandtest/js_tests/  -- the pure helpers of sandtest.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const st = require(path.join(__dirname, "..", "static", "js", "sandtest.js"));

test("ages", () => {
  assert.equal(st.fmtAge(null), "never");
  assert.equal(st.fmtAge(400), "0.4 s");
  assert.equal(st.fmtAge(42000), "42 s");
  assert.equal(st.fmtAge(125000), "2 min 5 s");
});

test("connection state: waiting, connected, stale, unreachable", () => {
  assert.deepEqual(st.connState(1000, null, ""), { cls: "wait", text: "waiting for the rig…", stale: false });
  const bad = st.connState(1000, null, "cannot reach x: refused");
  assert.equal(bad.cls, "wait");
  assert.match(bad.text, /not reachable: cannot reach x: refused/);
  const ok = st.connState(10000, 9400, "");
  assert.equal(ok.cls, "ok");
  assert.equal(ok.stale, false);
  assert.match(ok.text, /connected · status 0\.6 s old/);
  const old = st.connState(20000, 9400, "");       // no failure reported, but nothing new for 10 s
  assert.equal(old.cls, "busy");
  assert.equal(old.stale, true);
  assert.match(old.text, /last good status 11 s ago/);
  const err = st.connState(10000, 9400, "no answer from x within 2 s");
  assert.equal(err.stale, true);
  assert.match(err.text, /NO ANSWER · last good status 0\.6 s ago · no answer from x/);
});

test("the heads table: both faces, window highlight", () => {
  const sweep = { faces: { mirror: 0, reflector: 180 }, in_window: [3], hit: true, window_face: "reflector",
                  heads: { "10": { angle_deg: 5, width_deg: 2 }, "3": { angle_deg: 12, width_deg: 4 }, "1": { angle_deg: -20, width_deg: 4 } } };
  const rows = st.headRows(sweep);
  assert.deepEqual(rows.map(r => r.head), [1, 3, 10]);
  assert.equal(rows[1].mirrorAt, 12);
  assert.equal(rows[1].reflectorAt, 192);
  assert.deepEqual(rows.map(r => r.inWindow), [false, true, false]);
  assert.deepEqual(st.headRows(null), []);
  assert.deepEqual(st.headRows({ heads: { "2": { angle_deg: 1, width_deg: 1 } } })[0].mirrorAt, null);
  assert.equal(st.windowFlag(sweep).cls, "hit");
  assert.equal(st.windowFlag(sweep).text, "IN WINDOW: head 3 (reflector)");
  assert.equal(st.windowFlag({ hit: false, in_window: [] }).cls, "clear");
  assert.equal(st.windowFlag(undefined).cls, "none");
});

test("press and play commands", () => {
  assert.deepEqual(st.buildCommand("press", { channel: "3", press_ms: "120" }).cmd, { cmd: "press", channel: 3, press_ms: 120 });
  assert.deepEqual(st.buildCommand("press", { channel: "3", press_ms: "" }).cmd, { cmd: "press", channel: 3 });
  assert.match(st.buildCommand("press", { channel: "9" }).error, /channel must be at most 8/);
  assert.match(st.buildCommand("press", { channel: "" }).error, /channel is needed/);
  assert.match(st.buildCommand("press", { channel: "1.5" }).error, /whole number/);
  assert.deepEqual(st.buildCommand("play", { pattern: " 13425678 ", interval_ms: "400", press_ms: "120", repeat: "3" }).cmd,
    { cmd: "play", pattern: "13425678", interval_ms: 400, press_ms: 120, repeat: 3 });
  assert.equal(st.buildCommand("play", { pattern: "12345678  21436587" }).cmd.pattern, "12345678 21436587");
  assert.equal(st.buildCommand("play", { pattern: "ROUNDS" }).cmd.pattern, "rounds");
  assert.match(st.buildCommand("play", { pattern: "129" }).error, /pattern must be/);
  assert.match(st.buildCommand("play", { pattern: "" }).error, /pattern is needed/);
  assert.match(st.buildCommand("play", { pattern: "12", repeat: "0" }).error, /repeat must be at least 1/);
});

test("stress, sweep, scan, visit", () => {
  assert.deepEqual(st.buildCommand("stress", { seed: "7", seconds: "30" }).cmd, { cmd: "stress", seed: 7, seconds: 30 });
  assert.deepEqual(st.buildCommand("sweep", { from_deg: "-30", to_deg: "30", speed_dps: "10", dwell_ms: "500", cycles: "0" }).cmd,
    { cmd: "sweep", mode: "sweep", from_deg: -30, to_deg: 30, speed_dps: 10, dwell_ms: 500, cycles: 0 });
  assert.match(st.buildCommand("sweep", { from_deg: "-30" }).error, /to deg is needed/);
  assert.match(st.buildCommand("sweep", { from_deg: "a", to_deg: "1" }).error, /must be a number/);
  assert.match(st.buildCommand("sweep", { from_deg: "0", to_deg: "1", speed_dps: "0" }).error, /speed dps must be at least 0.05/);
  assert.deepEqual(st.buildCommand("scan", { speed_dps: "3", dwell_ms: "300", cycles: "1", face: "" }).cmd,
    { cmd: "sweep", mode: "scan", speed_dps: 3, dwell_ms: 300, cycles: 1 });
  assert.deepEqual(st.buildCommand("visit", { head: "3", dwell_ms: "500", face: "reflector" }).cmd,
    { cmd: "sweep", mode: "visit", head: 3, dwell_ms: 500, face: "reflector" });
  assert.match(st.buildCommand("visit", { head: "3", face: "front" }).error, /face must be/);
});

test("menace sends allow_hits only as the page's checkbox says, safe by default", () => {
  assert.deepEqual(st.buildCommand("menace", { seed: "7", seconds: "60", face: "", allow_hits: false }).cmd,
    { cmd: "sweep", mode: "menace", seed: 7, seconds: 60, allow_hits: false });
  assert.equal(st.buildCommand("menace", { seed: "7", allow_hits: true }).cmd.allow_hits, true);
  assert.equal(st.buildCommand("menace", { seed: "7" }).cmd.allow_hits, undefined);
});

test("profile needs a head and a face", () => {
  assert.deepEqual(st.buildCommand("profile", { head: "3", face: "reflector", span_deg: "10", step_deg: "0.5", dwell_ms: "2000", passes: "1" }).cmd,
    { cmd: "sweep", mode: "profile", head: 3, face: "reflector", span_deg: 10, step_deg: 0.5, dwell_ms: 2000, passes: 1 });
  assert.match(st.buildCommand("profile", { head: "3", face: "" }).error, /face is needed/);
  assert.match(st.buildCommand("profile", { head: "", face: "mirror" }).error, /head is needed/);
  assert.match(st.buildCommand("profile", { head: "3", face: "mirror", step_deg: "0" }).error, /step deg must be at least 0.01/);
  assert.equal(st.buildCommand("nope", {}).error, "unknown command nope");
});

test("numbers shown to the eye", () => {
  assert.equal(st.num(12.5, 2), "12.50");
  assert.equal(st.num(30), "30");
  assert.equal(st.num(null, 1), "–");
  assert.equal(st.num("x", 1), "–");
});
