// Mode presets (pure module).  Run:  node dashboard/tests/modes_test.mjs
import assert from 'node:assert/strict';
import * as MD from '../static/play/modes.js';

const exp = {
  classic: { kind: 'play', layout: 'originalClassic', ghosts: 'DirectionalGhost', arcade: false, preset: 'classic' },
  ours: { kind: 'play', layout: 'originalClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: false, preset: 'classic' },
  arcade: { kind: 'play', layout: 'originalClassic', ghosts: 'ArcadeGhostTeam', arcade: true, preset: 'classic' },
  think: { kind: 'watch', layout: 'mediumClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: false, preset: 'teacher', pacman: 'AlphaBetaAgent' },
  versus: { kind: 'versus', layout: 'originalClassic', ghosts: 'DirectionalGhost', versusGhosts: 'EnhancedCoordinatedGhostTeam', arcade: false, pacman: 'GreedyAgent', seed: 7 },
};
assert.deepEqual(MD.MODE_IDS, ['classic', 'ours', 'arcade', 'think', 'versus']);
for (const [id, want] of Object.entries(exp)) {
  const m = MD.byId(id);
  for (const [k, v] of Object.entries(want)) assert.equal(m[k], v, `${id}.${k}`);
  assert.ok(m.name && m.what && m.see && m.badge, id + ' has name, what, see, badge');
  assert.ok(!/\b(BFS|telemetry|preset|hub|recorder)\b/i.test([m.name, m.what, m.see, m.badge].join(' ')), id + ' has no jargon');
}
assert.match(MD.byId('classic').what, /Berkeley CS188/);

// every play/watch mode becomes a #/run deep link with the exact parameters
for (const id of ['classic', 'ours', 'arcade', 'think']) {
  const h = MD.runHash(id, { seed: 5 });
  assert.ok(h.startsWith('#/run?'));
  const q = new URLSearchParams(h.slice(6));
  assert.equal(q.get('layout'), exp[id].layout); assert.equal(q.get('ghosts'), exp[id].ghosts);
  assert.equal(q.get('arcade'), exp[id].arcade ? '1' : '0'); assert.equal(q.get('kind'), exp[id].kind);
  assert.equal(q.get('seed'), '5'); assert.equal(q.get('mode'), id);
}
assert.equal(MD.runHash('versus'), '#/versus');
// thinking switch: ON = teacher preset; SEE HOW THEY THINK is always on
assert.equal(new URLSearchParams(MD.runHash('ours', { thinking: true }).slice(6)).get('preset'), 'teacher');
assert.equal(new URLSearchParams(MD.runHash('ours', { thinking: false }).slice(6)).get('preset'), 'classic');
assert.equal(new URLSearchParams(MD.runHash('think', { thinking: false }).slice(6)).get('preset'), 'teacher');
assert.equal(MD.presetForThinking(true), 'teacher'); assert.equal(MD.thinkingOn('coach'), true); assert.equal(MD.thinkingOn('classic'), false);

// recognising a mode from run parameters, badges, and the other side
for (const id of ['classic', 'ours', 'arcade']) {
  const q = new URLSearchParams(MD.runHash(id, { seed: 1 }).slice(6));
  assert.equal(MD.modeFor(Object.fromEntries(q)).id, id);
}
assert.equal(MD.modeFor({ kind: 'watch', layout: 'mediumClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: '0', pacman: 'AlphaBetaAgent', depth: '2' }).id, 'think');
assert.equal(MD.modeFor({ kind: 'watch', layout: 'smallClassic', ghosts: 'DirectionalGhost', arcade: '0', pacman: 'AlphaBetaAgent', depth: '2' }), null, 'a level demo is CUSTOM');
assert.equal(MD.badgeFor({ kind: 'play', layout: 'originalClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: false }).line, 'coordinated team, original rules');
assert.equal(MD.badgeFor({ kind: 'play', layout: 'smallClassic', ghosts: 'DirectionalGhost', arcade: false }).name, 'CUSTOM');
assert.equal(MD.otherSide({ kind: 'play', layout: 'mediumClassic', ghosts: 'DirectionalGhost', arcade: false, preset: 'classic' }, 42), null,
  'CLASSIC on another maze is CUSTOM, so no other side');
const c = MD.otherSide({ kind: 'play', layout: 'originalClassic', ghosts: 'DirectionalGhost', arcade: false, preset: 'classic' }, 42);
assert.equal(c.mode.id, 'ours'); assert.match(c.hash, /seed=42/); assert.match(c.hash, /layout=originalClassic/);
const back = MD.otherSide({ kind: 'play', layout: 'originalClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: false, preset: 'teacher' }, 42);
assert.equal(back.mode.id, 'classic'); assert.match(back.hash, /preset=teacher/);
assert.equal(MD.otherSide({ kind: 'play', layout: 'originalClassic', ghosts: 'ArcadeGhostTeam', arcade: true }, 1), null);
console.log('ok modes_test');
