// node --test changes/bells/js_tests/  -- the pure helpers of power.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const pw = require(path.join(__dirname, "..", "static", "js", "power.js"));

test("the confirm names the machine and says what will happen", () => {
  const r = pw.confirmInfo("reboot", "sandbells2");
  assert.equal(r.yes, "Yes, reboot sandbells2 now");
  assert.match(r.note, /Reboots sandbells2 only/);
  assert.match(r.note, /offline for about a minute/);
  const s = pw.confirmInfo("poweroff", "sandbells2");
  assert.equal(s.yes, "Yes, shut down sandbells2");
  assert.match(s.note, /stays off until its power is switched off and on again/);
});

test("the confirm lapses after 5 s", () => {
  assert.equal(pw.CONFIRM_S, 5);
  assert.equal(pw.secondsLeft(1000, 1000), 5);
  assert.equal(pw.secondsLeft(1000, 2500), 4);
  assert.equal(pw.secondsLeft(1000, 5999), 1);
  assert.equal(pw.secondsLeft(1000, 6000), 0);
  assert.equal(pw.secondsLeft(1000, 9000), 0);
});

test("what the page says once accepted", () => {
  assert.equal(pw.acceptedText("reboot", "sandbells"), "Rebooting sandbells… reconnect shortly");
  assert.match(pw.acceptedText("poweroff", "sandbells"), /^Shutting down sandbells… wait for the green light/);
});

test("after a reboot the page waits for the new boot", () => {
  assert.equal(pw.pollDecision("old", false, null), "wait");                       // not answering
  assert.equal(pw.pollDecision("old", true, null), "wait");
  assert.equal(pw.pollDecision("old", false, { ok: true, boot_id: "old" }), "wait"); // still the old boot
  assert.equal(pw.pollDecision("old", true, { ok: true, boot_id: "old" }), "wait");
  assert.equal(pw.pollDecision("old", false, { ok: true, boot_id: "new" }), "back");
  assert.equal(pw.pollDecision("", false, { ok: true, boot_id: "" }), "wait");       // boot id unknown: need a failure first
  assert.equal(pw.pollDecision("", true, { ok: true, boot_id: "" }), "back");
  assert.equal(pw.pollDecision("old", false, { ok: false }), "wait");
});

test("error text", () => {
  assert.equal(pw.errorText({ ok: false, error: "reboot is not enabled on x" }, 503), "Not done: reboot is not enabled on x");
  assert.equal(pw.errorText(null, 403), "Not done: HTTP 403");
});
