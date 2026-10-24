// The game modes: the one place that says what each plain-language mode really sets. PURE (no DOM), unit-tested
// under node (dashboard/tests/modes_test.mjs).  Every mode is a row of the same parameters the detailed setup
// (CUSTOM) edits, so a mode is never a separate code path: it is a saved set of choices.
//
// kind   'play' = you steer Pac-Man, 'watch' = an AI steers him, 'versus' = the side-by-side screen
// layout, ghosts, arcade (rules), preset (the thinking overlay: 'classic' = off, 'teacher' = on), pacman, depth

export const MODES = [
  { id: 'classic', name: 'CLASSIC', kind: 'play',
    what: 'The original Berkeley CS188 ghosts and rules, on the original maze. The baseline to compare against.',
    see: 'You will see: four ghosts that each chase you on their own.',
    badge: 'original ghosts, original rules',
    layout: 'originalClassic', ghosts: 'DirectionalGhost', arcade: false, preset: 'classic' },
  { id: 'ours', name: 'OUR GHOSTS', kind: 'play',
    what: 'The same game, but the ghosts are our coordinated team. Try to beat them.',
    see: 'You will see: ghosts that split up, cut you off and trap you.',
    badge: 'coordinated team, original rules',
    layout: 'originalClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: false, preset: 'classic' },
  { id: 'arcade', name: 'ARCADE', kind: 'play',
    what: 'Close to the real Pac-Man: four ghosts with their own personalities, scatter and chase phases, real speeds.',
    see: 'You will see: Blinky, Pinky, Inky and Clyde, fruit, and a ghost house.',
    badge: 'four ghost personalities, arcade speeds and scoring',
    layout: 'originalClassic', ghosts: 'ArcadeGhostTeam', arcade: true, preset: 'classic' },
  { id: 'think', name: 'SEE HOW THEY THINK', kind: 'watch',
    what: 'Watch an AI Pac-Man play against our ghosts, with the thinking drawn on the maze.',
    see: 'You will see: each ghost’s job, where it is heading, and the Commander’s orders.',
    badge: 'AI Pac-Man vs our ghosts, thinking shown',
    layout: 'mediumClassic', ghosts: 'EnhancedCoordinatedGhostTeam', arcade: false, preset: 'teacher',
    pacman: 'AlphaBetaAgent', depth: 2 },
  { id: 'versus', name: 'VERSUS', kind: 'versus',
    what: 'The same Pac-Man, the same maze and the same dice, once against the original ghosts and once against ours.',
    see: 'You will see: two mazes side by side, a move counter for each, and who caught him faster.',
    badge: 'original ghosts and our ghosts, side by side',
    layout: 'originalClassic', ghosts: 'DirectionalGhost', versusGhosts: 'EnhancedCoordinatedGhostTeam', arcade: false,
    preset: 'classic', pacman: 'GreedyAgent', seed: 7 },
];

export const MODE_IDS = MODES.map((m) => m.id);
export const byId = (id) => MODES.find((m) => m.id === id) || null;

/** The thinking overlay is one switch.  ON means the TEACHER layer preset; OFF means CLASSIC (nothing drawn). */
export const presetForThinking = (on) => (on ? 'teacher' : 'classic');
export const thinkingOn = (preset) => preset !== 'classic' && preset != null;

/** The URL that starts a mode.  `thinking` applies to the play modes; SEE HOW THEY THINK is always on. */
export function runHash(mode, { seed, thinking = false, layout } = {}) {
  const m = typeof mode === 'string' ? byId(mode) : mode;
  if (!m) return '#/menu';
  if (m.kind === 'versus') return '#/versus';
  const q = new URLSearchParams({ kind: m.kind, mode: m.id, layout: layout || m.layout, ghosts: m.ghosts, arcade: m.arcade ? '1' : '0',
    preset: m.id === 'think' ? 'teacher' : presetForThinking(thinking) });
  if (m.pacman) q.set('pacman', m.pacman);
  if (m.depth) q.set('depth', String(m.depth));
  if (seed != null) q.set('seed', String(seed));
  return '#/run?' + q;
}

/** Which mode do these run parameters amount to?  Used to label a game started from a deep link or CUSTOM. */
export function modeFor(p) {
  const arcade = p.arcade === true || p.arcade === '1' || p.arcade === 1;
  for (const m of MODES) {
    if (m.kind === 'versus') continue;
    if (m.kind === (p.kind === 'play' ? 'play' : 'watch') && m.layout === p.layout && m.ghosts === p.ghosts && m.arcade === arcade
      && (m.kind === 'play' || (m.pacman === p.pacman && (!m.depth || Number(p.depth) === m.depth)))) return m;
  }
  return null;
}

/** The two-part mode badge shown in the game HUD: { name, line }. Falls back to a plain description for CUSTOM. */
export function badgeFor(p, teams = []) {
  const m = p.mode && byId(p.mode) && modeFor(p) ? byId(p.mode) : modeFor(p);
  if (m) return { name: m.name, line: m.badge };
  const label = (teams.find((t) => t.name === p.ghosts) || {}).label || p.ghosts;
  const arcade = p.arcade === true || p.arcade === '1';
  return { name: 'CUSTOM', line: `${label} ghosts, ${arcade ? 'arcade' : 'original'} rules, ${niceMaze(p.layout)} maze` };
}

/** PLAY THE OTHER SIDE: CLASSIC <-> OUR GHOSTS with the same maze and seed.  null for every other mode. */
export function otherSide(p, seed) {
  const m = modeFor(p);
  if (!m || (m.id !== 'classic' && m.id !== 'ours')) return null;
  const other = byId(m.id === 'classic' ? 'ours' : 'classic');
  return { mode: other, hash: runHash(other, { seed, thinking: thinkingOn(p.preset), layout: p.layout }) };
}

// ---- plain labels for the detailed setup -----------------------------------------------------------------------
export function niceMaze(name) {
  if (/^demo_/.test(name)) return 'DEMO: ' + name.replace(/^demo_/, '').replace(/_/g, ' ').toUpperCase();
  return { originalClassic: 'ORIGINAL', mediumClassic: 'MEDIUM', smallClassic: 'SMALL' }[name] || name.replace(/Classic$/, '').toUpperCase();
}
export function mazeBlurb(name) {
  if (/^demo_/.test(name)) return 'A small hand-built maze that shows one ghost tactic.';
  return { originalClassic: 'The full-size maze from the original game.', mediumClassic: 'A medium maze: quicker games.',
    smallClassic: 'A small maze: very quick games.' }[name] || 'A classic maze.';
}
