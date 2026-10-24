// Search visualiser. The data is the real expansion order recorded from search.py by dashboard/searchviz.py.
// The animation only replays that list; nothing here searches.
import { h, api, store, reduceMotion } from './util.js';

const ALGOS = [['dfs', 'DFS'], ['bfs', 'BFS'], ['ucs', 'UCS'], ['astar', 'A*']];
const MAZES = [['tinyMaze', 'tiny'], ['mediumMaze', 'medium'], ['bigMaze', 'big']];
const TAU = Math.PI * 2;

export function mountSearchViz(root, { auto } = {}) {
  const S = { algo: 'astar', maze: 'mediumMaze', data: null, i: 0, phase: 'idle', raf: 0, speed: 1, showExp: true, showFront: true, showPath: true,
    expSet: new Map(), front: new Set(), pathI: 0, busy: false };
  const abort = new AbortController();
  const el = {};
  el.cv = h('canvas', { 'aria-label': 'Search animation', role: 'img' });
  el.box = h('div', { class: 'sv-board' }, el.cv);
  el.exp = h('b', {}, '0'); el.cost = h('b', {}, '-'); el.front = h('b', {}, '0'); el.status = h('p', { class: 'sv-status', role: 'status' }, 'Pick an algorithm and a maze, then RUN.');
  el.algoBtns = ALGOS.map(([k, l]) => h('button', { class: 'btn chip', 'data-k': k, onclick: () => { S.algo = k; paintControls(); } }, l));
  el.mazeBtns = MAZES.map(([k, l]) => h('button', { class: 'btn chip', 'data-k': k, onclick: () => { S.maze = k; paintControls(); } }, l));
  el.run = h('button', { class: 'btn solid', onclick: () => run() }, 'RUN');
  el.all = h('button', { class: 'btn', onclick: () => compareAll() }, 'COMPARE ALL FOUR');
  el.speed = h('input', { type: 'range', min: '0.5', max: '6', step: '0.5', value: '1', 'aria-label': 'Animation speed', oninput: (e) => { S.speed = +e.target.value; } });
  const chk = (key, label, k) => h('label', { class: 'sv-chk' }, h('input', { type: 'checkbox', checked: true, onchange: (e) => { S[key] = e.target.checked; draw(); } }), label, h('kbd', {}, k));
  el.layers = h('div', { class: 'sv-layers', role: 'group', 'aria-label': 'Search layers' },
    chk('showExp', 'Expanded cells', 'E'), chk('showFront', 'Frontier', 'F'), chk('showPath', 'Final path', 'P'));
  el.table = h('div', { class: 'sv-table' });
  root.replaceChildren(h('div', { class: 'sv' },
    h('div', { class: 'sv-ctl' },
      h('div', { class: 'sv-row' }, h('span', { class: 'lab' }, 'ALGORITHM'), ...el.algoBtns),
      h('div', { class: 'sv-row' }, h('span', { class: 'lab' }, 'MAZE'), ...el.mazeBtns),
      h('div', { class: 'sv-row' }, el.run, el.all, h('label', { class: 'sv-speed' }, 'speed', el.speed)),
      el.layers),
    el.box,
    h('dl', { class: 'sv-read' }, h('div', {}, h('dt', {}, 'EXPANDED'), h('dd', {}, el.exp)), h('div', {}, h('dt', {}, 'FRONTIER'), h('dd', {}, el.front)),
      h('div', {}, h('dt', {}, 'PATH COST'), h('dd', {}, el.cost))),
    el.status, el.table,
    h('p', { class: 'cap' }, 'Source: the real functions in search.py, run on the real PositionSearchProblem; the order below is recorded by wrapping the problem, not re-implemented.')));

  function paintControls() {
    el.algoBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === S.algo)));
    el.mazeBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.k === S.maze)));
  }
  paintControls();

  function cellGeom() {
    const d = S.data, r = el.box.getBoundingClientRect(), dpr = Math.min(devicePixelRatio || 1, 2);
    el.cv.width = Math.max(2, Math.round(r.width * dpr)); el.cv.height = Math.max(2, Math.round(r.height * dpr));
    const c = Math.min(el.cv.width / d.width, el.cv.height / d.height);
    return { c, ox: (el.cv.width - c * d.width) / 2, oy: (el.cv.height - c * d.height) / 2 };
  }

  function draw() {
    const d = S.data; if (!d) return;
    const g = cellGeom(), ctx = el.cv.getContext('2d'), cs = getComputedStyle(document.documentElement);
    const col = (n) => cs.getPropertyValue(n).trim();
    const X = (x) => g.ox + x * g.c, Y = (y) => g.oy + (d.height - 1 - y) * g.c;
    ctx.fillStyle = col('--void'); ctx.fillRect(0, 0, el.cv.width, el.cv.height);
    ctx.fillStyle = col('--wall-fill');
    d.walls.forEach((row, ry) => { for (let x = 0; x < d.width; x++) if (row[x] === '%') ctx.fillRect(g.ox + x * g.c, g.oy + ry * g.c, g.c + 0.5, g.c + 0.5); });
    const n = Math.max(1, d.expanded.length);
    if (S.showExp) {
      for (const [k, i] of S.expSet) {
        const [x, y] = k.split(',').map(Number), t = i / n;
        ctx.fillStyle = `oklch(${0.45 + 0.4 * t} ${0.1 + 0.08 * t} ${200 - 120 * t})`;
        ctx.fillRect(X(x) + 1, Y(y) + 1, g.c - 2, g.c - 2);
      }
    }
    if (S.showFront) {
      ctx.strokeStyle = col('--order'); ctx.lineWidth = Math.max(1, g.c * 0.12);
      for (const k of S.front) { const [x, y] = k.split(',').map(Number); ctx.strokeRect(X(x) + g.c * 0.2, Y(y) + g.c * 0.2, g.c * 0.6, g.c * 0.6); }
    }
    if (S.showPath && S.pathI > 0) {
      ctx.strokeStyle = col('--pac'); ctx.lineWidth = Math.max(2, g.c * 0.34); ctx.lineJoin = ctx.lineCap = 'round';
      ctx.beginPath();
      d.path.slice(0, S.pathI + 1).forEach(([x, y], i) => (i ? ctx.lineTo(X(x) + g.c / 2, Y(y) + g.c / 2) : ctx.moveTo(X(x) + g.c / 2, Y(y) + g.c / 2)));
      ctx.stroke();
    }
    ctx.fillStyle = col('--pac'); ctx.beginPath(); ctx.arc(X(d.start[0]) + g.c / 2, Y(d.start[1]) + g.c / 2, g.c * 0.42, 0.4, TAU - 0.4); ctx.lineTo(X(d.start[0]) + g.c / 2, Y(d.start[1]) + g.c / 2); ctx.fill();
    ctx.fillStyle = col('--dot'); ctx.beginPath(); ctx.arc(X(d.goal[0]) + g.c / 2, Y(d.goal[1]) + g.c / 2, g.c * 0.28, 0, TAU); ctx.fill();
  }

  async function fetchViz(algo, maze) { return api(`/api/searchviz?algo=${algo}&maze=${maze}`); }

  async function run() {
    if (S.busy) return;
    S.busy = true; el.run.disabled = true; cancelAnimationFrame(S.raf);
    el.status.textContent = 'Running the real search...';
    try {
      S.data = await fetchViz(S.algo, S.maze);
      S.i = 0; S.pathI = 0; S.expSet = new Map(); S.front = new Set(); S.phase = 'expanding';
      el.exp.textContent = '0'; el.cost.textContent = '-'; el.front.textContent = '0';
      el.box.style.setProperty('--ar', `${S.data.width} / ${S.data.height}`);
      store.set('pac.sv', { algo: S.algo, maze: S.maze });
      if (reduceMotion()) { S.i = S.data.expanded.length; advance(S.data.expanded.length); S.pathI = S.data.path.length; finish(); draw(); }
      else loop();
    } catch (e) { el.status.textContent = 'Failed: ' + e.message; }
    S.busy = false; el.run.disabled = false;
  }

  function advance(count) {
    const d = S.data;
    for (let k = 0; k < count && S.i < d.expanded.length; k++, S.i++) {
      const c = d.expanded[S.i], key = c[0] + ',' + c[1];
      S.expSet.set(key, S.i); S.front.delete(key);
      for (const s of d.succ[S.i]) { const sk = s[0] + ',' + s[1]; if (!S.expSet.has(sk)) S.front.add(sk); }
    }
    el.exp.textContent = String(S.i); el.front.textContent = String(S.front.size);
  }
  function finish() {
    S.phase = 'done'; el.cost.textContent = String(S.data.cost); el.exp.textContent = String(S.data.expandedCount);
    el.status.textContent = `${S.data.label} on ${S.data.maze}: looked at ${S.data.expandedCount} cells, found a path of cost ${S.data.cost}.`;
  }
  function loop() {
    const d = S.data;
    const per = Math.max(1, Math.ceil(d.expanded.length / (60 * 4)) * S.speed);
    if (S.phase === 'expanding') { advance(per); if (S.i >= d.expanded.length) { S.phase = 'path'; el.status.textContent = 'Goal reached. Tracing the path...'; } }
    else if (S.phase === 'path') { S.pathI = Math.min(d.path.length - 1, S.pathI + Math.max(1, Math.ceil(d.path.length / 90) * S.speed)); if (S.pathI >= d.path.length - 1) finish(); }
    draw();
    if (S.phase !== 'done') S.raf = requestAnimationFrame(loop);        // loop ends by itself: no idle rAF
  }

  async function compareAll() {
    el.all.disabled = true; el.table.textContent = 'Running all four...';
    try {
      const rows = [];
      for (const [k] of ALGOS) { const d = await fetchViz(k, S.maze); rows.push(d); }
      el.table.replaceChildren(h('table', {},
        h('caption', {}, `Same maze (${S.maze}), same goal`),
        h('thead', {}, h('tr', {}, h('th', {}, 'Algorithm'), h('th', {}, 'Cells expanded'), h('th', {}, 'Path cost'))),
        h('tbody', {}, ...rows.map((d) => h('tr', {}, h('td', {}, d.label), h('td', {}, d.expandedCount), h('td', {}, d.cost))))));
    } catch (e) { el.table.textContent = 'Failed: ' + e.message; }
    el.all.disabled = false;
  }

  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey || /input|select|textarea/i.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    const map = { e: 'showExp', f: 'showFront', p: 'showPath' };
    if (map[k]) { S[map[k]] = !S[map[k]]; el.layers.querySelectorAll('input')[['e', 'f', 'p'].indexOf(k)].checked = S[map[k]]; draw(); }
  }, { signal: abort.signal });
  const ro = new ResizeObserver(() => draw()); ro.observe(el.box);
  const saved = store.get('pac.sv', null);
  if (saved && ALGOS.some((a) => a[0] === saved.algo) && MAZES.some((m) => m[0] === saved.maze)) { S.algo = saved.algo; S.maze = saved.maze; paintControls(); }
  if (auto) { S.algo = 'astar'; S.maze = 'mediumMaze'; paintControls(); run(); }

  return { run, destroy() { abort.abort(); cancelAnimationFrame(S.raf); ro.disconnect(); }, state: S };
}
