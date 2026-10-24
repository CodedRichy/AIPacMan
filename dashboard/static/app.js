'use strict';
/* Hunt Table client. No framework, no build step.
   The trace is downloaded once (so scrubbing and the role ribbon work at once);
   playback itself is driven by the server's SSE /stream, which acts as the playhead clock. */
(function () {
  const $ = (id) => document.getElementById(id);
  const SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16];
  const ROLE_GLYPH = { chaser: 'C', interceptor: 'I', blocker: 'B', sweeper: 'S', capsule_guard: 'G', blinky: 'B', pinky: 'P', inky: 'I', clyde: 'C' };
  const LAYERS = [
    ['paths', 'Paths', true], ['targets', 'Targets', true], ['reserved', 'Reserved', true],
    ['predicted', 'Predicted', true], ['food', 'Food', true],
  ];
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const S = {
    name: null, header: null, frames: [], footer: null,
    cur: 0, playing: false, es: null, speedIdx: 2,
    layers: Object.fromEntries(LAYERS.map((l) => [l[0], l[2]])),
    walls: null, anim: null, colors: {}, ribbon: null,
  };

  const cv = $('maze'), ctx = cv.getContext('2d');
  const rb = $('ribbon'), rctx = rb.getContext('2d');

  /* ---------- colour tokens (read from CSS so canvas and DOM agree) ---------- */
  function readColors() {
    const cs = getComputedStyle(document.documentElement);
    const g = (n) => cs.getPropertyValue(n).trim();
    S.colors = {
      pac: g('--pac'), food: g('--food'), scared: g('--scared'), rule: g('--rule'), ink: g('--ink'),
      inkDim: g('--ink-dim'), faint: g('--ink-faint'), bg: g('--bg'), surface: g('--surface-2'),
      none: g('--role-none'),
      role: Object.fromEntries(['chaser', 'interceptor', 'blocker', 'sweeper', 'capsule_guard', 'blinky', 'pinky', 'inky', 'clyde']
        .map((r) => [r, g('--role-' + r)])),
    };
  }
  const roleColor = (r) => S.colors.role[r] || S.colors.none;
  const alpha = (c, a) => c.replace(/\)\s*$/, ' / ' + a + ')');   // oklch(... ) -> oklch(... / a)

  /* ---------- loading ---------- */
  async function refreshList(select) {
    const list = await (await fetch('/api/traces')).json();
    const pick = $('tracePick');
    pick.innerHTML = '';
    if (!list.length) pick.append(new Option('No traces yet: record one', ''));
    for (const t of list) {
      const res = t.win ? 'win' : t.lose ? 'loss' : 'cut';
      pick.append(new Option(`${t.layout} / ${(t.ghostTeam || '').replace('CoordinatedGhostTeam', 'Coord')} / s${t.seed} / ${t.ticks}t / ${t.score} ${res}`, t.name));
    }
    if (select) pick.value = select;
    return list;
  }

  async function loadTrace(name) {
    if (!name) return;
    stop();
    const text = await (await fetch('/api/traces/' + encodeURIComponent(name))).text();
    const recs = text.split('\n').filter(Boolean).map((l) => JSON.parse(l));
    S.name = name;
    S.header = recs[0];
    S.frames = recs.filter((r) => r.type === 'frame');
    S.footer = recs[recs.length - 1].type === 'end' ? recs[recs.length - 1] : null;
    S.walls = S.header.walls.map((row) => Array.from(row, (ch) => ch === '%'));
    S.cur = 0; S.anim = null;
    const sc = $('scrub'); sc.max = Math.max(S.frames.length - 1, 0); sc.value = 0;
    $('board').classList.add('has-data');
    $('board').style.aspectRatio = `${S.header.width} / ${S.header.height}`;
    const h = S.header, f = S.footer;
    $('runMeta').textContent = `${h.layout} · ${h.pacmanAgent} vs ${h.ghostTeam} · seed ${h.seed}` +
      (f ? ` · ${f.win ? 'win' : f.lose ? 'loss' : 'cut at ' + f.ticks}` : '');
    buildRibbon();
    sizeCanvas();
    show(0);
    history.replaceState(null, '', '?trace=' + encodeURIComponent(name));
  }

  /* ---------- transport (SSE is the clock) ---------- */
  function stop() {
    S.playing = false;
    if (S.es) { S.es.close(); S.es = null; }
    $('bPlay').textContent = 'Play'; $('bPlay').setAttribute('aria-label', 'Play');
  }
  function play() {
    if (!S.name || !S.frames.length) return;
    if (S.cur >= S.frames.length - 1) S.cur = -1;      // restart from the top
    if (S.es) S.es.close();
    S.playing = true;
    $('bPlay').textContent = 'Pause'; $('bPlay').setAttribute('aria-label', 'Pause');
    const url = `/stream?trace=${encodeURIComponent(S.name)}&speed=${SPEEDS[S.speedIdx]}&start=${S.cur + 1}`;
    const es = new EventSource(url);
    S.es = es;
    es.addEventListener('frame', (e) => {
      const f = JSON.parse(e.data);
      S.frames[f.tick] = f;
      show(f.tick, true);
    });
    es.addEventListener('end', () => { if (S.es === es) stop(); });
    es.onerror = () => { if (S.es === es) stop(); };
  }
  const toggle = () => (S.playing ? stop() : play());
  function seek(t) {
    const was = S.playing;
    if (was) stop();
    show(Math.min(Math.max(t, 0), S.frames.length - 1));
    if (was) play();
  }

  function setSpeed(i) {
    S.speedIdx = Math.min(Math.max(i, 0), SPEEDS.length - 1);
    $('speed').value = S.speedIdx;
    $('speedLbl').textContent = SPEEDS[S.speedIdx] + 'x';
    if (S.playing) { S.cur = S.cur; play(); }
  }

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
    const rr = rb.getBoundingClientRect();
    rb.width = Math.round(rr.width * dpr); rb.height = Math.round(rr.height * dpr);
    buildRibbon();
    render();
  }
  const cx = (x) => ox + (x + 0.5) * cell;
  const cy = (y) => oy + (S.header.height - 1 - y + 0.5) * cell;

  /* ---------- metrics helpers ---------- */
  function mazeDist(from) {            // BFS distance map from a tile
    const W = S.header.width, H = S.header.height, d = new Int16Array(W * H).fill(-1);
    const q = [[from[0], from[1]]]; d[from[1] * W + from[0]] = 0;
    for (let i = 0; i < q.length; i++) {
      const [x, y] = q[i], base = d[y * W + x];
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const nx = x + dx, ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= W || ny >= H || S.walls[H - 1 - ny][nx] || d[ny * W + nx] >= 0) continue;
        d[ny * W + nx] = base + 1; q.push([nx, ny]);
      }
    }
    return (p) => d[Math.round(p[1]) * W + Math.round(p[0])];
  }
  function spread(gs) {
    if (gs.length < 2) return 0;
    let s = 0, n = 0;
    for (let i = 0; i < gs.length; i++) for (let j = i + 1; j < gs.length; j++) {
      s += Math.abs(gs[i].pos[0] - gs[j].pos[0]) + Math.abs(gs[i].pos[1] - gs[j].pos[1]); n++;
    }
    return s / n;
  }

  /* ---------- show / panels ---------- */
  function show(t, fromStream) {
    const prev = S.frames[t - 1];
    S.cur = t;
    const f = S.frames[t];
    if (!f) return;
    S.anim = (!reduceMotion && fromStream && prev) ? { prev, t0: performance.now(), dur: Math.min(1000 / (8 * SPEEDS[S.speedIdx]), 140) } : null;
    $('scrub').value = t;
    panels(f);
    render();
    if (S.anim) requestAnimationFrame(tickAnim);
  }
  function tickAnim() {
    if (!S.anim) return;
    render();
    if (performance.now() - S.anim.t0 < S.anim.dur) requestAnimationFrame(tickAnim); else { S.anim = null; render(); }
  }

  function panels(f) {
    const total = S.frames.length - 1, h = S.header;
    $('mScore').textContent = f.score;
    $('mTick').innerHTML = `${f.tick}<span class="of"> / ${total}</span>`;
    $('mFood').textContent = f.food.length + ' / ' + h.foodTotal;
    const dist = mazeDist(f.pacman.pos);
    const live = f.ghosts.map((g) => ({ g, d: dist(g.pos) }));
    const hunters = live.filter((x) => x.g.scaredTimer === 0 && x.d >= 0);
    $('mNear').textContent = hunters.length ? (() => { const m = Math.min(...hunters.map((x) => x.d)); return m + (m === 1 ? ' tile' : ' tiles'); })() : (live.length ? 'all scared' : '–');
    $('mSpread').textContent = f.ghosts.length > 1 ? spread(f.ghosts).toFixed(1) : '–';

    const ts = $('tState'); ts.textContent = (f.tacticalState || 'n/a (no coordinator)').replace(/_/g, ' '); ts.dataset.s = f.tacticalState || '';
    $('mStrat').textContent = (f.macroStrategy || 'n/a').replace(/_/g, ' ').toLowerCase();

    const ol = $('roster'); ol.innerHTML = '';
    for (const { g, d } of live) {
      const li = document.createElement('li');
      if (g.scaredTimer > 0) li.classList.add('scared');
      li.style.setProperty('--c', roleColor(g.role));
      const tgt = g.target ? `→ ${g.target[0]},${g.target[1]} · ${g.path.length ? g.path.length - 1 : 0} steps` : 'no target';
      li.innerHTML = `<span class="glyph">${ROLE_GLYPH[g.role] || g.index}</span>` +
        `<span class="rname">${(g.role || 'ghost ' + g.index).replace('_', ' ')}<small>#${g.index}</small></span>` +
        `<span class="rdist">${d >= 0 ? d : '–'}</span>` +
        `<span class="rsub">${tgt}${g.scaredTimer > 0 ? ` · <b>scared ${g.scaredTimer}</b>` : ''}</span>`;
      ol.append(li);
    }
  }

  /* ---------- canvas render ---------- */
  function lerpPos(a, b, k) { return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k]; }
  function render() {
    if (!S.header) return;
    const f = S.frames[S.cur]; if (!f) return;
    const C = S.colors, W = S.header.width, H = S.header.height;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.lineJoin = 'round'; ctx.lineCap = 'round';

    // wall contours: only edges that border open floor
    ctx.beginPath();
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (!S.walls[y][x]) continue;
      const px = ox + x * cell, py = oy + y * cell;
      if (y > 0 && !S.walls[y - 1][x]) { ctx.moveTo(px, py); ctx.lineTo(px + cell, py); }
      if (y < H - 1 && !S.walls[y + 1][x]) { ctx.moveTo(px, py + cell); ctx.lineTo(px + cell, py + cell); }
      if (x > 0 && !S.walls[y][x - 1]) { ctx.moveTo(px, py); ctx.lineTo(px, py + cell); }
      if (x < W - 1 && !S.walls[y][x + 1]) { ctx.moveTo(px + cell, py); ctx.lineTo(px + cell, py + cell); }
    }
    ctx.strokeStyle = C.inkDim; ctx.lineWidth = Math.max(1, cell * 0.07); ctx.stroke();

    const k = S.anim ? Math.min((performance.now() - S.anim.t0) / S.anim.dur, 1) : 1;
    const pv = S.anim ? S.anim.prev : null;

    if (S.layers.food) {
      ctx.fillStyle = C.food;
      for (const [x, y] of f.food) { ctx.beginPath(); ctx.arc(cx(x), cy(y), cell * 0.07, 0, 6.2832); ctx.fill(); }
    }
    for (const [x, y] of f.capsules) {            // capsules: ringed, slow pulse off when reduced motion
      ctx.strokeStyle = C.pac; ctx.lineWidth = Math.max(1, cell * 0.06);
      ctx.beginPath(); ctx.arc(cx(x), cy(y), cell * 0.26, 0, 6.2832); ctx.stroke();
      ctx.fillStyle = C.pac; ctx.beginPath(); ctx.arc(cx(x), cy(y), cell * 0.1, 0, 6.2832); ctx.fill();
    }

    // reserved tiles: hatched squares in the reserving ghost's colour
    if (S.layers.reserved) for (const r of f.reservedTiles || []) {
      const g = f.ghosts.find((q) => q.index === r.ghost);
      const col = roleColor(g && g.role), px = ox + r.tile[0] * cell, py = oy + (H - 1 - r.tile[1]) * cell;
      ctx.save(); ctx.beginPath(); ctx.rect(px + 1, py + 1, cell - 2, cell - 2); ctx.clip();
      ctx.strokeStyle = alpha(col, 0.7); ctx.lineWidth = Math.max(1, cell * 0.05); ctx.beginPath();
      for (let i = -cell; i < cell * 2; i += cell * 0.28) { ctx.moveTo(px + i, py + cell); ctx.lineTo(px + i + cell, py); }
      ctx.stroke(); ctx.restore();
      ctx.strokeStyle = col; ctx.lineWidth = Math.max(1, cell * 0.05); ctx.strokeRect(px + 1, py + 1, cell - 2, cell - 2);
    }

    // planned paths, then straight target lines
    if (S.layers.paths) for (const g of f.ghosts) {
      if (!g.path || g.path.length < 2) continue;
      ctx.strokeStyle = alpha(roleColor(g.role), 0.55); ctx.lineWidth = Math.max(1.5, cell * 0.14);
      ctx.beginPath(); g.path.forEach(([x, y], i) => (i ? ctx.lineTo(cx(x), cy(y)) : ctx.moveTo(cx(x), cy(y)))); ctx.stroke();
    }
    if (S.layers.targets) for (const g of f.ghosts) {
      if (!g.target) continue;
      const col = roleColor(g.role), tx = cx(g.target[0]), ty = cy(g.target[1]), r = cell * 0.3;
      ctx.strokeStyle = col; ctx.lineWidth = Math.max(1, cell * 0.05); ctx.setLineDash([cell * 0.2, cell * 0.2]);
      ctx.beginPath(); ctx.moveTo(cx(g.pos[0]), cy(g.pos[1])); ctx.lineTo(tx, ty); ctx.stroke(); ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(tx - r, ty); ctx.lineTo(tx + r, ty); ctx.moveTo(tx, ty - r); ctx.lineTo(tx, ty + r); ctx.stroke();
      ctx.beginPath(); ctx.arc(tx, ty, r * 0.6, 0, 6.2832); ctx.stroke();
    }

    // predicted pac-man
    if (S.layers.predicted && f.predictedPacman) {
      const [px, py] = [cx(f.predictedPacman[0]), cy(f.predictedPacman[1])];
      ctx.strokeStyle = C.pac; ctx.lineWidth = Math.max(1, cell * 0.06); ctx.setLineDash([cell * 0.12, cell * 0.12]);
      ctx.beginPath(); ctx.arc(px, py, cell * 0.42, 0, 6.2832); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = C.pac; ctx.font = `700 ${Math.max(8, cell * 0.3)}px 'Space Mono', monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('P+', px, py);
    }

    // ghosts
    f.ghosts.forEach((g, i) => {
      const p = pv && pv.ghosts[i] ? lerpPos(pv.ghosts[i].fpos || pv.ghosts[i].pos, g.fpos || g.pos, k) : (g.fpos || g.pos);
      drawGhost(cx(p[0]), cy(p[1]), cell * 0.4, g);
    });
    // pac-man
    const pp = pv ? lerpPos(pv.pacman.fpos || pv.pacman.pos, f.pacman.fpos || f.pacman.pos, k) : (f.pacman.fpos || f.pacman.pos);
    drawPac(cx(pp[0]), cy(pp[1]), cell * 0.42, f.pacman.dir, f.tick);

    // ribbon playhead
    drawRibbonHead();
  }

  function drawPac(x, y, r, dir, tick) {
    const ang = { East: 0, South: Math.PI / 2, West: Math.PI, North: -Math.PI / 2 }[dir] || 0;
    const m = (tick % 2 ? 0.1 : 0.42) * (dir === 'Stop' ? 0.2 : 1);
    ctx.fillStyle = S.colors.pac; ctx.beginPath(); ctx.moveTo(x, y);
    ctx.arc(x, y, r, ang + m, ang + Math.PI * 2 - m); ctx.closePath(); ctx.fill();
  }
  function drawGhost(x, y, r, g) {
    const scared = g.scaredTimer > 0, col = scared ? S.colors.scared : roleColor(g.role);
    ctx.beginPath();
    ctx.arc(x, y - r * 0.1, r, Math.PI, 0);
    ctx.lineTo(x + r, y + r * 0.9);
    for (let i = 0; i < 3; i++) { const sx = x + r - (i + 0.5) * (2 * r / 3); ctx.lineTo(sx, y + r * 0.6); ctx.lineTo(x + r - (i + 1) * (2 * r / 3), y + r * 0.9); }
    ctx.closePath();
    if (scared) {
      ctx.fillStyle = alpha(col, 0.14); ctx.fill();
      ctx.setLineDash([r * 0.3, r * 0.2]); ctx.strokeStyle = col; ctx.lineWidth = Math.max(1.5, r * 0.14); ctx.stroke(); ctx.setLineDash([]);
    } else { ctx.fillStyle = col; ctx.fill(); }
    ctx.fillStyle = scared ? col : S.colors.bg;
    ctx.font = `700 ${Math.max(8, r * 0.95)}px 'Space Mono', monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(scared ? String(g.scaredTimer) : (ROLE_GLYPH[g.role] || String(g.index)), x, y + r * 0.05);
  }

  /* ---------- role ribbon: one strip per ghost + tactical-state strip ---------- */
  const STATE_COL = { COORDINATED_HUNT: 'inkDim', DEFEND_CAPSULE: 'capsule_guard', TRAP_AMBUSH: 'chaser', SCATTER: 'scared' };
  function buildRibbon() {
    if (!S.header || !rb.width) return;
    const off = document.createElement('canvas'); off.width = rb.width; off.height = rb.height;
    const c = off.getContext('2d'), n = S.frames.length, rows = S.header.numGhosts + 1;
    const rh = off.height / rows, colW = off.width / Math.max(n, 1);
    for (let t = 0; t < n; t++) {
      const f = S.frames[t]; if (!f) continue;
      const x = t * colW;
      f.ghosts.forEach((g, i) => {
        c.fillStyle = g.scaredTimer > 0 ? alpha(S.colors.scared, 0.45) : roleColor(g.role);
        c.fillRect(x, i * rh + 1, Math.ceil(colW), rh - 2);
      });
      const key = STATE_COL[f.tacticalState];
      c.fillStyle = key ? (key === 'inkDim' ? alpha(S.colors.inkDim, 0.35) : (S.colors.role[key] || S.colors[key])) : alpha(S.colors.faint, 0.2);
      c.fillRect(x, (rows - 1) * rh + 1, Math.ceil(colW), rh - 2);
    }
    S.ribbon = off;
  }
  function drawRibbonHead() {
    rctx.clearRect(0, 0, rb.width, rb.height);
    if (!S.ribbon) return;
    rctx.drawImage(S.ribbon, 0, 0);
    const x = (S.cur + 0.5) * rb.width / Math.max(S.frames.length, 1);
    rctx.fillStyle = S.colors.ink; rctx.fillRect(x - dpr * 0.75, 0, dpr * 1.5, rb.height);
  }

  /* ---------- wiring ---------- */
  function buildLayers() {
    const box = $('layers');
    LAYERS.forEach(([key, label], i) => {
      const b = document.createElement('button');
      b.type = 'button'; b.setAttribute('aria-pressed', 'true'); b.dataset.key = key;
      b.innerHTML = `<kbd>${i + 1}</kbd>${label}`;
      b.onclick = () => flip(key);
      box.append(b);
    });
  }
  function flip(key) {
    S.layers[key] = !S.layers[key];
    document.querySelector(`#layers [data-key="${key}"]`).setAttribute('aria-pressed', S.layers[key]);
    render();
  }

  $('bPlay').onclick = toggle;
  $('bBack').onclick = () => seek(S.cur - 1);
  $('bFwd').onclick = () => seek(S.cur + 1);
  $('scrub').oninput = (e) => seek(+e.target.value);
  $('speed').oninput = (e) => setSpeed(+e.target.value);
  $('tracePick').onchange = (e) => loadTrace(e.target.value);
  new ResizeObserver(() => sizeCanvas()).observe($('board'));

  document.addEventListener('keydown', (e) => {
    const tag = (e.target.tagName || '').toLowerCase();
    if (tag === 'input' && e.target.type !== 'range' || tag === 'select' || tag === 'textarea') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const big = e.shiftKey ? 10 : 1;
    switch (e.key) {
      case ' ': if (tag === 'button') return; e.preventDefault(); toggle(); break;
      case 'ArrowLeft': if (tag === 'input') return; e.preventDefault(); seek(S.cur - big); break;
      case 'ArrowRight': if (tag === 'input') return; e.preventDefault(); seek(S.cur + big); break;
      case 'Home': e.preventDefault(); seek(0); break;
      case 'End': e.preventDefault(); seek(S.frames.length - 1); break;
      case '[': setSpeed(S.speedIdx - 1); break;
      case ']': setSpeed(S.speedIdx + 1); break;
      case 't': case 'T': e.preventDefault(); $('tracePick').focus(); break;
      default:
        if (/^[1-5]$/.test(e.key)) flip(LAYERS[+e.key - 1][0]);
    }
  });

  $('recForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target));
    const btn = $('recGo'), msg = $('recMsg');
    btn.disabled = true; msg.textContent = 'Recording… (a few seconds)';
    try {
      const r = await fetch('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fd) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.statusText);
      msg.textContent = `Done: ${j.frames} ticks, score ${j.score}`;
      await refreshList(j.name); await loadTrace(j.name);
      $('rec').open = false;
    } catch (err) { msg.textContent = 'Failed: ' + err.message; }
    btn.disabled = false;
  });

  (async function init() {
    readColors(); buildLayers(); setSpeed(2);
    const list = await refreshList();
    const want = new URLSearchParams(location.search).get('trace');
    const first = (want && list.some((t) => t.name === want)) ? want : (list[0] && list[0].name);
    if (first) { $('tracePick').value = first; await loadTrace(first); }
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(render);
    window.__hunt = S;      // handy for debugging and screenshot tooling
  })();
})();
