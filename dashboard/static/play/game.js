// GameScreen: the arcade cabinet (HUD + board + splash) and the intel side panel (layers, tickers, teacher).
// One component serves live play, AI watching, trace replay and the title's attract mode.
import { h, api, store, pad, fmtScore, reduceMotion } from './util.js';
import { ArcadeView } from './render.js';
import * as LY from './layers.js';

const MAX_TICKER = 14;
const FRUIT_KINDS = ['cherry', 'strawberry', 'orange', 'apple', 'melon', 'galaxian', 'bell', 'key'];

export function pacIcon(size = 16) {
  return h('span', { class: 'life', 'aria-hidden': 'true', style: `width:${size}px;height:${size}px` });
}

/** Bring a v1 / hand-made trace frame up to what the renderer reads. */
export function normFrame(f) {
  f.dt = f.dt || 0.0667;
  if (!f.pacman.fpos) f.pacman.fpos = f.pacman.pos.slice();
  for (const g of f.ghosts) {
    if (!g.fpos) g.fpos = g.pos.slice();
    if (!g.mode) g.mode = g.scaredTimer > 0 ? 'frightened' : 'active';
  }
  f.reservedTiles = f.reservedTiles || [];
  return f;
}

export function mountGame(root, opts) {
  const kind = opts.kind;                        // play | watch | replay | attract
  const attract = kind === 'attract';
  const P = opts.params || {};
  let layers = opts.layers;
  const S = {
    live: kind === 'play' || kind === 'watch', phase: 'ready', prevFrame: null, frame: null, header: null, paused: false,
    score: 0, hi: store.get('pac.hi', 0), lives: 0, level: 1, over: false, es: null, timer: 0, frames: [], pos: 0,
    speed: 1, tickRate: opts.tickRate || 15, capText: '', cmdSeen: -1, chatSeen: new Set(), entering: null,
  };
  const abort = new AbortController();

  // ---- DOM ---------------------------------------------------------------------------------------------
  const el = {};
  el.score = h('b', { class: 'hud-num', id: 'hScore' }, '00');
  el.hi = h('b', { class: 'hud-num' }, pad(S.hi, 2));
  el.hud = h('div', { class: 'hud', 'aria-label': 'Score' },
    h('div', { class: 'hud-cell' }, h('span', { class: 'hud-lab blink' }, '1UP'), el.score),
    h('div', { class: 'hud-cell hud-mid' }, h('span', { class: 'hud-lab' }, 'HIGH SCORE'), el.hi));
  el.canvas = h('canvas', { 'aria-hidden': 'true' });
  el.splash = h('div', { class: 'splash', role: 'status', 'aria-live': 'polite' });
  el.board = h('div', { class: 'board', tabindex: '0', 'aria-label': kind === 'play' ? 'Maze. Arrow keys or W A S D steer Pac-Man. Space pauses.' : 'Maze' }, el.canvas, el.splash);
  el.lives = h('div', { class: 'lives', 'aria-label': 'Lives' });
  el.fruit = h('div', { class: 'fruit-row', 'aria-hidden': 'true' });
  el.lvl = h('span', { class: 'hud-lvl' }, '');
  el.foot = h('div', { class: 'hud-foot' }, el.lives, el.lvl, el.fruit);
  el.tactical = h('p', { class: 'tactical', hidden: true });
  el.dpad = h('div', { class: 'dpad', 'aria-label': 'Touch controls' },
    ...[['North', '↑'], ['West', '←'], ['South', '↓'], ['East', '→']].map(([d, s]) =>
      h('button', { class: 'btn', 'aria-label': d, onclick: () => steer(d) }, s)));
  el.cab = h('div', { class: 'cab' }, attract ? null : el.hud, el.board, attract ? null : el.foot,
    attract ? null : el.tactical, kind === 'play' ? el.dpad : null);

  // intel panel
  el.presets = h('div', { class: 'presets', role: 'group', 'aria-label': 'Layer presets' });
  el.layerList = h('ul', { class: 'layer-list' });
  el.caption = h('p', { class: 'caption', 'aria-live': 'off' });
  el.legend = h('dl', { class: 'legend' }, ...LY.LEGEND.flatMap(([a, b]) => [h('dt', {}, a), h('dd', {}, b)]));
  el.teacher = h('section', { class: 'teacher' }, h('p', { class: 'eyebrow' }, 'TEACHER'), el.caption,
    h('details', { open: true }, h('summary', {}, 'Legend'), el.legend));
  el.cmdLane = h('ol', { class: 'ticker', role: 'log', 'aria-label': 'Commander orders' });
  el.chatLane = h('ol', { class: 'ticker chat', role: 'log', 'aria-label': 'Ghost chatter' });
  el.cmdSec = h('section', {}, h('p', { class: 'eyebrow split' }, h('span', {}, 'Commander'), h('span', { id: 'cmdSrc' }, 'no coordinator')), el.cmdLane);
  el.chatSec = h('section', {}, h('p', { class: 'eyebrow split' }, h('span', {}, 'Ghost chatter'), h('span', {}, 'ghost to ghost')), el.chatLane);
  el.roster = h('ol', { class: 'roster' });
  el.ai = h('section', { class: 'ai', hidden: true });
  el.meta = h('p', { class: 'run-meta' });
  el.panelBody = h('div', { class: 'intel-body' },
    h('p', { class: 'eyebrow' }, 'Layers'), el.presets, el.layerList, el.teacher, el.ai, el.cmdSec, el.chatSec,
    h('section', {}, h('p', { class: 'eyebrow split' }, h('span', {}, 'Ghosts'), h('span', {}, 'mode')), el.roster), el.meta);
  el.panel = h('aside', { class: 'intel', 'aria-label': 'Intel overlay controls and tickers' },
    h('div', { class: 'intel-head' }, h('span', {}, 'INTEL'), h('kbd', {}, 'L')), el.panelBody);
  const panelOpen0 = store.get('pac.panel', !attract && layers.preset !== 'classic');
  root.replaceChildren(h('div', { class: 'game' + (attract ? ' attract' : '') + (panelOpen0 && !attract ? '' : ' no-panel'), 'data-kind': kind },
    el.cab, attract ? null : el.panel));
  const gameEl = root.firstChild;

  const view = new ArcadeView(el.canvas, { layers: layers.on, reduceMotion: reduceMotion(), smooth: store.get('pac.opts', {}).smooth !== false });
  view.start();

  // ---- panel ---------------------------------------------------------------------------------------------
  function drawPanel() {
    el.presets.replaceChildren(...Object.entries(LY.PRESETS).map(([k, p]) =>
      h('button', { class: 'btn chip', 'aria-pressed': String(layers.preset === k), onclick: () => setLayers(LY.stateFromPreset(k)) }, p.label)));
    el.layerList.replaceChildren(...LY.LAYERS.map((l) => h('li', {},
      h('label', { title: l.note }, h('input', { type: 'checkbox', checked: layers.on[l.id], onchange: () => setLayers(LY.toggle(layers, l.id)) }),
        h('span', { class: 'lname' }, l.label), h('kbd', {}, l.key.toUpperCase())))));
    el.teacher.hidden = layers.preset !== 'teacher';
    el.cmdSec.hidden = !layers.on.commander;
    el.chatSec.hidden = !layers.on.chatter;
    el.tactical.hidden = !layers.on.tactical;
    gameEl.dataset.preset = layers.preset;
  }
  function setLayers(next) {
    layers = next; view.setLayers(layers.on); drawPanel();
    store.set('pac.layers', layers);
    if (opts.onLayers) opts.onLayers(layers);
    if (S.frame) panels(S.frame);
  }
  function setPanel(open) {
    gameEl.classList.toggle('no-panel', !open); store.set('pac.panel', open);
    requestAnimationFrame(() => view.resize());
  }
  drawPanel();

  // ---- stream (live) ---------------------------------------------------------------------------------------
  function connect() {
    const es = new EventSource('/live/stream');
    S.es = es;
    // The hub replays the previous session's last header/frame/status to a new subscriber: accept only our own game.
    const mine = (hd) => hd.layout === P.layout && hd.ghostTeam === P.ghosts && hd.seed >= P.seed && hd.seed < P.seed + 16;
    es.addEventListener('header', (e) => { const hd = JSON.parse(e.data); if (mine(hd)) { S.accept = true; onHeader(hd); } });
    es.addEventListener('frame', (e) => { if (S.accept) onFrame(JSON.parse(e.data)); });
    es.addEventListener('status', (e) => { const s = JSON.parse(e.data); if (s.params && s.params.seed === P.seed) onStatus(s); });
    es.addEventListener('end', (e) => { if (S.accept) onEnd(JSON.parse(e.data)); });
  }
  async function startLive() {
    el.splash.replaceChildren(h('p', { class: 'splash-t dim' }, 'LOADING'));
    try {
      connect();
      await api('/api/live/start', { ...P, campaign: true });
    } catch (e) { splash('ERROR', 'red', String(e.message || e)); }
  }

  // ---- trace replay ----------------------------------------------------------------------------------------
  async function startTrace() {
    try {
      const text = await (await fetch('/api/traces/' + encodeURIComponent(opts.trace), { signal: abort.signal })).text();
      const recs = text.split('\n').filter(Boolean).map((l) => JSON.parse(l));
      const header = recs[0];
      S.frames = recs.filter((r) => r.type === 'frame').map(normFrame);
      S.tickRate = Math.round(header.tickRate || 15);
      onHeader(header);
      S.pos = 0; setPhase('playing');
      S.acc = performance.now();
      S.timer = setInterval(stepTrace, 16);
      el.meta.textContent = `${opts.trace}`;
    } catch (e) { if (e.name !== 'AbortError') splash('NO TRACE', 'red', String(e.message || e)); }
  }
  function stepTrace() {
    const now = performance.now();
    if (S.paused) { S.acc = now; return; }
    const step = 1000 / (S.tickRate * S.speed);
    let n = 0;
    while (S.acc <= now && S.pos < S.frames.length && n++ < 8) { onFrame(S.frames[S.pos++]); S.acc += step; }
    if (S.pos >= S.frames.length) {
      if (opts.loop) { S.pos = 0; view.resetTrail(); onHeader(S.header); }
      else { clearInterval(S.timer); splash('END OF REPLAY', 'white'); }
    }
  }
  function seek(delta) {
    if (kind !== 'replay' || !S.frames.length) return;
    S.paused = true; paintPause();
    S.pos = Math.max(0, Math.min(S.frames.length - 1, S.pos + delta));
    view.prev = null; onFrame(S.frames[S.pos]);
  }

  // ---- events --------------------------------------------------------------------------------------------
  function onHeader(hd) {
    S.header = hd;
    el.board.style.setProperty('--ar', `${hd.width} / ${hd.height}`);
    gameEl.style.setProperty('--arn', hd.width / hd.height);
    view.setHeader(hd);
    el.cmdLane.replaceChildren(); el.chatLane.replaceChildren(); S.chatSeen.clear();
    el.meta.textContent = `${hd.layout} · ${hd.pacmanAgent} vs ${hd.ghostTeam}${hd.arcade ? ' · arcade rules, level ' + hd.level : ' · Berkeley rules'} · seed ${hd.seed}`;
    if (S.live) setPhase('ready');
  }
  function onFrame(f) {
    S.prevFrame = S.frame; S.frame = f;
    if (kind === 'replay' || attract) f.hud = f.hud || null;
    view.push(f);
    S.score = f.score;
    panels(f);
  }
  function onStatus(s) {
    S.paused = !!s.paused;
    if (s.lives != null) { S.lives = s.lives; S.level = s.level; drawLives(); }
    if (s.phase) setPhase(S.paused && s.phase === 'playing' ? 'paused' : s.phase);
    else if (S.paused) setPhase('paused');
    if (s.state === 'error') splash('ERROR', 'red', (s.result && s.result.error) || '');
  }
  function onEnd(r) {
    if (r.error) return splash('ERROR', 'red', r.error);
    S.over = true;
    finishScore(r.score);
  }

  function setPhase(p) {
    S.phase = p;
    view.setPhase(p === 'paused' ? 'playing' : p);
    if (p === 'ready') splash('READY!', 'yellow');
    else if (p === 'paused') splash('PAUSED', 'white');
    else if (p === 'cleared') splash('LEVEL CLEAR', 'white');
    else if (p === 'gameover') splash('GAME OVER', 'red');
    else if (p === 'dying') el.splash.replaceChildren();
    else el.splash.replaceChildren();
    paintPause();
  }
  function splash(text, color, sub) {
    el.splash.replaceChildren(...[h('p', { class: 'splash-t ' + color }, text), sub ? h('p', { class: 'splash-s' }, sub) : null].filter(Boolean));
  }
  function paintPause() { if (opts.onPause) opts.onPause(S.paused); }

  // ---- HUD / panel updates ---------------------------------------------------------------------------------
  let last = {};
  function setText(node, key, v) { if (last[key] !== v) { last[key] = v; node.textContent = v; } }
  function drawLives() {
    const n = Math.max(0, S.lives - 1);
    const key = 'l' + n;
    if (last.lives === key) return; last.lives = key;
    el.lives.replaceChildren(...Array.from({ length: Math.min(n, 8) }, () => pacIcon(18)));
  }
  function panels(f) {
    const hud = f.hud;
    setText(el.score, 'sc', pad(f.score < 0 ? 0 : f.score, 2));
    el.score.classList.toggle('neg', f.score < 0);
    if (f.score < 0) setText(el.score, 'sc', '-' + String(Math.abs(f.score)));
    setText(el.hi, 'hi', pad(Math.max(S.hi, f.score), 2));
    if (hud) {
      if (hud.lives != null && hud.lives !== S.lives) { S.lives = hud.lives; drawLives(); }
      setText(el.lvl, 'lvl', 'LEVEL ' + hud.level);
      const fk = hud.fruitHistory.join();
      if (last.fk !== fk) { last.fk = fk; el.fruit.replaceChildren(...hud.fruitHistory.map(fruitIcon)); }
    } else if (!S.live && S.header) setText(el.lvl, 'lvl', S.header.arcade ? 'LEVEL ' + (S.header.level || 1) : '');
    if (layers.on.tactical) {
      const t = f.tacticalState ? `${String(f.tacticalState).replace(/_/g, ' ')}${f.macroStrategy ? ' · ' + String(f.macroStrategy).replace(/_/g, ' ') : ''}` : 'no coordinator state for this team';
      setText(el.tactical, 'tac', 'TACTICAL  ' + t);
    }
    // tickers
    const c = f.commander || { source: 'none', messages: [] };
    const src = el.cmdSec.querySelector('#cmdSrc'); if (src) setText(src, 'src', c.source === 'none' ? 'no coordinator' : c.source.replace(/^get/, '').toLowerCase());
    for (const m of c.messages) addLane(el.cmdLane, m, f);
    if (!el.cmdLane.children.length) el.cmdLane.append(h('li', { class: 'none' }, 'Waiting for the coordinator...'));
    const msgs = LY.readMessages(f);
    for (const m of view.newMsgs || []) addChat(m);
    if (!msgs.length && !el.chatLane.children.length) el.chatLane.append(h('li', { class: 'none' }, 'No messages: this team does not publish any.'));
    // roster
    if (f.tick % 3 === 0 || !el.roster.children.length) drawRoster(f);
    if (f.ai) drawAi(f.ai); else el.ai.hidden = true;
    if (layers.preset === 'teacher' && f.tick % 4 === 0) {
      const text = LY.captions(f, S.prevFrame).join(' ');
      if (text !== S.capText) { S.capText = text; el.caption.replaceChildren(...LY.captions(f, S.prevFrame).map((l) => h('span', { class: 'cap-line' }, l))); }
    }
  }
  function addLane(ol, m, f) {
    ol.querySelector('.none')?.remove();
    const g = m.ghost ? f.ghosts.find((q) => q.index === m.ghost) : null;
    const li = h('li', { 'data-kind': m.kind }, h('time', {}, 't' + m.tick), h('b', { class: 'src' }, m.src), h('span', { class: 'txt' }, m.text));
    if (g) li.style.setProperty('--c', view.ghostColor(g));
    ol.prepend(li);
    while (ol.children.length > MAX_TICKER) ol.lastElementChild.remove();
  }
  function addChat(m) {
    el.chatLane.querySelector('.none')?.remove();
    const li = h('li', { 'data-kind': 'chat' }, h('time', {}, m.tick != null ? 't' + m.tick : ''),
      h('b', { class: 'src' }, `G${m.from}>${m.to === 'all' || m.to == null ? 'ALL' : 'G' + m.to}`),
      h('span', { class: 'txt' }, `${m.type}${m.ackOf != null ? ' (ack)' : ''} ${LY.payloadText(m.payload)}`));
    el.chatLane.prepend(li);
    while (el.chatLane.children.length > MAX_TICKER) el.chatLane.lastElementChild.remove();
  }
  function drawRoster(f) {
    el.roster.replaceChildren(...f.ghosts.map((g) => {
      const li = h('li', { 'data-mode': g.mode },
        h('span', { class: 'glyph' }, g.role ? (g.role[0].toUpperCase()) : g.index),
        h('span', { class: 'rname' }, (g.role || 'ghost ' + g.index).replace('_', ' '), h('small', {}, '#' + g.index)),
        h('span', { class: 'rmode' }, g.mode), h('span', { class: 'rsub' }, g.target ? `→ ${g.target[0]},${g.target[1]}` : 'no target'));
      li.style.setProperty('--c', view.ghostColor(g));
      return li;
    }));
  }
  function drawAi(a) {
    el.ai.hidden = false;
    el.ai.replaceChildren(h('p', { class: 'eyebrow' }, 'Pac-Man agent'),
      h('p', { class: 'ai-name' }, a.name + (a.depth ? '  depth ' + a.depth : '')),
      h('dl', { class: 'stats' },
        h('div', {}, h('dt', {}, 'decisions'), h('dd', {}, a.decisions)),
        h('div', {}, h('dt', {}, 'last move'), h('dd', {}, `${a.lastMs} ms`)),
        h('div', {}, h('dt', {}, 'avg move'), h('dd', {}, `${a.avgMs} ms`)),
        h('div', {}, h('dt', {}, 'nodes (last)'), h('dd', {}, a.lastNodes)),
        h('div', {}, h('dt', {}, 'nodes (avg)'), h('dd', {}, a.avgNodes))),
      h('p', { class: 'cap' }, 'Nodes = game states generated while choosing the move.'));
  }
  function fruitIcon(kind) {
    const cv = h('canvas', { width: 28, height: 28, class: 'fruit' });
    drawFruitOn(cv, kind);
    return cv;
  }
  function drawFruitOn(cv, kind) {
    const fake = Object.create(ArcadeView.prototype);
    fake.ctx = cv.getContext('2d');
    fake.drawFruit(kind, 14, 14, 11);
  }

  // ---- scores ------------------------------------------------------------------------------------------------
  function finishScore(score) {
    if (kind !== 'play') return;
    if (score > S.hi) { S.hi = score; store.set('pac.hi', score); }
    const table = store.get('pac.scores', []);
    if (score > 0 && (table.length < 8 || score > table[table.length - 1].score)) enterInitials(score, table);
  }
  function enterInitials(score, table) {
    S.entering = { letters: [], score, table };
    drawInitials();
  }
  function drawInitials() {
    const e = S.entering; if (!e) return;
    const slots = [0, 1, 2].map((i) => h('span', { class: 'slot' + (i === e.letters.length ? ' cur' : '') }, e.letters[i] || '_'));
    el.splash.replaceChildren(h('p', { class: 'splash-t red' }, 'GAME OVER'),
      h('p', { class: 'splash-s' }, `NEW HIGH SCORE ${e.score}`), h('p', { class: 'initials' }, ...slots),
      h('p', { class: 'splash-s' }, 'TYPE 3 LETTERS, ENTER TO SAVE'));
  }
  function saveInitials() {
    const e = S.entering; if (!e || e.letters.length < 3) return;
    const row = { name: e.letters.join(''), score: e.score, layout: P.layout, ghosts: P.ghosts, rules: P.arcade ? 'ARCADE' : 'BERKELEY' };
    const t = [...e.table, row].sort((a, b) => b.score - a.score).slice(0, 8);
    store.set('pac.scores', t); S.entering = null;
    splash('GAME OVER', 'red', 'SCORE SAVED. ESC FOR MENU');
  }

  // ---- input ------------------------------------------------------------------------------------------------
  const DIRS = { ArrowUp: 'North', ArrowDown: 'South', ArrowLeft: 'West', ArrowRight: 'East', w: 'North', s: 'South', a: 'West', d: 'East' };
  function steer(dir) { if (kind === 'play' && !S.over) api('/api/key', { dir }).catch(() => {}); }
  function togglePause() {
    if (attract) return;
    if (S.live) api('/api/live/pause', { paused: !S.paused }).catch(() => {});
    else { S.paused = !S.paused; S.paused ? splash('PAUSED', 'white') : el.splash.replaceChildren(); }
  }
  function onKey(e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'select' || tag === 'textarea' || (tag === 'input' && e.target.type !== 'checkbox')) return;
    if (attract) return;
    if (S.entering) {
      if (/^[a-zA-Z]$/.test(e.key) && S.entering.letters.length < 3) S.entering.letters.push(e.key.toUpperCase());
      else if (e.key === 'Backspace') S.entering.letters.pop();
      else if (e.key === 'Enter') { saveInitials(); e.preventDefault(); e.stopPropagation(); return; }
      else return;
      e.preventDefault(); e.stopPropagation(); drawInitials(); return;
    }
    const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
    if (kind === 'play' && DIRS[k]) { e.preventDefault(); steer(DIRS[k]); return; }
    if (k === 'l') { setPanel(gameEl.classList.contains('no-panel')); return; }
    if (k === ' ' || k === 'p') { if (tag !== 'button') { e.preventDefault(); togglePause(); } return; }
    if (kind === 'replay') {
      if (k === 'ArrowRight') { e.preventDefault(); seek(e.shiftKey ? 10 : 1); return; }
      if (k === 'ArrowLeft') { e.preventDefault(); seek(e.shiftKey ? -10 : -1); return; }
      if (k === 'Home') { S.pos = 0; return; }
      if (k === '+' || k === '=') { S.speed = Math.min(S.speed * 2, 8); return; }
      if (k === '-') { S.speed = Math.max(S.speed / 2, 0.25); return; }
    }
    const id = LY.hotkey(k);
    if (id) { setLayers(LY.toggle(layers, id)); }
  }
  document.addEventListener('keydown', onKey, { capture: true, signal: abort.signal });

  // ---- go ------------------------------------------------------------------------------------------------------
  if (S.live) startLive(); else startTrace();

  const api_ = {
    togglePause, seek, setPanel, setLayers, state: S, view,
    destroy() {
      abort.abort();
      clearInterval(S.timer);
      if (S.es) S.es.close();
      view.destroy();
      if (S.live) fetch('/api/live/stop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', keepalive: true }).catch(() => {});
      if (window.__pac === api_) window.__pac = null;
    },
  };
  if (!attract) window.__pac = api_;      // debug handle for tests and screenshots
  return api_;
}
