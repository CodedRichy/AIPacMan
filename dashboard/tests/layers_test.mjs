// Layer toggle / preset / caption logic (pure module).  Run:  node dashboard/tests/layers_test.mjs
import assert from 'node:assert/strict';
import * as LY from '../static/play/layers.js';

// presets
const classic = LY.stateFromPreset('classic'), coach = LY.stateFromPreset('coach'), teacher = LY.stateFromPreset('teacher');
assert.ok(LY.IDS.every((id) => classic.on[id] === false), 'CLASSIC has everything off');
assert.deepEqual(LY.IDS.filter((id) => coach.on[id]).sort(), ['commander', 'paths', 'roles', 'targets']);
assert.ok(LY.IDS.every((id) => teacher.on[id] === true), 'TEACHER has everything on');
assert.equal(LY.presetFor(coach.on), 'coach');

// toggling is independent, immutable, and re-derives the preset name
let s = LY.toggle(classic, 'paths');
assert.equal(s.on.paths, true); assert.equal(classic.on.paths, false, 'input state not mutated');
assert.equal(s.preset, 'custom');
s = LY.toggle(LY.toggle(LY.toggle(LY.toggle(classic, 'paths'), 'targets'), 'roles'), 'commander');
assert.equal(s.preset, 'coach', 'toggling into the COACH set is recognised as COACH');
assert.equal(LY.toggle(s, 'nonsense'), s, 'unknown layer ids are ignored');
for (const id of LY.IDS) assert.equal(LY.toggle(LY.toggle(classic, id), id).preset, 'classic');

// hotkeys: every layer has a unique one, C aliases Commander
const keys = LY.LAYERS.map((l) => l.key);
assert.equal(new Set(keys).size, keys.length, 'hotkeys are unique');
for (const l of LY.LAYERS) assert.equal(LY.hotkey(l.key), l.id);
assert.equal(LY.hotkey('c'), 'commander'); assert.equal(LY.hotkey('C'), 'commander');
assert.equal(LY.hotkey('l'), null, 'L is reserved for the panel'); assert.equal(LY.hotkey(' '), null);
for (const reserved of ['w', 'a', 's', 'd', 'p']) assert.equal(LY.hotkey(reserved), null, reserved + ' is not a layer key');

// persistence: sanitize survives junk, and round-trips
assert.equal(LY.sanitize(null).preset, 'classic');
assert.equal(LY.sanitize('x', 'coach').preset, 'coach');
assert.equal(LY.sanitize({ on: null }).preset, 'classic');
assert.deepEqual(LY.sanitize(JSON.parse(JSON.stringify(s))).on, s.on);
assert.equal(LY.sanitize({ on: { paths: 'yes', trail: true } }).on.paths, false, 'only literal true counts');

// captions come from frame fields
const frame = (extra = {}) => ({
  tick: 0, tacticalState: 'TRAP_AMBUSH', macroStrategy: 'EARLY_SPREAD',
  ghosts: [
    { index: 1, role: 'chaser', target: [3, 4], path: [[1, 1], [2, 1], [3, 1], [3, 2]] },
    { index: 2, role: 'interceptor', target: [9, 2], path: [[5, 5], [6, 5], [7, 5], [8, 5], [9, 5], [9, 2]] },
  ], ...extra });
let cap = LY.captions({ ...frame(), tick: 24 }, null);   // tick 24 -> second role-bearing ghost
assert.ok(cap[0].includes('TRAP AMBUSH'));
assert.ok(cap.some((l) => l.includes('Ghost 2 is the INTERCEPTOR') && l.includes('where Pac-Man is predicted to be') && l.includes('5 moves')), cap.join(' | '));
cap = LY.captions({ ...frame(), tick: 0 }, null);
assert.ok(cap.some((l) => l.includes('Ghost 1 is the CHASER') && l.includes('3 moves')));
const bare = LY.captions({ tick: 0, ghosts: [{ index: 1 }] }, null);
assert.ok(bare[0].includes('no coordinator state'), 'no telemetry means an honest empty caption');

// ghost chatter: absent -> empty; hand-built sample frame following the Phase 10 shape
assert.deepEqual(LY.readMessages(frame()), [], 'never fabricate messages');
assert.deepEqual(LY.readMessages({ telemetry: { messages: 'junk' } }), []);
assert.deepEqual(LY.readBeliefs(frame()), {});
const prev = frame();
const sample = frame({
  tick: 7,
  telemetry: {
    messages: [{ tick: 7, from: 1, to: 2, type: 'REQUEST_SUPPORT', payload: { tile: [3, 4] } }, { tick: 7, from: 2, to: 'all', type: 'ACK', ackOf: 0 }, null, { type: 'x' }],
    beliefs: { 1: { pacTile: [3, 4], age: 0 } },
  },
});
sample.ghosts = [{ ...prev.ghosts[0] }, { ...prev.ghosts[1], role: 'blocker', target: [2, 2] }];
assert.equal(LY.readMessages(sample).length, 2, 'malformed entries are dropped');
assert.deepEqual(LY.readBeliefs(sample)[1].pacTile, [3, 4]);
const fx = LY.chatterEffects(prev, sample);
assert.equal(fx.length, 1, fx.join('|'));
assert.ok(fx[0].includes('REQUEST_SUPPORT') && fx[0].includes('became BLOCKER'), fx[0]);
assert.deepEqual(LY.chatterEffects(prev, { ...sample, ghosts: prev.ghosts }), [], 'no behaviour change, no claim');
assert.equal(LY.payloadText({ a: 'x'.repeat(100) }).length, 48);
assert.ok(LY.LEGEND.some(([k]) => /Dotted/.test(k)) && LY.LEGEND.find(([k]) => /Dotted/.test(k))[1].includes('not the ghost'), 'legend says paths are recorder BFS routes');
console.log('ok layers_test');
