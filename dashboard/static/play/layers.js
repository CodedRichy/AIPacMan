// Layer toggles, presets and teacher captions. PURE: no DOM, no fetch, so it can be unit-tested under node.
// Every caption is computed from fields that are really on the frame (roles, targets, tactical state,
// telemetry.messages); nothing here is scripted narration.

export const LAYERS = [
  { id: 'paths',     key: '1', label: 'Planned paths',      note: 'Dotted line from each ghost to the tile it is heading for. It shows the shortest route, which is not always the ghost’s own plan.' },
  { id: 'targets',   key: '2', label: 'Ghost targets',      note: 'Reticle on the tile each ghost is heading for.' },
  { id: 'roles',     key: '3', label: 'Roles + colours',    note: 'Letter badge: C chaser, I interceptor, B blocker, S sweeper, G capsule guard.' },
  { id: 'predicted', key: '4', label: 'Predicted Pac-Man',  note: 'Dashed Pac-Man outline where the interceptor expects him.' },
  { id: 'pincer',    key: '5', label: 'Pincer target',      note: 'Enhanced team only: the cut-off tile ahead of Pac-Man, with a jaw between it and him.' },
  { id: 'reserved',  key: '6', label: 'Reserved tiles',     note: 'Hatched tile a ghost has claimed for its next step.' },
  { id: 'tactical',  key: '7', label: 'Tactical state',     note: 'Banner with the coordinator’s state and macro strategy.' },
  { id: 'scared',    key: '8', label: 'Scared timers',      note: 'Countdown ring on each frightened ghost.' },
  { id: 'commander', key: '9', label: 'Commander + orders', note: 'Crowned stationary ghost, dashed order lines, order ticker.' },
  { id: 'chatter',   key: '0', label: 'Ghost chatter',      note: 'Ghost-to-ghost messages as arrows with a type label (only when the team publishes them).' },
  { id: 'trail',     key: 'h', label: 'Pac-Man heatmap',    note: 'Tiles Pac-Man has visited, brighter = more often.' },
];
export const IDS = LAYERS.map((l) => l.id);

export const PRESETS = {
  classic: { label: 'CLASSIC', on: [] },
  coach:   { label: 'COACH',   on: ['paths', 'targets', 'roles', 'commander'] },
  teacher: { label: 'TEACHER', on: IDS.slice() },
};

export function stateFromPreset(name) {
  const on = {};
  for (const id of IDS) on[id] = PRESETS[name].on.includes(id);
  return { preset: name, on };
}

/** Which preset (if any) exactly matches this on-map. */
export function presetFor(on) {
  for (const [name, p] of Object.entries(PRESETS)) {
    if (IDS.every((id) => !!on[id] === p.on.includes(id))) return name;
  }
  return 'custom';
}

export function toggle(state, id) {
  if (!IDS.includes(id)) return state;
  const on = { ...state.on, [id]: !state.on[id] };
  return { preset: presetFor(on), on };
}

/** Hotkey -> layer id. C is an alias for the Commander layer. */
export function hotkey(key) {
  const k = String(key).toLowerCase();
  if (k === 'c') return 'commander';
  const l = LAYERS.find((x) => x.key === k);
  return l ? l.id : null;
}

/** Restore from a parsed storage value; anything malformed falls back to the `fallback` preset. */
export function sanitize(raw, fallback = 'classic') {
  if (!raw || typeof raw !== 'object' || typeof raw.on !== 'object' || raw.on === null) return stateFromPreset(fallback);
  const on = {};
  for (const id of IDS) on[id] = raw.on[id] === true;
  return { preset: presetFor(on), on };
}

// ---------------------------------------------------------------------------------------------------------
// captions
// ---------------------------------------------------------------------------------------------------------
const ROLE_TEXT = {
  chaser: 'runs straight at Pac-Man',
  interceptor: 'runs to where Pac-Man is predicted to be',
  blocker: 'runs to a choke point to cut off his escape',
  sweeper: 'sweeps the food farthest from Pac-Man',
  capsule_guard: 'guards the power pellet',
  scared: 'is frightened and flees to a corner',
  blinky: 'chases Pac-Man directly',
  pinky: 'aims 4 tiles ahead of Pac-Man',
  inky: 'flanks, using Blinky and a point ahead of Pac-Man',
  clyde: 'chases from afar, retreats to its corner when close',
};
const TACTIC_TEXT = {
  COORDINATED_HUNT: 'hunt as a team',
  SCATTER: 'scatter to the corners (Pac-Man is powered up)',
  DEFEND_CAPSULE: 'one ghost guards the remaining power pellet',
  TRAP_AMBUSH: 'trap Pac-Man in a corridor',
  CHASE: 'chase', FRIGHTENED: 'ghosts are frightened',
};

export const roleName = (r) => String(r || 'ghost').replace(/_/g, ' ').toUpperCase();
export const tileStr = (t) => (t ? `(${t[0]},${t[1]})` : '');

export function describeGhost(g) {
  if (!g || !g.role) return null;
  const what = ROLE_TEXT[g.role] || 'follows its coordinator target';
  const moves = g.path && g.path.length > 1 ? g.path.length - 1 : null;
  const tgt = g.target ? `, target ${tileStr(g.target)}${moves != null ? ` (${moves} moves away by the shortest route)` : ''}` : '';
  return `Ghost ${g.index} is the ${roleName(g.role)}: it ${what}${tgt}.`;
}

/** Real chatter from a frame, read defensively.  Returns [] until a team actually publishes messages. */
export function readMessages(frame) {
  const t = frame && frame.telemetry;
  const m = t && !Array.isArray(t) && t.messages;
  if (!Array.isArray(m)) return [];
  return m.filter((x) => x && typeof x === 'object' && x.type != null && x.from != null);
}
export function readBeliefs(frame) {
  const t = frame && frame.telemetry;
  const b = t && !Array.isArray(t) && t.beliefs;
  return b && typeof b === 'object' && !Array.isArray(b) ? b : {};
}
export const msgKey = (m) => [m.tick, m.from, m.to, m.type, JSON.stringify(m.payload)].join('|');
export function payloadText(p) {
  if (p == null) return '';
  const s = typeof p === 'string' ? p : JSON.stringify(p);
  return s.length > 48 ? s.slice(0, 45) + '...' : s;
}

/** Messages whose receiver changed role or target between two frames: the only honest way to say
 *  "this message changed behaviour".  Returns caption strings. */
export function chatterEffects(prev, cur) {
  if (!prev || !cur) return [];
  const out = [];
  for (const m of readMessages(cur)) {
    const targets = m.to === 'all' || m.to == null ? cur.ghosts.map((g) => g.index) : [Number(m.to)];
    for (const gi of targets) {
      if (gi === Number(m.from)) continue;
      const a = prev.ghosts.find((g) => g.index === gi), b = cur.ghosts.find((g) => g.index === gi);
      if (!a || !b) continue;
      const roleChanged = a.role !== b.role, tgtChanged = JSON.stringify(a.target) !== JSON.stringify(b.target);
      if (roleChanged || tgtChanged) {
        out.push(`Ghost ${m.from} sent ${m.type}${m.to === 'all' ? ' to all' : ' to ghost ' + m.to}; ghost ${gi} then ` +
          (roleChanged ? `became ${roleName(b.role)}` : `retargeted ${tileStr(a.target)} to ${tileStr(b.target)}`) + '.');
        break;
      }
    }
  }
  return out;
}

/** Teacher caption for a frame: tactical state line + one ghost (rotating) + chatter effects. */
export function captions(frame, prev) {
  if (!frame) return [];
  const lines = [];
  if (frame.tacticalState) {
    const k = String(frame.tacticalState).toUpperCase();
    lines.push(`Team state ${roleName(k)}: ${TACTIC_TEXT[k] || 'set by the coordinator'}${frame.macroStrategy ? '; strategy ' + roleName(frame.macroStrategy) : ''}.`);
  }
  const withRole = frame.ghosts.filter((g) => g.role);
  if (withRole.length) {
    const g = withRole[Math.floor(frame.tick / 24) % withRole.length];
    const d = describeGhost(g);
    if (d) lines.push(d);
  }
  lines.push(...chatterEffects(prev, frame));
  if (!lines.length) lines.push('This ghost team publishes no coordinator state, so there is nothing to explain here.');
  return lines;
}

export const LEGEND = [
  ['Dotted line', 'The shortest route from a ghost to the tile it is heading for. This is an estimate, not the ghost’s own plan.'],
  ['Reticle', 'The tile a ghost is aiming for.'],
  ['Letter badge', 'The ghost’s role: C chaser, I interceptor, B blocker, S sweeper, G capsule guard.'],
  ['Dashed Pac-Man', 'Where the interceptor expects Pac-Man to be.'],
  ['Bracket + jaw', 'Pincer tile ahead of Pac-Man (Enhanced team only).'],
  ['Hatched tile', 'A tile a ghost has reserved for its next step.'],
  ['Ring + number', 'Frightened time left on a ghost.'],
  ['Crowned ghost', 'The Commander: a display, not a player. Dashed lines are its orders.'],
  ['Green arrow', 'A message from one ghost to another (type on the label).'],
  ['Warm squares', 'Tiles Pac-Man has visited; brighter means more often.'],
];
