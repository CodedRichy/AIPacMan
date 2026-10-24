// Every screen. Each returns { back, crumb, hints, bg?, destroy? } for the router and footer.
import { h, api, store, fmtScore } from './util.js';
import { mountGame, pacIcon } from './game.js';
import { mountSearchViz } from './searchviz.js';
import { LEVELS, flowSvg } from './levels.js';
import * as LY from './layers.js';

// ---- keyboard list helpers -------------------------------------------------------------------------------------
function keys(handler) {
  const ac = new AbortController();
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (/input|select|textarea/i.test(e.target.tagName)) return;
    handler(e);
  }, { signal: ac.signal });
  return () => ac.abort();
}

/** Vertical arcade menu: Up/Down, Enter, mouse hover and click. */
function listMenu(ul, items, { onFocus, onActivate, wrap = true } = {}) {
  let i = 0;
  const btns = items.map((it, n) => {
    const b = h('button', { class: 'mi', role: 'menuitem', tabindex: '-1', 'data-autofocus': n === 0 ? '' : null,
      onmouseenter: () => set(n), onfocus: () => set(n), onclick: () => onActivate(it, n) }, h('span', { class: 'mi-cur', 'aria-hidden': 'true' }), h('span', { class: 'mi-l' }, it.label), it.tag ? h('span', { class: 'mi-tag' }, it.tag) : null);
    return b;
  });
  ul.replaceChildren(...btns.map((b) => h('li', {}, b)));
  function set(n) {
    i = wrap ? (n + items.length) % items.length : Math.max(0, Math.min(items.length - 1, n));
    btns.forEach((b, k) => b.setAttribute('aria-current', String(k === i)));
    if (onFocus) onFocus(items[i], i);
  }
  set(0);
  const off = keys((e) => {
    if (e.key === 'ArrowDown' || e.key === 's') { e.preventDefault(); set(i + 1); btns[i].scrollIntoView({ block: 'nearest' }); }
    else if (e.key === 'ArrowUp' || e.key === 'w') { e.preventDefault(); set(i - 1); btns[i].scrollIntoView({ block: 'nearest' }); }
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onActivate(items[i], i); }
  });
  return { set, off, get index() { return i; } };
}

const wordmark = (small) => h('h1', { class: 'wordmark' + (small ? ' small' : '') }, h('span', { class: 'wm-ai' }, 'AI'), ' PAC-MAN');

// ---- title ---------------------------------------------------------------------------------------------------------
export async function title(root, ctx) {
  const go = () => ctx.go('#/menu');
  root.replaceChildren(h('section', { class: 'title', onclick: go, 'data-autofocus': '', tabindex: '-1' },
    wordmark(false),
    h('p', { class: 'sub' }, 'SEARCH · MULTI-AGENT · GHOST TEAMS'),
    h('p', { class: 'press blink' }, h('button', { class: 'press-b', onclick: (e) => { e.stopPropagation(); go(); } }, 'PRESS ENTER')),
    h('p', { class: 'credit' }, 'FREE PLAY · BERKELEY CS188 FRAMEWORK · LOCALHOST ONLY')));
  const off = keys((e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  return { bg: true, crumb: [], hints: [['Enter', 'START'], ['click', 'START']], destroy: off };
}

// ---- main menu ---------------------------------------------------------------------------------------------------
const MENU = [
  { label: 'PLAY', hash: '#/play', desc: 'Steer Pac-Man yourself against any ghost team. Three lives, extra life at 10,000.' },
  { label: 'WATCH AI', hash: '#/watch', desc: 'Pick a Pac-Man agent (greedy, minimax, alpha-beta, expectimax) and watch it think.' },
  { label: 'LEVEL SELECT', hash: '#/levels', desc: 'The project map: one level per phase, with a demo and the real numbers.' },
  { label: 'HIGH SCORES', hash: '#/scores', desc: 'Which ghost team hunts best? Ranked from the newest benchmark.' },
  { label: 'REPLAYS', hash: '#/replays', desc: 'Recorded games you can pause, step through and study.' },
  { label: 'OPTIONS', hash: '#/options', desc: 'Game speed, smooth motion, scanlines, default overlay.' },
  { label: 'ABOUT', hash: '#/about', desc: 'What this is, controls, credits.' },
];
export async function menu(root, ctx) {
  const ul = h('ul', { class: 'menu', role: 'menu', 'aria-label': 'Main menu' });
  const desc = h('p', { class: 'menu-desc', 'aria-live': 'polite' });
  root.replaceChildren(h('section', { class: 'menu-screen' }, wordmark(true), ul, desc));
  const m = listMenu(ul, MENU, { onFocus: (it) => { desc.textContent = it.desc; }, onActivate: (it) => ctx.go(it.hash) });
  return { bg: true, back: '#/title', crumb: [], hints: [['↑↓', 'MOVE'], ['Enter', 'SELECT'], ['Esc', 'TITLE']], destroy: m.off };
}

// ---- setup (PLAY / WATCH AI) -----------------------------------------------------------------------------------
export async function setup(root, ctx, kind) {
  const meta = await ctx.app.getMeta();
  const saved = store.get('pac.setup.' + kind, {});
  const opts = ctx.app.opts();
  const S = { layout: saved.layout || (kind === 'play' ? 'originalClassic' : 'smallClassic'),
    ghosts: saved.ghosts || (kind === 'play' ? 'ArcadeGhostTeam' : 'DirectionalGhost'),
    arcade: saved.arcade != null ? saved.arcade : kind === 'play',
    intel: saved.intel || opts.intel, pacman: saved.pacman || 'AlphaBetaAgent', depth: saved.depth || 2 };
  const teamChoices = () => meta.teams.filter((t) => S.arcade || !t.arcadeOnly).map((t) => ({ v: t.name, l: t.name.replace(/GhostTeam$/, '').replace('Directional', 'Berkeley') .toUpperCase() || t.name }));
  const rows = () => {
    const r = [];
    if (kind === 'watch') {
      r.push({ id: 'pacman', label: 'PAC-MAN', choices: meta.pacmen.map((p) => ({ v: p.name, l: p.name.replace('Agent', '').toUpperCase() })), desc: () => (meta.pacmen.find((p) => p.name === S.pacman) || {}).blurb });
      const dep = (meta.pacmen.find((p) => p.name === S.pacman) || {}).depth;
      r.push({ id: 'depth', label: 'DEPTH', choices: dep ? [1, 2, 3].map((d) => ({ v: d, l: String(d) })) : [{ v: S.depth, l: '-' }], desc: () => (dep ? 'Plies of look-ahead. Each extra ply costs far more time.' : 'This agent does not look ahead.') });
    }
    r.push({ id: 'layout', label: 'MAZE', choices: meta.layouts.map((l) => ({ v: l, l: l.replace(/^demo_/, 'DEMO ').replace(/Classic$/, '').replace(/_/g, ' ').toUpperCase() })), desc: () => (S.layout.startsWith('demo_') ? 'A small hand-built maze that shows one ghost tactic.' : 'A classic Berkeley maze.') });
    r.push({ id: 'ghosts', label: 'GHOSTS', choices: teamChoices(), desc: () => (meta.teams.find((t) => t.name === S.ghosts) || {}).blurb });
    r.push({ id: 'arcade', label: 'RULES', choices: [{ v: false, l: 'BERKELEY' }, { v: true, l: 'ARCADE' }], desc: () => (S.arcade ? 'Real-game speeds, scatter and chase timers, ghost house, fruit. Scoring: dots 10, pellets 50, ghosts 200-1600.' : 'Course rules: grid moves, -1 per move, +10 per dot, -500 when caught, +500 for clearing.') });
    r.push({ id: 'intel', label: 'INTEL', choices: [{ v: 'classic', l: 'OFF' }, { v: 'coach', l: 'COACH' }, { v: 'teacher', l: 'TEACHER' }], desc: () => ({ classic: 'Pure arcade. Press L in the game to open the layers panel.', coach: 'Ghost paths, targets, roles and the Commander drawn on the maze.', teacher: 'Every layer on, a legend, and live captions explaining what the ghosts are doing.' }[S.intel]) });
    return r;
  };
  let R = rows(), row = 0;
  const list = h('ul', { class: 'opt-rows' });
  const desc = h('p', { class: 'menu-desc', 'aria-live': 'polite' });
  function fix() {
    if (!S.arcade && S.ghosts.startsWith('Arcade')) S.ghosts = 'DirectionalGhost';
    const dep = (meta.pacmen.find((p) => p.name === S.pacman) || {}).depth;
    if (!dep) S.depth = 2;
  }
  function paint() {
    fix(); R = rows();
    list.replaceChildren(...R.map((r, n) => {
      const idx = Math.max(0, r.choices.findIndex((c) => c.v === S[r.id]));
      const cur = r.choices[idx] || r.choices[0];
      return h('li', { class: 'opt-row', 'aria-current': String(n === row) },
        h('span', { class: 'ol' }, r.label),
        h('button', { class: 'arrow', 'aria-label': 'previous ' + r.label, onclick: () => { row = n; cycle(-1); } }, '◀'),
        h('span', { class: 'ov' }, cur.l),
        h('button', { class: 'arrow', 'aria-label': 'next ' + r.label, onclick: () => { row = n; cycle(1); } }, '▶'));
    }), h('li', { class: 'opt-row start', 'aria-current': String(row === R.length) }, h('button', { class: 'start-b', 'data-autofocus': '', onclick: start }, kind === 'play' ? 'START GAME' : 'START WATCHING')));
    const r = R[row]; desc.textContent = r ? (r.desc() || '') : 'Enter to begin.';
  }
  function cycle(d) {
    const r = R[row]; if (!r) return;
    const idx = Math.max(0, r.choices.findIndex((c) => c.v === S[r.id]));
    S[r.id] = r.choices[(idx + d + r.choices.length) % r.choices.length].v;
    paint();
  }
  function start() {
    fix(); store.set('pac.setup.' + kind, S);
    const q = new URLSearchParams({ kind, layout: S.layout, ghosts: S.ghosts, arcade: S.arcade ? '1' : '0', preset: S.intel });
    if (kind === 'watch') { q.set('pacman', S.pacman); q.set('depth', String(S.depth)); }
    ctx.go('#/run?' + q);
  }
  paint();
  root.replaceChildren(h('section', { class: 'menu-screen setup' }, h('h2', { class: 'screen-t' }, kind === 'play' ? 'PLAY' : 'WATCH AI'), list, desc));
  const off = keys((e) => {
    if (e.key === 'ArrowDown' || e.key === 's') { e.preventDefault(); row = Math.min(R.length, row + 1); paint(); }
    else if (e.key === 'ArrowUp' || e.key === 'w') { e.preventDefault(); row = Math.max(0, row - 1); paint(); }
    else if (e.key === 'ArrowLeft' || e.key === 'a') { e.preventDefault(); cycle(-1); }
    else if (e.key === 'ArrowRight' || e.key === 'd') { e.preventDefault(); cycle(1); }
    else if (e.key === 'Enter') { e.preventDefault(); if (row === R.length) start(); else { row = R.length; paint(); } }
  });
  return { back: '#/menu', crumb: [kind === 'play' ? 'PLAY' : 'WATCH AI'], hints: [['↑↓', 'ROW'], ['←→', 'CHANGE'], ['Enter', 'START'], ['Esc', 'MENU']], destroy: off };
}

// ---- run (the game itself) -----------------------------------------------------------------------------------------
export async function run(root, ctx) {
  const q = ctx.q, kind = q.kind === 'play' ? 'play' : 'watch';
  const opts = ctx.app.opts();
  if (q.preset) ctx.app.layers = LY.stateFromPreset(['classic', 'coach', 'teacher'].includes(q.preset) ? q.preset : 'classic');
  const arcade = q.arcade === '1';
  const params = { layout: q.layout || 'smallClassic', ghosts: q.ghosts || 'DirectionalGhost', arcade, level: 1, seed: Math.floor(Math.random() * 9000),
    tickRate: opts.speed, lives: kind === 'play' ? 3 : 1, pacman: kind === 'play' ? 'browser' : (q.pacman || 'GreedyAgent') };
  if (kind === 'watch' && q.depth) params.depth = Number(q.depth);
  const wrap = h('div', { class: 'game-wrap' });
  root.replaceChildren(wrap);
  const g = mountGame(wrap, { kind, params, layers: ctx.app.layers, tickRate: opts.speed, onLayers: (l) => { ctx.app.layers = l; } });
  const back = kind === 'play' ? '#/play' : '#/watch';
  return { back, crumb: [[back, kind === 'play' ? 'PLAY' : 'WATCH AI'], 'GAME'],
    hints: kind === 'play'
      ? [['←↑↓→', 'STEER'], ['Space', 'PAUSE'], ['L', 'LAYERS'], ['1-0 H C', 'TOGGLE'], ['Esc', 'QUIT']]
      : [['Space', 'PAUSE'], ['L', 'LAYERS'], ['1-0 H C', 'TOGGLE'], ['Esc', 'QUIT']],
    destroy: () => g.destroy() };
}

// ---- level select + level pages --------------------------------------------------------------------------------
async function getFacts(ctx) { return api('/api/facts'); }

export async function levels(root, ctx) {
  const facts = await getFacts(ctx);
  const ul = h('ul', { class: 'menu levels', role: 'menu', 'aria-label': 'Levels' });
  const det = h('div', { class: 'lv-detail', 'aria-live': 'polite' });
  root.replaceChildren(h('section', { class: 'menu-screen lv-select' }, h('h2', { class: 'screen-t' }, 'LEVEL SELECT'), h('div', { class: 'lv-split' }, ul, det)));
  const items = LEVELS.map((L) => ({ label: `${L.n < 7 ? L.n : '+'}  ${L.code}`, L, tag: facts.levels[String(L.n)].phase ? facts.levels[String(L.n)].phase.state.toUpperCase() : 'BONUS' }));
  const m = listMenu(ul, items, {
    onFocus: ({ L }) => {
      const f = facts.levels[String(L.n)];
      det.replaceChildren(h('p', { class: 'eyebrow' }, L.n < 7 ? `LEVEL ${L.n} · PHASE ${L.phase}` : 'BONUS LEVEL'), h('h3', {}, L.title), h('p', {}, L.blurb),
        f.numbers[0] ? h('p', { class: 'chip-line' }, h('b', {}, f.numbers[0].label + ': '), f.numbers[0].value) : null,
        f.phase ? h('p', { class: 'cap' }, `PENDING_TASKS.md: ${f.phase.done} done, ${f.phase.open} open, ${f.phase.partial} partial`) : null,
        h('p', { class: 'cap' }, h('code', {}, L.source)));
    },
    onActivate: ({ L }) => ctx.go('#/levels/' + L.n),
  });
  return { back: '#/menu', crumb: ['LEVEL SELECT'], hints: [['↑↓', 'MOVE'], ['Enter', 'OPEN'], ['Esc', 'MENU']], destroy: m.off };
}

export async function level(root, ctx, n) {
  const L = LEVELS.find((x) => x.n === n);
  if (!L) return levels(root, ctx);
  const facts = (await getFacts(ctx)).levels[String(n)];
  const bundle = await getFacts(ctx);
  const nodes = [];
  const sec = (t, ...kids) => h('section', { class: 'lv-sec' }, h('h3', {}, t), ...kids);
  const tryBtn = h('button', { class: 'btn solid big', 'data-autofocus': '', onclick: tryIt }, 'TRY IT: ' + L.try.label);
  async function tryIt() {
    if (L.try.go === '#/replays/auto') {
      const t = (await ctx.app.getTraces()).filter((x) => /_v2\.jsonl$/.test(x.name));
      const pick = t.find((x) => /Enhanced/.test(x.ghostTeam)) || t[0];
      return ctx.go(pick ? '#/replays/' + encodeURIComponent(pick.name) : '#/replays');
    }
    if (n === 1) { svHost.scrollIntoView({ behavior: 'smooth', block: 'start' }); if (sv) sv.run(); return; }
    ctx.go(L.try.go);
  }
  const svHost = h('div', { class: 'sv-host' });
  let sv = null;
  const numbers = facts.numbers.length ? h('dl', { class: 'numbers' }, ...facts.numbers.flatMap((x) => [h('dt', {}, x.label), h('dd', {}, x.value, h('small', {}, x.source))]))
    : h('p', { class: 'cap' }, 'No measured numbers recorded for this level yet.');
  const phase = facts.phase ? h('p', { class: 'phase-line' }, h('b', {}, 'PENDING_TASKS.md says: '), `${facts.phase.state || 'no state'}. ${facts.phase.status}`) : null;
  const rows = h('dl', { class: 'how-rows' }, ...L.rows.flatMap(([a, b]) => [h('dt', {}, a), h('dd', {}, b)]));
  const diagram = h('div', { class: 'diagram', html: flowSvg(L.flow) });
  let cmpHost = null, cmpTimer = 0;
  if (L.compare) {
    cmpHost = h('div', { class: 'cmp' });
    const draw = (d) => {
      const r = d.result;
      if (d.running) { cmpHost.replaceChildren(h('p', {}, `Running real games... ${d.progress[0]} / ${d.progress[1]} (2 worker processes)`)); return; }
      if (!r) { cmpHost.replaceChildren(h('p', { class: 'cap' }, 'No comparison run yet. Press RUN COMPARISON.'), runBtn); return; }
      const maxN = Math.max(...r.rows.map((x) => x.nodesPerMove)), maxT = Math.max(...r.rows.map((x) => x.msPerMove));
      cmpHost.replaceChildren(
        h('table', {}, h('caption', {}, `Depth ${r.depth}, ${r.layout}, vs ${r.ghost}, ${r.games} games each, run ${r.ranAt}`),
          h('thead', {}, h('tr', {}, ...['AGENT', 'WIN RATE', 'AVG SCORE', 'NODES / MOVE', 'MS / MOVE'].map((t) => h('th', {}, t)))),
          h('tbody', {}, ...r.rows.map((x) => h('tr', {}, h('td', {}, x.agent.replace('Agent', '')), h('td', {}, `${Math.round(100 * x.winRate)}% (${x.wins}/${x.games})`), h('td', {}, x.avgScore.toFixed(0)),
            h('td', {}, h('span', { class: 'bar', style: `--w:${(100 * x.nodesPerMove / maxN).toFixed(0)}%` }), x.nodesPerMove.toFixed(0)),
            h('td', {}, h('span', { class: 'bar', style: `--w:${(100 * x.msPerMove / maxT).toFixed(0)}%` }), x.msPerMove.toFixed(1)))))),
        runBtn, h('p', { class: 'cap' }, 'Nodes = game states generated per move. Same win rate with fewer nodes is the point of alpha-beta.'));
    };
    const runBtn = h('button', { class: 'btn', onclick: async () => { runBtn.disabled = true; try { await api('/api/compare/run', { games: 8, depth: 3 }); } catch (e) { /* already running */ } poll(); } }, 'RUN COMPARISON (2 PROCESSES)');
    const poll = async () => {
      clearTimeout(cmpTimer);
      try { const d = await api('/api/compare'); draw(d); if (d.running) cmpTimer = setTimeout(poll, 1500); else runBtn.disabled = false; } catch (e) { /* ignore */ }
    };
    poll();
  }
  root.replaceChildren(h('article', { class: 'level' },
    h('header', { class: 'lv-head' }, h('p', { class: 'eyebrow' }, n < 7 ? `LEVEL ${n} OF 6` : 'BONUS LEVEL'), h('h2', { class: 'screen-t' }, L.code),
      h('p', { class: 'lv-sub' }, L.blurb)),
    h('div', { class: 'lv-grid' },
      h('div', { class: 'lv-main' },
        sec('WHAT IS THIS?', ...L.explain.map((p) => h('p', {}, p)), h('div', { class: 'lv-actions' }, tryBtn, h('span', { class: 'src' }, 'SOURCE ', h('code', {}, L.source), L.also ? h('code', {}, L.also) : null))),
        n === 1 ? sec('SEARCH VISUALISER', svHost) : null,
        L.compare ? sec('SIDE BY SIDE: REAL GAMES', cmpHost) : null),
      h('div', { class: 'lv-side' },
        sec('HOW IT WORKS', diagram, rows),
        sec('REAL NUMBERS', numbers, phase)))));
  if (n === 1) sv = mountSearchViz(svHost, { auto: new URLSearchParams(ctx.q).get('try') === '1' });
  if (ctx.q.try === '1' && n === 1) setTimeout(() => svHost.scrollIntoView({ block: 'start' }), 50);
  const off = keys((e) => {
    if (e.key === 'ArrowRight' && n < 7) { e.preventDefault(); ctx.go('#/levels/' + (n + 1)); }
    if (e.key === 'ArrowLeft' && n > 1) { e.preventDefault(); ctx.go('#/levels/' + (n - 1)); }
  });
  void bundle; void nodes;
  return { back: '#/levels', crumb: [['#/levels', 'LEVEL SELECT'], `LEVEL ${n < 7 ? n : 'BONUS'}`], hints: [['Enter', 'TRY IT'], ['←→', 'PREV / NEXT LEVEL'], ['Esc', 'LEVELS']],
    destroy: () => { off(); clearTimeout(cmpTimer); if (sv) sv.destroy(); } };
}

// ---- high scores --------------------------------------------------------------------------------------------------
export async function scores(root, ctx) {
  let timer = 0;
  const host = h('div', { class: 'scores' });
  const status = h('p', { class: 'bench-status', role: 'status' });
  const gamesSel = h('select', { 'aria-label': 'Games per matchup' }, ...[10, 20, 40].map((v) => h('option', { value: v }, v + ' games each')));
  const mazeSel = h('select', { 'aria-label': 'Maze' }, ...['mediumClassic', 'smallClassic'].map((v) => h('option', { value: v }, v)));
  const runB = h('button', { class: 'btn solid', 'data-autofocus': '', onclick: async () => {
    runB.disabled = true;
    try { await api('/api/benchmark/run', { games: Number(gamesSel.value), layout: mazeSel.value }); } catch (e) { status.textContent = e.message; }
    watch();
  } }, 'RUN BENCHMARK');
  async function watch() {
    clearTimeout(timer);
    const s = await api('/api/benchmark/status').catch(() => ({ state: 'idle' }));
    if (s.state === 'running') { status.textContent = `Benchmark running: ${s.layout}, ${s.games} games each, ${s.seconds}s (2 worker processes)...`; runB.disabled = true; timer = setTimeout(watch, 2000); }
    else if (s.state === 'done') { status.textContent = `Finished in ${s.seconds}s: ${s.file}`; runB.disabled = false; load(); }
    else if (s.state === 'failed') { status.textContent = 'Benchmark failed.'; runB.disabled = false; }
    else runB.disabled = false;
  }
  const medal = (i) => ['1ST', '2ND', '3RD', '4TH', '5TH', '6TH'][i] || (i + 1) + 'TH';
  const table = (title, sub, rows, cols) => h('section', { class: 'hs' }, h('h3', {}, title), h('p', { class: 'cap' }, sub),
    h('ol', { class: 'hs-list' }, ...rows.map((r, i) => h('li', {}, h('span', { class: 'rk' }, medal(i)), h('span', { class: 'cd' }, r.code), ...cols.map((c) => h('span', { class: c.cls || 'vl' }, c.f(r))), h('span', { class: 'tm' }, r.team)))));
  async function load() {
    const hs = await api('/api/highscores');
    const mine = store.get('pac.scores', []);
    host.replaceChildren(
      hs.file ? h('p', { class: 'cap' }, `From ${hs.file} (${hs.timestamp}). Lower Pac-Man score = stronger ghosts.`) : h('p', {}, 'No benchmark results found. Press RUN BENCHMARK.'),
      hs.file ? h('div', { class: 'hs-two' },
        table('STRONGEST HUNTERS', 'ranked by Pac-Man\'s average score, lowest first', hs.byScore, [{ f: (r) => r.avgScore.toFixed(1), cls: 'vl big' }, { f: (r) => `${r.games} games`, cls: 'vl dim' }]),
        table('FASTEST KILLS', 'ranked by average moves until Pac-Man is caught', hs.byKill, [{ f: (r) => r.killTime.toFixed(1) + ' moves', cls: 'vl big' }, { f: (r) => `${Math.round(100 * r.killRate)}% caught`, cls: 'vl dim' }])) : null,
      h('section', { class: 'hs' }, h('h3', {}, 'YOUR SCORES'), mine.length ? h('ol', { class: 'hs-list' }, ...mine.map((r, i) => h('li', {}, h('span', { class: 'rk' }, medal(i)), h('span', { class: 'cd' }, r.name), h('span', { class: 'vl big' }, fmtScore(r.score)), h('span', { class: 'tm' }, `${r.layout} · ${r.rules}`))))
        : h('p', { class: 'cap' }, 'Nothing yet. Play a game and beat the clock.')));
  }
  root.replaceChildren(h('section', { class: 'menu-screen wide' }, h('h2', { class: 'screen-t' }, 'HIGH SCORES'), host,
    h('div', { class: 'bench' }, runB, gamesSel, mazeSel, status)));
  await load(); watch();
  return { back: '#/menu', crumb: ['HIGH SCORES'], hints: [['Enter', 'RUN BENCHMARK'], ['Esc', 'MENU']], destroy: () => clearTimeout(timer) };
}

// ---- replays ---------------------------------------------------------------------------------------------------------
export async function replays(root, ctx) {
  const list = (await ctx.app.getTraces());
  const ul = h('ul', { class: 'menu replays', role: 'menu' });
  const desc = h('p', { class: 'menu-desc' });
  root.replaceChildren(h('section', { class: 'menu-screen wide' }, h('h2', { class: 'screen-t' }, 'REPLAYS'), list.length ? ul : h('p', {}, 'No traces in dashboard/traces yet. Record one with dashboard/record.py.'), desc));
  const items = list.map((t) => ({ t, label: `${t.layout}`.replace('Classic', '').toUpperCase(), tag: `${(t.ghostTeam || '').replace('GhostTeam', '').replace('EnhancedCoordinated', 'ENH-COORD').toUpperCase()}  ${t.score}  ${t.ticks}T` }));
  const m = items.length ? listMenu(ul, items, { onFocus: ({ t }) => { desc.textContent = `${t.name}${/_v2\.jsonl$/.test(t.name) ? '' : ' (schema 1: no sub-tile motion)'}`; }, onActivate: ({ t }) => ctx.go('#/replays/' + encodeURIComponent(t.name)) }) : { off() {} };
  return { back: '#/menu', crumb: ['REPLAYS'], hints: [['↑↓', 'MOVE'], ['Enter', 'WATCH'], ['Esc', 'MENU']], destroy: m.off };
}

export async function replay(root, ctx, name) {
  const wrap = h('div', { class: 'game-wrap' });
  root.replaceChildren(wrap);
  const opts = ctx.app.opts();
  const g = mountGame(wrap, { kind: 'replay', trace: name, layers: ctx.app.layers, tickRate: opts.speed, onLayers: (l) => { ctx.app.layers = l; } });
  return { back: '#/replays', crumb: [['#/replays', 'REPLAYS'], name.length > 28 ? name.slice(0, 26) + '..' : name],
    hints: [['Space', 'PAUSE'], ['←→', 'STEP (Shift x10)'], ['+ -', 'SPEED'], ['L', 'LAYERS'], ['1-0 H C', 'TOGGLE'], ['Esc', 'LIST']], destroy: () => g.destroy() };
}

// ---- options / about -------------------------------------------------------------------------------------------------
export async function options(root, ctx) {
  const o = ctx.app.opts();
  const defs = [
    { id: 'speed', label: 'GAME SPEED', ch: [[10, 'SLOW'], [15, 'ARCADE'], [20, 'FAST'], [30, 'TURBO']], note: 'Rounds per second. 15 is close to the real arcade pace.' },
    { id: 'smooth', label: 'SMOOTH MOTION', ch: [[true, 'ON'], [false, 'OFF']], note: 'Slides characters between ticks. Always off when the system asks for reduced motion.' },
    { id: 'scan', label: 'SCANLINES', ch: [[true, 'ON'], [false, 'OFF']], note: 'A faint CRT line pattern. Static: it never flickers.' },
    { id: 'intel', label: 'DEFAULT INTEL', ch: [['classic', 'OFF'], ['coach', 'COACH'], ['teacher', 'TEACHER']], note: 'Layer preset used when a game starts without one.' },
  ];
  let row = 0;
  const ul = h('ul', { class: 'opt-rows' }), desc = h('p', { class: 'menu-desc' });
  const paint = () => {
    const cur = ctx.app.opts();
    ul.replaceChildren(...defs.map((d, n) => {
      const i = Math.max(0, d.ch.findIndex((c) => c[0] === cur[d.id]));
      return h('li', { class: 'opt-row', 'aria-current': String(n === row) }, h('span', { class: 'ol' }, d.label),
        h('button', { class: 'arrow', 'aria-label': 'previous', onclick: () => { row = n; cyc(-1); } }, '◀'), h('span', { class: 'ov' }, d.ch[i][1]),
        h('button', { class: 'arrow', 'aria-label': 'next', onclick: () => { row = n; cyc(1); } }, '▶'));
    }), h('li', { class: 'opt-row start', 'aria-current': String(row === defs.length) }, h('button', { class: 'start-b', onclick: clear }, 'CLEAR MY SCORES')));
    desc.textContent = defs[row] ? defs[row].note : 'Removes the high scores saved in this browser.';
  };
  function cyc(dir) {
    const d = defs[row]; if (!d) return;
    const cur = ctx.app.opts()[d.id], i = Math.max(0, d.ch.findIndex((c) => c[0] === cur));
    ctx.app.setOpts({ [d.id]: d.ch[(i + dir + d.ch.length) % d.ch.length][0] }); paint();
  }
  function clear() { store.set('pac.scores', []); store.set('pac.hi', 0); desc.textContent = 'Scores cleared.'; }
  void o; paint();
  root.replaceChildren(h('section', { class: 'menu-screen setup' }, h('h2', { class: 'screen-t' }, 'OPTIONS'), ul, desc));
  const off = keys((e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); row = Math.min(defs.length, row + 1); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); row = Math.max(0, row - 1); paint(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); cyc(-1); }
    else if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); if (row === defs.length) clear(); else cyc(1); }
  });
  return { back: '#/menu', crumb: ['OPTIONS'], hints: [['↑↓', 'ROW'], ['←→', 'CHANGE'], ['Esc', 'MENU']], destroy: off };
}

export async function about(root, ctx) {
  root.replaceChildren(h('section', { class: 'menu-screen wide about' }, h('h2', { class: 'screen-t' }, 'ABOUT'),
    h('p', {}, 'This is a Pac-Man engine you can read. It started as the Berkeley CS188 search and multi-agent projects, then grew a team of cooperating ghosts, a recorder, a benchmark harness and an arcade rule set.'),
    h('p', {}, 'The maze on screen is the real game. The extra drawings (the INTEL layers) show what the ghost coordinator decided, taken from the game\'s own state.'),
    h('h3', {}, 'CONTROLS'),
    h('dl', { class: 'how-rows' }, h('dt', {}, 'Arrows / WASD'), h('dd', {}, 'steer Pac-Man, or move in menus'), h('dt', {}, 'Enter / Esc'), h('dd', {}, 'select / go back'), h('dt', {}, 'Space'), h('dd', {}, 'pause'),
      h('dt', {}, 'L'), h('dd', {}, 'open or close the layers panel'), h('dt', {}, '1 to 0, H, C'), h('dd', {}, 'toggle one layer (C = Commander)')),
    h('h3', {}, 'CREDITS'),
    h('p', {}, 'Berkeley CS188 Pac-Man framework (UC Berkeley, educational use). Arcade rules follow the Pac-Man Dossier. Fonts: Press Start 2P and Space Mono, SIL Open Font License 1.1, bundled; nothing loads from the network.'),
    h('p', { class: 'cap' }, 'Everything runs on 127.0.0.1. Files: dashboard/README.md, docs/ARCHITECTURE.md, docs/ARCADE_MODE.md, dashboard/DESIGN.md.')));
  return { back: '#/menu', crumb: ['ABOUT'], hints: [['Esc', 'MENU']] };
}
