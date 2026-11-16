// node --test changes/bells/js_tests/  -- the pure helpers of chime_player.js
"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const cp = require(path.join(__dirname, "..", "static", "js", "chime_player.js"));

test("the status says where the music goes", () => {
  assert.equal(cp.playingTo({ midi_out: true, midi_port: "20:0", hdmi_audio: true }), "(MIDI 20:0, HDMI)");
  assert.equal(cp.playingTo({ midi_out: true, midi_port: "14:0", hdmi_audio: false }), "(MIDI 14:0)");
  assert.equal(cp.playingTo({ midi_out: false, midi_port: "", hdmi_audio: true }), "(HDMI)");
  assert.equal(cp.playingTo({ midi_out: false, hdmi_audio: false }), "(silent)");
  assert.equal(cp.playingTo(undefined), "(silent)");
});

test("the port menu: automatic, the ports, a saved port that is gone", () => {
  const ports = [{ id: "14:0", client: "Midi Through" }, { id: "20:0", client: "Roland" }];
  assert.deepEqual(cp.portChoices(ports, ""), [["", cp.PORT_AUTO], ["14:0", "14:0 Midi Through"], ["20:0", "20:0 Roland"]]);
  assert.deepEqual(cp.portChoices(ports, "20:0").length, 3);
  assert.deepEqual(cp.portChoices([], "20:0"), [["", cp.PORT_AUTO], ["20:0", "20:0 (not there now)"]]);
});

test("the dot's event is the last one at or before now", () => {
  const ev = [[0, 1, 0.1, 0.1], [1, 1, 0.2, 0.1], [2, 2, 0.3, 0.1]];
  assert.equal(cp.eventAt(ev, -0.1), -1);
  assert.equal(cp.eventAt(ev, 0), 0);
  assert.equal(cp.eventAt(ev, 1.5), 1);
  assert.equal(cp.eventAt(ev, 9), 2);
});
