'use strict';
/* Hunt Table live client. No framework, no build step.
   Frames arrive over SSE at the tick rate; the canvas runs on requestAnimationFrame and
   interpolates every actor between the previous and the current frame (schema v2 `fpos`).
   Keys go back with a tiny POST. The commander is a display element: a ring at the maze
   centre, a dashed line to a ghost when the coordinator issues an order, and a text ticker
   fed only by frame.commander.messages (computed server-side from real coordinator state). */
(function () {
  const $ = (id) => document.getElementById(id);
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const ROLE_GLYPH = { blinky: 'B', pinky: 'P', inky: 'I', clyde: 'C', chaser: 'C', interceptor: 'I', blocker: 'B', sweeper: 'S', capsule_guard: 'G' };
  const ORDER_MS = 300, MAX_TICKER = 14;

  const S = {
    header: null, prev: null, cur: null, t0: 0, dur: 66, walls: null,
    source: 'live', trace: null, tracePos: 0, traceTimer: 0, paused: false, tickRate: 15,
    smooth: !reduceMotion, cmdOn: true, orders: [], floaters: [], banner: '', colors: {}, hatch: null,
    status: null, ended: false,
  };
  try {
    const p = JSON.parse(localStorage.getItem('hunt-live') || '{}');
    if (typeof p.cmdOn === 'boolean') S.cmdOn = p.cmdOn;
    if (typeof p.smooth === 'boolean' && !reduceMotion) S.smooth = p.smooth;
  } catch (e) { /* storage may be blocked */ }
  const savePrefs = () => { try { localStorage.setItem('hunt-live', JSON.stringify({ cmdOn: S.cmdOn, smooth: S.smooth })); } catch (e) { /* ignore */ } };

  const cv = $('maze'), ctx = cv.getContext('2d');

  /* ---------- tokens ---------- */
  function readColors() {
    const cs = getComputedStyle(document.documentElement), g = (n) => cs.getPropertyValue(n).trim();
    S.colors = {
      pac: g('--pac'), food: g('--food'), rule: g('--rule'), ink: g('--ink'), inkDim: g('--ink-dim'), faint: g('--ink-faint'),
      bg: g('--bg'), cold: g('--cold'), coldDim: g('--cold-dim'), order: g('--order'),
      g: { blinky: g('--g-blinky'), pinky: g('--g-pinky'), inky: g('--g-inky'), clyde: g('--g-clyde'),
           chaser: g('--role-chaser'), interceptor: g('--role-interceptor'), blocker: g('--role-blocker'),
           sweeper: g('--role-sweeper'), capsule_guard: g('--role-capsule_guard') },
      none: g('--role-none'),
    };
    const h = document.createElement('canvas'); h.width = h.height = 6;
    const c = h.getContext('2d'); c.strokeStyle = S.colors.cold; c.lineWidth = 1.2;
    c.beginPath(); c.moveTo(-1, 7); c.lineTo(7, -1); c.moveTo(-1, 3); c.lineTo(3, -1); c.moveTo(3, 7); c.lineTo(7, 3); c.stroke();
    S.hatch = ctx.createPattern(h, 'repeat');
  }
  const alpha = (c, a) => c.replace(/\)\s*$/, ' / ' + a + ')');
  const ghostColor = (g) => S.colors.g[g.role] || S.colors.g[['blinky', 'pinky', 'inky', 'clyde'][(g.index - 1) % 4]] || S.colors.none;

  /* ---------- geometry ---------- */
  let cell = 20, ox = 0, oy = 0, dpr = 1;
  function sizeCanvas() {
    if (!S.header) return;
    const r = $('board').getBoundingClientRect();
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    const W = S.header.width, H = S.header.height;
    cell = Math.min(cv.width / (W + 0.6), cv.height / (H + 0.6));
    ox = (cv.width - cell * W) / 2; oy = (cv.height - cell * H) / 2;
  }
  const cx = (x) => ox + (x + 0.5) * cell;
  const cy = (y) => oy + (S.header.height - 1 - y + 0.5) * cell;
  const ringXY = () => [cx((S.header.width - 1) / 2), cy((S.header.height - 1) / 2)];

  /* ---------- stream ---------- */
  let es = null;
  function connect() {
    es = new EventSource('/live/stream');
    es.addEventListener('header', (e) => { if (S.source === 'live') onHeader(JSON.parse(e.data)); });
    es.addEventListener('frame', (e) => { if (S.source === 'live') onFrame(JSON.parse(e.data)); });
    es.addEventListener('status', (e) => { if (S.source === 'live') onStatus(JSON.parse(e.data)); });
    es.addEventListener('end', (e) => { if (S.source === 'live') onEnd(JSON.parse(e.data)); });
    es.onerror = () => { if (!S.header) $('empty').textContent = 'Live stream not available. Start the server with: python3 dashboard/live.py'; };
  }

  function onHeader(h) {
    S.header = h; S.prev = S.cur = null; S.orders = []; S.floaters = []; S.ended = false; setBanner('');
    S.walls = h.walls.map((row) => Array.from(row, (ch) => ch === '%'));
    $('board').classList.add('has-data');
    $('board').style.aspectRatio = `${h.width} / ${h.height}`;
    $('ticker').innerHTML = '';
    $('runMeta').textContent = `${h.layout} · ${h.pacmanAgent} vs ${h.ghostTeam}${h.arcade ? ` · arcade level ${h.level}` : ' · Berkeley rules'} · seed ${h.seed}`;
    $('modeTag').textContent = h.live ? 'live play' : 'replay';
    sizeCanvas();
  }

  function onFrame(f) {
    S.prev = S.cur; S.cur = f;
    S.t0 = performance.now(); S.dur = Math.max((f.dt || 0.066) * 1000, 16);
    if (!S.smooth) S.prev = null;
    panels(f);
    if (f.arcade) for (const ev of f.arcade.events || []) {
      if (ev[0] === 'eaten') {
        const g = f.ghosts.find((q) => q.index === ev[1]);
        if (g) S.floaters.push({ x: g.fpos[0], y: g.fpos[1], text: '+' + ev[2], t0: performance.now() });
      }
    }
    const c = f.commander || { source: 'none', messages: [] };
    $('cmdSrc').textContent = c.source === 'none' ? 'no coordinator' : c.source;
    for (const m of c.messages) addMessage(m, f);
  }

  function onStatus(s) {
    S.status = s; S.paused = !!s.paused;
    if (s.tickRate) { S.tickRate = s.tickRate; $('rate').value = Math.round(s.tickRate); $('rateLbl').textContent = Math.round(s.tickRate) + '/s'; }
    $('bPause').textContent = s.paused ? 'Resume' : 'Pause';
    $('bPause').setAttribute('aria-label', s.paused ? 'Resume' : 'Pause');
    if (!S.ended) setBanner(s.paused ? 'Paused' : (s.state === 'running' && S.cur && S.cur.tick < 2 ? 'Ready' : ''));
  }

  function onEnd(r) {
    S.ended = true;
    if (r.error) return setBanner('Error: ' + r.error);
    setBanner(r.stopped ? 'Stopped' : r.win ? 'Maze cleared' : r.lose ? 'Caught' : 'Over');
  }

  function setBanner(t) {
    const b = $('banner'); S.banner = t; b.textContent = t; b.hidden = !t;
  }

  /* ---------- commander ---------- */
  function addMessage(m, f) {
    const ol = $('ticker');
    const none = ol.querySelector('.none'); if (none) none.remove();
    const li = document.createElement('li');
    li.dataset.kind = m.kind;
    const g = m.ghost ? f.ghosts.find((q) => q.index === m.ghost) : null;
    if (g) li.style.setProperty('--c', ghostColor(g));
    li.innerHTML = `<time>t${m.tick}</time><b class="src"></b><span class="txt"></span>`;
    li.querySelector('.src').textContent = m.src;
    li.querySelector('.txt').textContent = m.text;
    ol.prepend(li);
    while (ol.children.length > MAX_TICKER) ol.lastElementChild.remove();
    if (S.cmdOn) S.orders.push({ ghost: m.ghost, t0: performance.now(), kind: m.kind });
  }

  function setCmd(on) {
    S.cmdOn = on; $('cmdPanel').hidden = !on; $('bCmd').setAttribute('aria-pressed', on); S.orders = []; savePrefs();
  }

  /* ---------- panels ---------- */
  const FMT = (s) => (s == null ? '–' : s.toFixed(1) + ' s');
  function panels(f) {
    const h = S.header;
    $('mScore').textContent = f.score;
    $('mFood').innerHTML = `${f.food.length}<span class="of"> / ${h.foodTotal}</span>`;
    $('mTick').textContent = f.tick;
    const a = f.arcade;
    if (a) {
      const frightened = a.frightLeftSec > 0;
      $('mPhase').textContent = frightened ? 'FRIGHT ' + FMT(a.frightLeftSec) : a.mode.toUpperCase() + ' ' + FMT(a.phaseLeftSec);
      $('mChain').textContent = a.combo ? String(200 * 2 ** Math.min(a.combo - 1, 3)) + ' last' : '–';
    } else {
      $('mPhase').textContent = (f.tacticalState || 'n/a').replace(/_/g, ' ');
      $('mChain').textContent = '–';
    }
    const ol = $('roster'); ol.innerHTML = '';
    for (const g of f.ghosts) {
      const li = document.createElement('li');
      li.dataset.mode = g.mode;
      li.style.setProperty('--c', ghostColor(g));
      const tgt = g.target ? `→ ${g.target[0]},${g.target[1]}` : 'no target';
      li.innerHTML = `<span class="glyph">${ROLE_GLYPH[g.role] || g.index}</span>` +
        `<span class="rname">${(g.role || 'ghost ' + g.index).replace('_', ' ')}<small>#${g.index}</small></span>` +
        `<span class="rmode">${g.mode}</span><span class="rsub">${tgt}</span>`;
      ol.append(li);
    }
  }

  /* ---------- drawing ---------- */
  const lerp = (a, b, k) => a + (b - a) * k;
  function actorPos(prevA, curA, k) {
    if (!prevA) return curA.fpos;
    const dx = curA.fpos[0] - prevA.fpos[0], dy = curA.fpos[1] - prevA.fpos[1];
    if (Math.abs(dx) + Math.abs(dy) > 2.5) return curA.fpos;        // teleport / revive: do not slide across walls
    return [prevA.fpos[0] + dx * k, prevA.fpos[1] + dy * k];
  }

  function drawWalls() {
    const H = S.header.height, W = S.header.width;
    ctx.beginPath();
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (!S.walls[y][x]) continue;
      const px = ox + x * cell, py = oy + y * cell;
      if (y > 0 && !S.walls[y - 1][x]) { ctx.moveTo(px, py); ctx.lineTo(px + cell, py); }
      if (y < H - 1 && !S.walls[y + 1][x]) { ctx.moveTo(px, py + cell); ctx.lineTo(px + cell, py + cell); }
      if (x > 0 && !S.walls[y][x - 1]) { ctx.moveTo(px, py); ctx.lineTo(px, py + cell); }
      if (x < W - 1 && !S.walls[y][x + 1]) { ctx.moveTo(px + cell, py); ctx.lineTo(px + cell, py + cell); }
    }
    ctx.strokeStyle = S.colors.inkDim; ctx.lineWidth = Math.max(1, cell * 0.07); ctx.stroke();
    const hs = S.header.house;                     // the pen door: a short hatched bar
    if (hs) {
      const x0 = ox + hs.doorXs[0] * cell, x1 = ox + (hs.doorXs[hs.doorXs.length - 1] + 1) * cell;
      const y = oy + (S.header.height - 1 - hs.doorY + 0.5) * cell;
      ctx.setLineDash([cell * 0.14, cell * 0.1]); ctx.strokeStyle = S.colors.faint; ctx.lineWidth = Math.max(1, cell * 0.08);
      ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); ctx.setLineDash([]);
    }
  }

  function render(now) {
    if (!S.header) return;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    drawWalls();
    const f = S.cur; if (!f) return;
    const C = S.colors;
    const k = S.prev ? Math.min((now - S.t0) / S.dur, 1) : 1;

    ctx.fillStyle = C.food;
    for (const [x, y] of f.food) { ctx.beginPath(); ctx.arc(cx(x), cy(y), cell * 0.07, 0, 6.2832); ctx.fill(); }
    const pulse = reduceMotion ? 1 : 0.75 + 0.25 * Math.sin(now / 1100 * 6.2832);
    for (const [x, y] of f.capsules) {
      ctx.strokeStyle = alpha(C.pac, pulse); ctx.lineWidth = Math.max(1, cell * 0.06);
      ctx.beginPath(); ctx.arc(cx(x), cy(y), cell * 0.26, 0, 6.2832); ctx.stroke();
      ctx.fillStyle = C.pac; ctx.beginPath(); ctx.arc(cx(x), cy(y), cell * 0.1, 0, 6.2832); ctx.fill();
    }

    const flash = f.arcade && f.arcade.frightLeftSec > 0 && f.arcade.frightLeftSec < 2 && !reduceMotion && Math.floor(now / 220) % 2 === 0;
    const gp = f.ghosts.map((g, i) => actorPos(S.prev && S.prev.ghosts[i], g, k));
    f.ghosts.forEach((g, i) => drawGhost(cx(gp[i][0]), cy(gp[i][1]), cell * 0.4, g, flash));
    const pp = actorPos(S.prev && S.prev.pacman, f.pacman, k);
    drawPac(cx(pp[0]), cy(pp[1]), cell * 0.42, f.pacman.dir, pp);

    if (S.cmdOn) drawCommander(now, gp, f);
    drawFloaters(now);
  }

  function drawPac(x, y, r, dir, pos) {
    const ang = { East: 0, South: Math.PI / 2, West: Math.PI, North: -Math.PI / 2 }[dir] || 0;
    const phase = (pos[0] + pos[1]) * 2;                              // mouth follows distance travelled, not wall-clock
    const m = (dir === 'Stop' ? 0.12 : 0.06 + 0.4 * Math.abs(Math.sin(phase * Math.PI / 2)));
    ctx.fillStyle = S.colors.pac; ctx.beginPath(); ctx.moveTo(x, y);
    ctx.arc(x, y, r, ang + m, ang + Math.PI * 2 - m); ctx.closePath(); ctx.fill();
  }

  function bodyPath(x, y, r) {
    ctx.beginPath();
    ctx.arc(x, y - r * 0.1, r, Math.PI, 0);
    ctx.lineTo(x + r, y + r * 0.9);
    for (let i = 0; i < 3; i++) { ctx.lineTo(x + r - (i + 0.5) * (2 * r / 3), y + r * 0.6); ctx.lineTo(x + r - (i + 1) * (2 * r / 3), y + r * 0.9); }
    ctx.closePath();
  }
  function drawEyes(x, y, r, dir, onBody) {
    const off = { East: [0.18, 0], West: [-0.18, 0], North: [0, -0.18], South: [0, 0.18] }[dir] || [0, 0];
    for (const s of [-1, 1]) {
      const ex = x + s * r * 0.36, ey = y - r * 0.15;
      ctx.fillStyle = S.colors.ink; ctx.beginPath(); ctx.ellipse(ex, ey, r * 0.24, r * 0.3, 0, 0, 6.2832); ctx.fill();
      ctx.fillStyle = onBody ? S.colors.bg : S.colors.coldDim;
      ctx.beginPath(); ctx.arc(ex + off[0] * r, ey + off[1] * r, r * 0.12, 0, 6.2832); ctx.fill();
    }
  }
  function drawGhost(x, y, r, g, flash) {
    if (g.mode === 'eyes') { drawEyes(x, y, r, g.dir, false); return; }          // eaten: eyes only
    const col = ghostColor(g);
    bodyPath(x, y, r);
    if (g.mode === 'frightened') {
      ctx.fillStyle = flash ? alpha(S.colors.ink, 0.5) : S.hatch; ctx.fill();    // desaturated cold hatch
      ctx.setLineDash([r * 0.3, r * 0.2]); ctx.strokeStyle = S.colors.cold; ctx.lineWidth = Math.max(1.2, r * 0.12); ctx.stroke(); ctx.setLineDash([]);
      for (const s of [-1, 1]) { ctx.fillStyle = S.colors.cold; ctx.fillRect(x + s * r * 0.36 - r * 0.07, y - r * 0.28, r * 0.14, r * 0.14); }
      return;
    }
    ctx.globalAlpha = (g.mode === 'house' || g.mode === 'exit') ? 0.7 : 1;
    ctx.fillStyle = col; ctx.fill();
    ctx.globalAlpha = 1;
    drawEyes(x, y, r, g.dir, true);
  }

  function drawCommander(now, gp, f) {
    const [rx, ry] = ringXY(), R = cell * 1.15;
    S.orders = S.orders.filter((o) => now - o.t0 < ORDER_MS);
    const hot = S.orders.length > 0;
    ctx.strokeStyle = hot ? S.colors.order : alpha(S.colors.inkDim, 0.7); ctx.lineWidth = Math.max(1.2, cell * 0.06);
    ctx.beginPath(); ctx.arc(rx, ry, R, 0, 6.2832); ctx.stroke();                 // hollow ring: never filled
    ctx.lineWidth = Math.max(1, cell * 0.045); ctx.beginPath();
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) { ctx.moveTo(rx + dx * R, ry + dy * R); ctx.lineTo(rx + dx * R * 1.28, ry + dy * R * 1.28); }
    ctx.stroke();
    for (const o of S.orders) {
      const age = now - o.t0;
      const p = reduceMotion ? 1 : Math.min(age / 110, 1);
      const a = age < 180 ? 1 : Math.max(0, 1 - (age - 180) / (ORDER_MS - 180));
      const targets = o.ghost ? [o.ghost] : f.ghosts.map((g) => g.index);
      for (const gi of targets) {
        const i = f.ghosts.findIndex((q) => q.index === gi); if (i < 0) continue;
        const gx = cx(gp[i][0]), gy = cy(gp[i][1]), ang = Math.atan2(gy - ry, gx - rx);
        const sx = rx + Math.cos(ang) * R, sy = ry + Math.sin(ang) * R;
        ctx.setLineDash([cell * 0.24, cell * 0.18]); ctx.strokeStyle = alpha(S.colors.order, a); ctx.lineWidth = Math.max(1.2, cell * 0.07);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(lerp(sx, gx, p), lerp(sy, gy, p)); ctx.stroke(); ctx.setLineDash([]);
      }
    }
  }

  function drawFloaters(now) {
    S.floaters = S.floaters.filter((q) => now - q.t0 < 1200);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const q of S.floaters) {
      const age = (now - q.t0) / 1200, rise = reduceMotion ? 0 : age * cell * 0.9;
      ctx.fillStyle = alpha(S.colors.cold, 1 - age * age);
      ctx.font = `700 ${Math.max(10, cell * 0.55)}px 'Space Mono', monospace`;
      ctx.fillText(q.text, cx(q.x), cy(q.y) - rise);
    }
  }

  let raf = 0;
  function loop(now) { render(now); raf = requestAnimationFrame(loop); }

  /* ---------- controls ---------- */
  const post = (url, body) => fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}), keepalive: true });
  const DIRS = { ArrowUp: 'North', ArrowDown: 'South', ArrowLeft: 'West', ArrowRight: 'East', w: 'North', s: 'South', a: 'West', d: 'East', W: 'North', S: 'South', A: 'West', D: 'East' };
  function steer(dir) { if (S.source === 'live') post('/api/key', { dir }).catch(() => {}); }

  function togglePause() {
    if (S.source === 'trace') { S.paused = !S.paused; $('bPause').textContent = S.paused ? 'Resume' : 'Pause'; return; }
    post('/api/live/pause', { paused: !S.paused }).catch(() => {});
  }

  document.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'select' || tag === 'textarea' || (tag === 'input' && e.target.type !== 'range')) return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (DIRS[e.key]) { e.preventDefault(); steer(DIRS[e.key]); return; }
    if (e.key === ' ' && tag !== 'button') { e.preventDefault(); togglePause(); }
    else if (e.key === 'c' || e.key === 'C') setCmd(!S.cmdOn);
  });
  document.querySelectorAll('.dpad [data-dir]').forEach((b) => b.addEventListener('click', () => steer(b.dataset.dir)));
  $('bPause').onclick = togglePause;
  $('bCmd').onclick = () => setCmd(!S.cmdOn);
  $('bSmooth').onclick = () => { S.smooth = !S.smooth; $('bSmooth').setAttribute('aria-pressed', S.smooth); savePrefs(); };
  let rateTimer = 0;
  $('rate').oninput = (e) => {
    const r = +e.target.value; $('rateLbl').textContent = r + '/s'; S.tickRate = r;
    clearTimeout(rateTimer);
    rateTimer = setTimeout(() => { if (S.source === 'live') post('/api/live/rate', { tickRate: r }).catch(() => {}); }, 120);
  };

  $('fArcade').onchange = (e) => {
    const g = $('fGhosts');
    if (e.target.value === 'true') g.value = 'ArcadeGhostTeam';
    else if (g.value === 'ArcadeGhostTeam') g.value = 'DirectionalGhost';
  };
  $('newForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target)), msg = $('newMsg'), btn = $('newGo');
    fd.arcade = fd.arcade === 'true'; fd.level = +fd.level; fd.seed = +fd.seed; fd.tickRate = S.tickRate;
    btn.disabled = true; msg.textContent = 'Starting…';
    try {
      setSource('live');
      const r = await fetch('/api/live/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fd) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.statusText);
      msg.textContent = ''; $('rec').open = false; $('board').focus();
    } catch (err) { msg.textContent = 'Failed: ' + err.message; }
    btn.disabled = false;
  });

  /* ---------- v2 trace replay (same renderer, client-side clock) ---------- */
  function setSource(src) {
    S.source = src;
    if (src === 'live') { clearInterval(S.traceTimer); S.trace = null; $('tracePick').value = ''; }
  }
  async function loadTrace(name) {
    if (!name) { setSource('live'); return; }
    setSource('trace');
    const text = await (await fetch('/api/traces/' + encodeURIComponent(name))).text();
    const recs = text.split('\n').filter(Boolean).map((l) => JSON.parse(l));
    const header = recs[0], frames = recs.filter((r) => r.type === 'frame');
    if (header.schema < 2) { $('newMsg').textContent = 'That trace is schema v1: use Replay v1.'; setSource('live'); return; }
    onHeader(header); S.trace = frames; S.tracePos = 0; S.paused = false;
    const q = new URLSearchParams(location.search), at = Math.max(0, +(q.get('t') || 0));   // ?t=120&pause=1 opens at a tick
    if (at > 1) { for (let i = Math.max(0, at - 24); i < at; i++) onFrame(frames[i]); S.tracePos = at; }
    if (q.get('pause') === '1') S.paused = true;
    $('bPause').textContent = S.paused ? 'Resume' : 'Pause';
    clearInterval(S.traceTimer);
    let acc = performance.now();
    S.traceTimer = setInterval(() => {
      const now = performance.now();
      if (S.paused) { acc = now; S.t0 = now; return; }
      const step = 1000 / S.tickRate;
      while (acc <= now && S.tracePos < frames.length) { onFrame(frames[S.tracePos++]); acc += step; }
      if (S.tracePos >= frames.length) { clearInterval(S.traceTimer); setBanner('End of trace'); }
    }, 16);
    S.tickRate = header.tickRate || 15; $('rate').value = Math.round(S.tickRate); $('rateLbl').textContent = Math.round(S.tickRate) + '/s';
  }
  $('tracePick').onchange = (e) => loadTrace(e.target.value);
  async function listTraces() {
    try {
      const list = await (await fetch('/api/traces')).json();
      for (const t of list) if (/_v2\.jsonl$/.test(t.name)) $('tracePick').append(new Option(`${t.layout} / ${t.ghostTeam} / s${t.seed} / ${t.ticks}t / ${t.score}`, t.name));
    } catch (e) { /* server without trace listing */ }
  }

  /* ---------- init ---------- */
  new ResizeObserver(sizeCanvas).observe($('board'));
  readColors();
  $('cmdPanel').hidden = !S.cmdOn; $('bCmd').setAttribute('aria-pressed', S.cmdOn);
  $('bSmooth').setAttribute('aria-pressed', S.smooth);
  $('ticker').innerHTML = '<li class="none">Waiting for the coordinator…</li>';
  connect(); listTraces();
  const want = new URLSearchParams(location.search).get('trace');
  if (want) loadTrace(want);
  raf = requestAnimationFrame(loop);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(readColors);
  window.__live = S;
})();
