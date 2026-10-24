// Every screen. Each returns { back, crumb, hints, bg?, destroy? } for the router and footer.
import { h, api, store, fmtScore, reduceMotion } from './util.js';
import { mountGame, pacIcon } from './game.js';
import { mountSearchViz } from './searchviz.js';
import { LEVELS, flowSvg } from './levels.js';
import * as LY from './layers.js';
import * as MD from './modes.js';
import { ArcadeView } from './render.js';

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
function listMenu(ul, items, { onFocus, onActivate, wrap = true, numbers = false } = {}) {
  if (numbers) ul.classList.add('numbered');
  let i = 0;
  const btns = items.map((it, n) => {
    const b = h('button', { class: 'mi', role: 'menuitem', tabindex: '-1', 'data-autofocus': n === 0 ? '' : null,
      onmouseenter: () => set(n), onfocus: () => set(n), onclick: () => onActivate(it, n) }, h('span', { class: 'mi-cur', 'aria-hidden': 'true' }), it.content || h('span', { class: 'mi-l' }, it.label), it.tag ? h('span', { class: 'mi-tag' }, it.tag) : null, numbers && n < 9 ? h('kbd', { class: 'mi-key', 'aria-hidden': 'true' }, String(n + 1)) : null);
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
    else if (numbers && /^[1-9]$/.test(e.key) && Number(e.key) <= items.length) { e.preventDefault(); set(Number(e.key) - 1); onActivate(items[i], i); }
  });
  return { set, off, get index() { return i; } };
}

const wordmark = (small) => h('h1', { class: 'wordmark' + (small ? ' small' : '') }, h('span', { class: 'wm-ai' }, 'AI'), ' PAC-MAN');

// ---- title ---------------------------------------------------------------------------------------------------------
export async function title(root, ctx) {
  const go = () => ctx.go('#/menu');
  root.replaceChildren(h('section', { class: 'title', onclick: go, 'data-autofocus': '', tabindex: '-1' },
    wordmark(false),
    h('p', { class: 'sub' }, 'PAC-MAN VS SMARTER GHOSTS'),
    h('p', { class: 'press blink' }, h('button', { class: 'press-b', onclick: (e) => { e.stopPropagation(); go(); } }, 'PRESS ENTER')),
    h('p', { class: 'credit' }, 'FREE PLAY · RUNS ONLY ON YOUR COMPUTER')));
  const off = keys((e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
  return { bg: true, crumb: [], hints: [['Enter', 'START'], ['click', 'START']], destroy: off };
}

// ---- main menu ---------------------------------------------------------------------------------------------------
const MENU = [
  { label: 'PLAY', hash: '#/play', desc: 'Pick a game mode and play Pac-Man against the ghosts.' },
  { label: 'WATCH', hash: '#/watch', desc: 'Let an AI play Pac-Man while you watch how it decides.' },
  { label: 'LEARN', hash: '#/levels', desc: 'A guided tour of the project, one step at a time, with a demo for each step.' },
  { label: 'SCORES', hash: '#/scores', desc: 'Which ghost team catches Pac-Man best? Plus your own best scores.' },
  { label: 'MORE', hash: '#/more', desc: 'Replays of recorded games, options and about.' },
];
export async function menu(root, ctx) {
  const ul = h('ul', { class: 'menu', role: 'menu', 'aria-label': 'Main menu' });
  const desc = h('p', { class: 'menu-desc', 'aria-live': 'polite' });
  root.replaceChildren(h('section', { class: 'menu-screen' }, wordmark(true), ul, desc));
  const m = listMenu(ul, MENU, { onFocus: (it) => { desc.textContent = it.desc; }, onActivate: (it) => ctx.go(it.hash), numbers: true });
  return { bg: true, back: '#/title', crumb: [], hints: [['UP DOWN', 'MOVE'], ['Enter', 'SELECT'], ['1-5', 'JUMP'], ['Esc', 'TITLE']], destroy: m.off };
}

const MORE = [
  { label: 'REPLAYS', hash: '#/replays', desc: 'Games that were recorded earlier. Pause them, step through them and study them.' },
  { label: 'OPTIONS', hash: '#/options', desc: 'Game speed, smooth motion, scanlines and the thinking switch.' },
  { label: 'ABOUT', hash: '#/about', desc: 'What this is, the controls and the credits.' },
];
export async function more(root, ctx) {
  const ul = h('ul', { class: 'menu', role: 'menu', 'aria-label': 'More' });
  const desc = h('p', { class: 'menu-desc', 'aria-live': 'polite' });
  root.replaceChildren(h('section', { class: 'menu-screen' }, h('h2', { class: 'screen-t' }, 'MORE'), ul, desc));
  const m = listMenu(ul, MORE, { onFocus: (it) => { desc.textContent = it.desc; }, onActivate: (it) => ctx.go(it.hash), numbers: true });
  return { bg: true, back: '#/menu', crumb: ['MORE'], hints: [['UP DOWN', 'MOVE'], ['Enter', 'OPEN'], ['1-3', 'JUMP'], ['Esc', 'MENU']], destroy: m.off };
}

// ---- mode picker (first step of PLAY) -------------------------------------------------------------------------------
const WHO = { classic: 'YOU STEER', ours: 'YOU STEER', arcade: 'YOU STEER', think: 'AI STEERS', versus: 'AI STEERS' };
export async function modePicker(root, ctx) {
  let thinking = store.get('pac.think', MD.thinkingOn(ctx.app.opts().intel));
  const ul = h('ul', { class: 'menu modes', role: 'menu', 'aria-label': 'Game modes' });
  const swLab = h('span', { class: 'mi-l' });
  const paintSw = () => { swLab.textContent = 'SHOW THE THINKING: ' + (thinking ? 'ON' : 'OFF'); };
  paintSw();
  const items = [
    ...MD.MODES.map((m) => ({ mode: m, tag: WHO[m.id], content: h('span', { class: 'mode-body' },
      h('span', { class: 'mode-name' }, m.name), h('span', { class: 'mode-what' }, m.what), h('span', { class: 'mode-see' }, m.see)) })),
    { sw: true, content: swLab, desc: 'ON draws each ghost’s job, route and orders on the maze while you play. OFF is just the game. Press T any time.' },
    { custom: true, label: 'CUSTOM...', desc: 'Choose the maze, the ghost team and the rules yourself.' },
  ];
  const note = h('p', { class: 'menu-desc', 'aria-live': 'polite' });
  root.replaceChildren(h('section', { class: 'menu-screen picker' }, h('h2', { class: 'screen-t' }, 'CHOOSE A MODE'), ul, note));
  const flip = () => { thinking = !thinking; store.set('pac.think', thinking); paintSw(); };
  const m = listMenu(ul, items, {
    onFocus: (it) => { note.textContent = it.mode ? (it.mode.id === 'think' ? 'This mode always shows the thinking.' : '') : it.desc; },
    onActivate: (it) => {
      if (it.sw) return flip();
      if (it.custom) return ctx.go('#/play/custom');
      store.set('pac.lastMode', it.mode.id);
      ctx.go(MD.runHash(it.mode, { seed: it.mode.seed != null ? it.mode.seed : Math.floor(Math.random() * 9000), thinking }));
    },
    numbers: true,
  });
  const last = MD.MODE_IDS.indexOf(store.get('pac.lastMode', 'ours'));
  m.set(Math.max(0, last));
  const off2 = keys((e) => {
    if (e.key === 't' || e.key === 'T') { flip(); }
    else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && items[m.index].sw) { e.preventDefault(); flip(); }
  });
  return { back: '#/menu', crumb: ['PLAY'], hints: [['UP DOWN', 'CHOOSE'], ['Enter', 'START'], ['1-7', 'JUMP'], ['T', 'THINKING'], ['Esc', 'MENU']], destroy: () => { m.off(); off2(); } };
}

// ---- custom setup (CUSTOM from the picker, and WATCH) -------------------------------------------------------------
const GROUP_NAME = { main: 'TEAMS', experimental: 'EXPERIMENTAL', maze: 'MAZES', demo: 'DEMO MAZES', ai: 'AI PAC-MAN' };
export async function setup(root, ctx, kind) {
  const meta = await ctx.app.getMeta();
  const saved = store.get('pac.setup.' + kind, {});
  const S = { layout: saved.layout || (kind === 'play' ? 'originalClassic' : 'smallClassic'),
    ghosts: saved.ghosts || (kind === 'play' ? 'EnhancedCoordinatedGhostTeam' : 'DirectionalGhost'),
    arcade: saved.arcade != null ? saved.arcade : false,
    intel: saved.intel === 'classic' || saved.intel == null ? 'classic' : 'teacher', pacman: saved.pacman || 'AlphaBetaAgent', depth: saved.depth || 2 };
  const pacInfo = () => meta.pacmen.find((p) => p.name === S.pacman) || {};
  const teamChoices = () => meta.teams.filter((t) => S.arcade || !t.arcadeOnly)
    .map((t) => ({ v: t.name, l: t.label.toUpperCase(), g: t.group === 'experimental' ? 'experimental' : 'main', blurb: t.blurb }));
  const mazeChoices = () => meta.layouts.map((l) => ({ v: l, l: MD.niceMaze(l), g: l.startsWith('demo_') ? 'demo' : 'maze', blurb: MD.mazeBlurb(l) }));
  const rows = () => {
    const r = [];
    r.push({ id: 'layout', grp: 'BASIC', label: 'MAZE', choices: mazeChoices(), desc: () => MD.mazeBlurb(S.layout) });
    r.push({ id: 'ghosts', grp: 'BASIC', label: 'GHOST TEAM', choices: teamChoices(), desc: () => { const t = meta.teams.find((x) => x.name === S.ghosts) || {}; return t.blurb; } });
    if (kind === 'watch') {
      r.push({ id: 'pacman', grp: 'ADVANCED', label: 'PAC-MAN IS', choices: meta.pacmen.map((p) => ({ v: p.name, l: p.name.replace('Agent', '').toUpperCase(), g: 'ai', blurb: p.blurb })), desc: () => pacInfo().blurb });
      r.push({ id: 'depth', grp: 'ADVANCED', label: 'LOOK-AHEAD', choices: pacInfo().depth ? [1, 2, 3].map((d) => ({ v: d, l: d + (d === 1 ? ' STEP' : ' STEPS') })) : [{ v: S.depth, l: '-' }],
        desc: () => (pacInfo().depth ? 'How many moves ahead the AI thinks. Each extra step makes it much slower.' : 'This AI does not look ahead.') });
    }
    r.push({ id: 'arcade', grp: 'ADVANCED', label: 'RULES', choices: [{ v: false, l: 'ORIGINAL' }, { v: true, l: 'ARCADE' }], desc: () => (S.arcade
      ? 'Close to the real game: real speeds, scatter and chase phases, a ghost house, fruit. Dots 10, pellets 50, ghosts 200 to 1600.'
      : 'The course rules: one step at a time, -1 per move, +10 per dot, -500 if caught, +500 for clearing the maze.') });
    r.push({ id: 'intel', grp: 'ADVANCED', label: 'SHOW THE THINKING', choices: [{ v: 'classic', l: 'OFF' }, { v: 'teacher', l: 'ON' }],
      desc: () => (S.intel === 'teacher' ? 'Draws each ghost’s job, route and the Commander’s orders on the maze, with a running explanation.' : 'Just the game. Press T during a game to turn the thinking on.') });
    return r;
  };
  let R = rows(), row = 0, open = null, cur = 0;
  const list = h('ul', { class: 'opt-rows' });
  const desc = h('p', { class: 'menu-desc', 'aria-live': 'polite' });
  function fix() {
    if (!S.arcade && (meta.teams.find((t) => t.name === S.ghosts) || {}).arcadeOnly) S.ghosts = 'DirectionalGhost';
    if (!meta.layouts.includes(S.layout)) S.layout = meta.layouts[0];
    if (!meta.teams.some((t) => t.name === S.ghosts)) S.ghosts = 'DirectionalGhost';
    if (!pacInfo().depth) S.depth = 2;
  }
  function pickList(r) {
    const ul = h('ul', { class: 'pick', role: 'listbox', 'aria-label': r.label });
    let lastG = null;
    r.choices.forEach((c, n) => {
      if (c.g && c.g !== lastG && (r.choices.some((x) => x.g !== c.g) || c.g === 'experimental')) {
        ul.append(h('li', { class: 'pick-h', role: 'presentation' }, GROUP_NAME[c.g] || c.g.toUpperCase()));
      }
      lastG = c.g;
      ul.append(h('li', { role: 'none' }, h('button', { class: 'pick-o', role: 'option', 'aria-selected': String(n === cur), 'aria-current': String(n === cur), 'data-n': String(n),
        onclick: () => { cur = n; choose(); } }, h('span', { class: 'po-l' }, c.l), c.blurb ? h('span', { class: 'po-d' }, c.blurb) : null)));
    });
    return ul;
  }
  function paint() {
    fix(); R = rows();
    let lastGrp = null;
    const nodes = [];
    R.forEach((r, n) => {
      if (r.grp !== lastGrp) { nodes.push(h('li', { class: 'opt-group', role: 'presentation' }, r.grp)); lastGrp = r.grp; }
      const idx = Math.max(0, r.choices.findIndex((c) => c.v === S[r.id]));
      const curc = r.choices[idx] || r.choices[0];
      const many = r.choices.length > 3;
      nodes.push(h('li', { class: 'opt-item' },
        h('div', { class: 'opt-row', 'aria-current': String(n === row), onclick: (e) => { if (e.target.closest('.arrow')) return; row = n; if (many) openPick(); else paint(); } },
          h('span', { class: 'ol' }, r.label),
          h('button', { class: 'arrow left', 'aria-label': 'previous ' + r.label, onclick: () => { row = n; open = null; cycle(-1); } }, ''),
          h('span', { class: 'ov' }, curc.l),
          h('button', { class: 'arrow right', 'aria-label': 'next ' + r.label, onclick: () => { row = n; open = null; cycle(1); } }, '')),
        open === r.id ? pickList(r) : null));
    });
    nodes.push(h('li', { class: 'opt-row start', 'aria-current': String(row === R.length) }, h('button', { class: 'start-b', 'data-autofocus': '', onclick: start }, kind === 'play' ? 'START GAME' : 'START WATCHING')));
    list.replaceChildren(...nodes);
    const r = R[row];
    const c = r && r.choices.find((x) => x.v === S[r.id]);
    desc.textContent = r ? (open ? 'Up and Down to look, Enter to choose, Esc to close.' : ((c && c.g === 'experimental' ? 'EXPERIMENTAL. ' : '') + (r.desc() || ''))) : 'Press Enter to begin.';
    const sel = list.querySelector('.pick-o[aria-current="true"]'); if (sel) sel.scrollIntoView({ block: 'nearest' });
  }
  function openPick() {
    const r = R[row]; if (!r || r.choices.length < 2) return;
    open = r.id; cur = Math.max(0, r.choices.findIndex((c) => c.v === S[r.id])); paint();
  }
  function choose() { const r = R[row]; S[r.id] = r.choices[cur].v; open = null; paint(); }
  function cycle(d) {
    const r = R[row]; if (!r) return;
    const idx = Math.max(0, r.choices.findIndex((c) => c.v === S[r.id]));
    S[r.id] = r.choices[(idx + d + r.choices.length) % r.choices.length].v;
    paint();
  }
  function start() {
    fix(); store.set('pac.setup.' + kind, S);
    const q = new URLSearchParams({ kind, layout: S.layout, ghosts: S.ghosts, arcade: S.arcade ? '1' : '0', preset: S.intel, seed: String(Math.floor(Math.random() * 9000)) });
    if (kind === 'watch') { q.set('pacman', S.pacman); q.set('depth', String(S.depth)); }
    ctx.go('#/run?' + q);
  }
  paint();
  const title = kind === 'play' ? 'CUSTOM GAME' : 'WATCH AN AI';
  root.replaceChildren(h('section', { class: 'menu-screen setup' },
    h('h2', { class: 'screen-t' }, title), kind === 'watch' ? h('p', { class: 'menu-desc lead' }, 'Choose who plays Pac-Man and who plays the ghosts, then watch.') : null, list, desc));
  const off = keys((e) => {
    if (open) {
      const r = R[row];
      if (e.key === 'ArrowDown' || e.key === 's') { e.preventDefault(); cur = (cur + 1) % r.choices.length; paint(); }
      else if (e.key === 'ArrowUp' || e.key === 'w') { e.preventDefault(); cur = (cur - 1 + r.choices.length) % r.choices.length; paint(); }
      else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); choose(); }
      else if (e.key === 'Escape' || e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); open = null; paint(); }
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 's') { e.preventDefault(); row = Math.min(R.length, row + 1); paint(); }
    else if (e.key === 'ArrowUp' || e.key === 'w') { e.preventDefault(); row = Math.max(0, row - 1); paint(); }
    else if (e.key === 'ArrowLeft' || e.key === 'a') { e.preventDefault(); cycle(-1); }
    else if (e.key === 'ArrowRight' || e.key === 'd') { e.preventDefault(); cycle(1); }
    else if (e.key === 'Enter') { e.preventDefault(); if (row === R.length) start(); else if (R[row].choices.length > 3) openPick(); else { row = R.length; paint(); } }
  });
  const here = kind === 'play' ? '#/play' : '#/menu';
  return { get back() { return open ? null : here; }, crumb: kind === 'play' ? [['#/play', 'PLAY'], 'CUSTOM'] : ['WATCH'],
    hints: [['UP DOWN', 'ROW'], ['LEFT RIGHT', 'CHANGE'], ['Enter', 'LIST / START'], ['Esc', 'BACK']], destroy: off };
}

// ---- run (the game itself) -----------------------------------------------------------------------------------------
export async function run(root, ctx) {
  const q = ctx.q, kind = q.kind === 'play' ? 'play' : 'watch';
  const opts = ctx.app.opts();
  const meta = await ctx.app.getMeta();
  if (q.preset) ctx.app.layers = LY.stateFromPreset(['classic', 'coach', 'teacher'].includes(q.preset) ? q.preset : 'classic');
  const arcade = q.arcade === '1';
  const seed = q.seed != null && /^\d{1,9}$/.test(q.seed) ? Number(q.seed) : Math.floor(Math.random() * 9000);
  const params = { layout: q.layout || 'smallClassic', ghosts: q.ghosts || 'DirectionalGhost', arcade, level: 1, seed,
    tickRate: opts.speed, lives: kind === 'play' ? 3 : 1, pacman: kind === 'play' ? 'browser' : (q.pacman || 'GreedyAgent') };
  if (kind === 'watch' && q.depth) params.depth = Number(q.depth);
  const badge = MD.badgeFor({ kind, layout: params.layout, ghosts: params.ghosts, arcade, pacman: params.pacman, depth: params.depth, mode: q.mode }, meta.teams);
  const preset = ctx.app.layers.preset;
  const other = kind === 'play' ? MD.otherSide({ kind, layout: params.layout, ghosts: params.ghosts, arcade, preset }, seed) : null;
  const again = '#/run?' + new URLSearchParams({ ...q, seed: String(Math.floor(Math.random() * 9000)) });
  const back = q.mode ? '#/play' : (kind === 'play' ? '#/play' : '#/watch');
  const actions = [
    other ? { label: 'PLAY THE OTHER SIDE', hash: other.hash, primary: true, note: other.mode.name } : null,
    { label: kind === 'play' ? 'PLAY AGAIN' : 'WATCH AGAIN', hash: again, primary: !other },
    { label: kind === 'play' ? 'CHOOSE A MODE' : 'BACK', hash: back },
  ];
  const wrap = h('div', { class: 'game-wrap' });
  root.replaceChildren(wrap);
  const g = mountGame(wrap, { kind, params, layers: ctx.app.layers, tickRate: opts.speed, badge, actions, onAction: (a) => ctx.go(a.hash), onLayers: (l) => { ctx.app.layers = l; } });
  return { back, crumb: [[back, kind === 'play' ? 'PLAY' : 'WATCH'], badge.name],
    hints: kind === 'play'
      ? [['ARROWS', 'STEER'], ['Space', 'PAUSE'], ['T', 'THINKING'], ['L', 'PANEL'], ['Esc', 'QUIT']]
      : [['Space', 'PAUSE'], ['T', 'THINKING'], ['L', 'PANEL'], ['Esc', 'QUIT']],
    destroy: () => g.destroy() };
}

// ---- versus: the same Pac-Man and seed against the original ghosts and ours --------------------------------------
const VS_MAZES = ['originalClassic', 'mediumClassic', 'smallClassic'];
export async function versus(root, ctx) {
  let layout = VS_MAZES.includes(ctx.q.layout) ? ctx.q.layout : 'originalClassic';
  let seed = /^\d{1,6}$/.test(ctx.q.seed || '') ? Number(ctx.q.seed) : 7;
  const V = { data: null, pos: 0, acc: 0, timer: 0, poll: 0, ended: [false, false], paused: false, gen: 0, views: [] };
  const sides = ['stock', 'ours'].map((id, n) => {
    const count = h('p', { class: 'vs-count', 'aria-live': 'off' }, 'MOVES 0');
    const end = h('p', { class: 'vs-end', role: 'status' });
    const canvas = h('canvas', { 'aria-hidden': 'true' });
    const board = h('div', { class: 'board', 'aria-label': n ? 'Maze with our ghosts' : 'Maze with the original ghosts' }, canvas);
    const el = h('article', { class: 'vs-side', 'data-side': id }, h('h3', {}, n ? 'OUR GHOSTS' : 'ORIGINAL GHOSTS'), count, board, end);
    return { id, count, end, canvas, board, el };
  });
  const info = h('p', { class: 'vs-info' });
  const verdict = h('p', { class: 'vs-verdict', role: 'status', 'aria-live': 'polite' });
  const btn = (label, key, fn, primary) => h('button', { class: 'btn' + (primary ? ' solid' : ''), onclick: fn }, label, ' ', h('kbd', {}, key));
  const bar = h('div', { class: 'vs-actions' }, btn('WATCH AGAIN', 'R', () => replay()), btn('NEW SEED', 'N', () => rerun(Math.floor(Math.random() * 900) + 1)), btn('CHANGE MAZE', 'M', () => { layout = VS_MAZES[(VS_MAZES.indexOf(layout) + 1) % VS_MAZES.length]; rerun(seed); }));
  root.replaceChildren(h('section', { class: 'versus' }, h('h2', { class: 'screen-t' }, 'VERSUS'),
    h('p', { class: 'vs-lead' }, 'The same Pac-Man, the same maze, the same dice. Only the ghosts are different.'),
    verdict, h('div', { class: 'vs-grid' }, sides[0].el, sides[1].el), info, bar));

  const stop = () => { clearInterval(V.timer); clearTimeout(V.poll); V.timer = 0; };
  const clearViews = () => { V.views.forEach((v) => v.destroy()); V.views = []; };
  async function rerun(newSeed) {
    stop(); clearViews(); V.data = null; seed = newSeed; const gen = ++V.gen;
    verdict.textContent = 'Running both games...'; verdict.classList.remove('done');
    info.textContent = `${MD.niceMaze(layout)} maze, seed ${seed}. The same seed always gives the same two games.`;
    sides.forEach((s) => { s.count.textContent = 'MOVES 0'; s.end.textContent = ''; s.el.classList.remove('win'); });
    history.replaceState(null, '', `#/versus?layout=${layout}&seed=${seed}`);
    try {
      await api('/api/versus/start', { layout, seed });
      const wait = async () => {
        const st = await api('/api/versus');
        if (gen !== V.gen) return;
        if (st.state === 'error') { verdict.textContent = 'Could not run: ' + st.error; return; }
        if (st.state !== 'done') { verdict.textContent = `Running both games... ${st.doneSides} of ${st.sides} done`; V.poll = setTimeout(wait, 300); return; }
        const data = await api('/api/versus/result');
        if (gen !== V.gen) return;
        V.data = data; begin();
      };
      await wait();
    } catch (e) { if (gen === V.gen) verdict.textContent = 'Could not run: ' + (e.message || e); }
  }
  function begin() {
    clearViews();
    const smooth = store.get('pac.opts', {}).smooth !== false;
    V.data.sides.forEach((sd, n) => {
      const view = new ArcadeView(sides[n].canvas, { layers: {}, reduceMotion: reduceMotion(), smooth });
      sides[n].board.style.setProperty('--ar', `${sd.header.width} / ${sd.header.height}`);
      view.setHeader(sd.header); view.start(); V.views.push(view);
    });
    replay();
  }
  function replay() {
    if (!V.data) return;
    stop(); V.pos = 0; V.ended = [false, false]; V.paused = false;
    verdict.textContent = ''; verdict.classList.remove('done');
    sides.forEach((s) => { s.end.textContent = ''; s.el.classList.remove('win'); s.count.textContent = 'MOVES 0'; });
    V.views.forEach((v) => { v.prev = null; v.setPhase('playing'); });
    V.acc = performance.now();
    V.timer = setInterval(step, 16);
  }
  function endLine(sd) {
    if (sd.caughtAt != null) return `CAUGHT PAC-MAN AFTER ${sd.caughtAt} MOVES`;
    if (sd.cleared) return `PAC-MAN CLEARED THE MAZE IN ${sd.ticks} MOVES`;
    return `PAC-MAN STILL FREE AFTER ${sd.ticks} MOVES`;
  }
  function step() {
    const now = performance.now();
    if (V.paused) { V.acc = now; return; }
    const rate = Math.round(V.data.sides[0].header.tickRate || 15), dt = 1000 / rate;
    let n = 0;
    while (V.acc <= now && n++ < 8) {
      V.data.sides.forEach((sd, i) => {
        if (V.ended[i]) return;
        const f = sd.frames[V.pos];
        if (f) { V.views[i].push(f); sides[i].count.textContent = `MOVES ${V.pos}   SCORE ${f.score}`; }
        if (V.pos >= sd.frames.length - 1) {
          V.ended[i] = true; sides[i].end.textContent = endLine(sd);
          if (sd.caughtAt != null) V.views[i].setPhase('dying');
        }
      });
      V.pos++; V.acc += dt;
      if (V.ended[0] && V.ended[1]) { finish(); break; }
    }
  }
  function finish() {
    stop();
    const [a, b] = V.data.sides;
    if (a.caughtAt != null && b.caughtAt != null && a.caughtAt !== b.caughtAt) sides[a.caughtAt < b.caughtAt ? 0 : 1].el.classList.add('win');
    else if ((a.caughtAt != null) !== (b.caughtAt != null)) sides[a.caughtAt != null ? 0 : 1].el.classList.add('win');
    verdict.textContent = V.data.verdict; verdict.classList.add('done');
  }
  rerun(seed);
  const off = keys((e) => {
    const k = e.key.toLowerCase();
    if (k === 'r') replay();
    else if (k === 'n') rerun(Math.floor(Math.random() * 900) + 1);
    else if (k === 'm') { layout = VS_MAZES[(VS_MAZES.indexOf(layout) + 1) % VS_MAZES.length]; rerun(seed); }
    else if (k === ' ') { e.preventDefault(); V.paused = !V.paused; }
  });
  return { back: '#/play', crumb: [['#/play', 'PLAY'], 'VERSUS'], hints: [['R', 'WATCH AGAIN'], ['N', 'NEW SEED'], ['M', 'CHANGE MAZE'], ['Space', 'PAUSE'], ['Esc', 'BACK']],
    destroy: () => { off(); stop(); V.gen++; clearViews(); fetch('/api/versus/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', keepalive: true }).catch(() => {}); } };
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
  return { back: '#/menu', crumb: ['LEVEL SELECT'], hints: [['UP DOWN', 'MOVE'], ['Enter', 'OPEN'], ['Esc', 'MENU']], destroy: m.off };
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
  return { back: '#/levels', crumb: [['#/levels', 'LEVEL SELECT'], `LEVEL ${n < 7 ? n : 'BONUS'}`], hints: [['Enter', 'TRY IT'], ['LEFT RIGHT', 'PREV / NEXT LEVEL'], ['Esc', 'LEVELS']],
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
  return { back: '#/menu', crumb: ['REPLAYS'], hints: [['UP DOWN', 'MOVE'], ['Enter', 'WATCH'], ['Esc', 'MENU']], destroy: m.off };
}

export async function replay(root, ctx, name) {
  const wrap = h('div', { class: 'game-wrap' });
  root.replaceChildren(wrap);
  const opts = ctx.app.opts();
  const g = mountGame(wrap, { kind: 'replay', trace: name, layers: ctx.app.layers, tickRate: opts.speed, onLayers: (l) => { ctx.app.layers = l; } });
  return { back: '#/replays', crumb: [['#/replays', 'REPLAYS'], name.length > 28 ? name.slice(0, 26) + '..' : name],
    hints: [['Space', 'PAUSE'], ['LEFT RIGHT', 'STEP (Shift x10)'], ['+ -', 'SPEED'], ['L', 'LAYERS'], ['1-0 H C', 'TOGGLE'], ['Esc', 'LIST']], destroy: () => g.destroy() };
}

// ---- options / about -------------------------------------------------------------------------------------------------
export async function options(root, ctx) {
  const o = ctx.app.opts();
  const defs = [
    { id: 'speed', label: 'GAME SPEED', ch: [[10, 'SLOW'], [15, 'ARCADE'], [20, 'FAST'], [30, 'TURBO']], note: 'Rounds per second. 15 is close to the real arcade pace.' },
    { id: 'smooth', label: 'SMOOTH MOTION', ch: [[true, 'ON'], [false, 'OFF']], note: 'Slides characters between ticks. Always off when the system asks for reduced motion.' },
    { id: 'scan', label: 'SCANLINES', ch: [[true, 'ON'], [false, 'OFF']], note: 'A faint CRT line pattern. Static: it never flickers.' },
    { id: 'intel', label: 'SHOW THE THINKING', ch: [['classic', 'OFF'], ['teacher', 'ON']], note: 'Draws what the ghosts are planning on the maze. You can also press T during a game.' },
  ];
  let row = 0;
  const ul = h('ul', { class: 'opt-rows' }), desc = h('p', { class: 'menu-desc' });
  const paint = () => {
    const cur = ctx.app.opts();
    ul.replaceChildren(...defs.map((d, n) => {
      const i = Math.max(0, d.ch.findIndex((c) => c[0] === (d.id === 'intel' && cur.intel === 'coach' ? 'teacher' : cur[d.id])));
      return h('li', { class: 'opt-row', 'aria-current': String(n === row) }, h('span', { class: 'ol' }, d.label),
        h('button', { class: 'arrow left', 'aria-label': 'previous', onclick: () => { row = n; cyc(-1); } }, ''), h('span', { class: 'ov' }, d.ch[i][1]),
        h('button', { class: 'arrow right', 'aria-label': 'next', onclick: () => { row = n; cyc(1); } }, ''));
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
  return { back: '#/menu', crumb: ['OPTIONS'], hints: [['UP DOWN', 'ROW'], ['LEFT RIGHT', 'CHANGE'], ['Esc', 'MENU']], destroy: off };
}

export async function about(root, ctx) {
  root.replaceChildren(h('section', { class: 'menu-screen wide about' }, h('h2', { class: 'screen-t' }, 'ABOUT'),
    h('p', {}, 'This is a Pac-Man game you can read. It started as the original Berkeley CS188 game, then grew a team of ghosts that work together, a way to record and replay games, a score table and an arcade rule set.'),
    h('p', {}, 'The maze on screen is the real game. The extra drawings (SHOW THE THINKING) show what the ghost team decided, taken from the game\'s own state.'),
    h('h3', {}, 'CONTROLS'),
    h('dl', { class: 'how-rows' }, h('dt', {}, 'Arrows / WASD'), h('dd', {}, 'steer Pac-Man, or move in menus'), h('dt', {}, 'Enter / Esc'), h('dd', {}, 'select / go back'), h('dt', {}, 'Space'), h('dd', {}, 'pause'),
      h('dt', {}, 'T'), h('dd', {}, 'turn SHOW THE THINKING on or off'), h('dt', {}, 'L'), h('dd', {}, 'open or close the side panel'), h('dt', {}, '1 to 0, H, C'), h('dd', {}, 'toggle one layer (C = Commander)')),
    h('h3', {}, 'CREDITS'),
    h('p', {}, 'Framework credit: UC Berkeley, educational use. Arcade rules follow the Pac-Man Dossier. Fonts: Press Start 2P and Space Mono, SIL Open Font License 1.1, bundled; nothing loads from the network.'),
    h('p', { class: 'cap' }, 'Everything runs on 127.0.0.1. Files: dashboard/README.md, docs/ARCHITECTURE.md, docs/ARCADE_MODE.md, dashboard/DESIGN.md.')));
  return { back: '#/menu', crumb: ['ABOUT'], hints: [['Esc', 'MENU']] };
}
