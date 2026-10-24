// The arcade renderer: one canvas, one requestAnimationFrame loop while started.
// Classic look first (double-line blue walls, yellow Pac-Man, red/pink/cyan/orange ghosts, blue frightened
// ghosts, eyes-only eaten ghosts, score popups); the "intel" layers (layers.js) are drawn on top in the
// surveyor style.  Everything that grows per frame is capped (orders, floaters, chatter, seen-message keys,
// trail map <= number of tiles).
import { readMessages, readBeliefs, msgKey, payloadText, roleName } from './layers.js';

const TAU = Math.PI * 2;
const MAX_ORDERS = 24, MAX_FLOATERS = 16, MAX_CHATTER = 24, MAX_SEEN = 400;
const ORDER_MS = 320, CHATTER_MS = 1400;
const ROLE_LETTER = { chaser: 'C', interceptor: 'I', blocker: 'B', sweeper: 'S', capsule_guard: 'G', scared: 'F',
  blinky: 'B', pinky: 'P', inky: 'I', clyde: 'C' };
const alpha = (c, a) => c.replace(/\)\s*$/, ' / ' + a + ')');

export class ArcadeView {
  constructor(canvas, opts = {}) {
    this.cv = canvas;
    this.ctx = canvas.getContext('2d');
    this.on = opts.layers || {};
    this.reduce = !!opts.reduceMotion;
    this.smooth = opts.smooth !== false && !this.reduce;
    this.header = null; this.prev = null; this.cur = null; this.t0 = 0; this.dur = 66;
    this.phase = 'playing'; this.phaseT0 = 0;
    this.floaters = []; this.orders = []; this.chatter = []; this.seen = new Set();
    this.trail = new Map(); this.scaredMax = new Map();
    this.cell = 16; this.ox = 0; this.oy = 0; this.wallPath = null;
    this.raf = 0; this.running = false;
    this.readColors();
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(canvas.parentElement || canvas);
  }

  readColors() {
    const cs = getComputedStyle(document.documentElement), g = (n) => cs.getPropertyValue(n).trim();
    this.C = {
      void: g('--void'), wall: g('--wall'), door: g('--door'), pac: g('--pac'), dot: g('--dot'), ink: g('--ink'),
      fright: g('--fright'), frightFlash: g('--fright-flash'), face: g('--fright-face'), order: g('--order'),
      chat: g('--chat'), cold: g('--cold'), faint: g('--ink-faint'), dim: g('--ink-dim'), pupil: g('--pupil'),
      ghost: [g('--g-blinky'), g('--g-pinky'), g('--g-inky'), g('--g-clyde')],
      role: { chaser: g('--role-chaser'), interceptor: g('--role-interceptor'), blocker: g('--role-blocker'),
        sweeper: g('--role-sweeper'), capsule_guard: g('--role-capsule_guard'), scared: g('--cold') },
      pixel: g('--font-pixel') || 'monospace', data: g('--font-data') || 'monospace',
    };
  }

  setLayers(on) { this.on = on; }

  setHeader(h) {
    this.header = h; this.prev = this.cur = null; this.orders = []; this.floaters = []; this.chatter = [];
    this.seen.clear(); this.scaredMax.clear();
    this.walls = h.walls.map((row) => Array.from(row, (ch) => ch === '%'));
    this.resize();
  }

  /** New game on the same maze keeps the heatmap; a new maze (different size) resets it. */
  resetTrail() { this.trail.clear(); }

  setPhase(p) {
    if (p === this.phase) return;
    this.phase = p; this.phaseT0 = performance.now();
  }

  resize() {
    const cv = this.cv, box = cv.parentElement || cv;
    const r = box.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.max(2, Math.round(r.width * dpr)); cv.height = Math.max(2, Math.round(r.height * dpr));
    if (!this.header) return;
    const W = this.header.width, H = this.header.height;
    this.cell = Math.min(cv.width / W, cv.height / H);
    this.ox = (cv.width - this.cell * W) / 2; this.oy = (cv.height - this.cell * H) / 2;
    this.buildWalls();
    if (!this.running) this.render(performance.now());
  }

  buildWalls() {
    const { width: W, height: H } = this.header, c = this.cell, p = new Path2D();
    const wl = this.walls;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (!wl[y][x]) continue;
      const px = this.ox + x * c, py = this.oy + y * c;
      if (y > 0 && !wl[y - 1][x]) { p.moveTo(px, py); p.lineTo(px + c, py); }
      if (y < H - 1 && !wl[y + 1][x]) { p.moveTo(px, py + c); p.lineTo(px + c, py + c); }
      if (x > 0 && !wl[y][x - 1]) { p.moveTo(px, py); p.lineTo(px, py + c); }
      if (x < W - 1 && !wl[y][x + 1]) { p.moveTo(px + c, py); p.lineTo(px + c, py + c); }
    }
    this.wallPath = p;
  }

  // ---- geometry ----------------------------------------------------------------------------------------
  X(x) { return this.ox + (x + 0.5) * this.cell; }
  Y(y) { return this.oy + (this.header.height - 1 - y + 0.5) * this.cell; }

  // ---- data in -------------------------------------------------------------------------------------------
  push(f) {
    const now = performance.now();
    this.prev = this.smooth ? this.cur : null; this.cur = f;
    this.t0 = now; this.dur = Math.max((f.dt || 0.066) * 1000, 16);
    if (this.header) {
      const key = f.pacman.pos[0] + ',' + f.pacman.pos[1];
      if (this.trail.size < this.header.width * this.header.height) this.trail.set(key, (this.trail.get(key) || 0) + 1);
      else if (this.trail.has(key)) this.trail.set(key, this.trail.get(key) + 1);
    }
    for (const g of f.ghosts) {
      const t = g.mode === 'frightened' ? (f.arcade ? f.arcade.frightLeftSec : g.scaredTimer) : 0;
      if (t > (this.scaredMax.get(g.index) || 0)) this.scaredMax.set(g.index, t);
      if (!t) this.scaredMax.delete(g.index);
    }
    // score popups: arcade events, or (Berkeley) a frightened ghost that jumped home
    if (f.arcade) {
      for (const ev of f.arcade.events || []) if (ev[0] === 'eaten') {
        const g = f.ghosts.find((q) => q.index === ev[1]);
        if (g) this.pop(g.fpos[0], g.fpos[1], String(ev[2]), this.C.cold);
      }
    } else if (this.prev) {
      f.ghosts.forEach((g, i) => {
        const p = this.prev.ghosts[i];
        if (p && p.mode === 'frightened' && g.mode !== 'frightened' && Math.abs(p.fpos[0] - g.fpos[0]) + Math.abs(p.fpos[1] - g.fpos[1]) > 2.5) {
          this.pop(p.fpos[0], p.fpos[1], '200', this.C.cold);
        }
      });
    }
    const h = f.hud;
    if (h) for (const ev of h.events || []) {
      if (ev[0] === 'fruit') this.pop(f.pacman.fpos[0], f.pacman.fpos[1], String(ev[2]), this.C.order);
      if (ev[0] === 'extra') this.pop(f.pacman.fpos[0], f.pacman.fpos[1] - 1, '1UP', this.C.pac);
    }
    const c = f.commander;
    if (c && this.on.commander) for (const m of c.messages || []) {
      this.orders.push({ ghost: m.ghost, t0: now });
      if (this.orders.length > MAX_ORDERS) this.orders.shift();
    }
    this.newMsgs = [];
    for (const m of readMessages(f)) {
      const k = msgKey(m);
      if (this.seen.has(k)) continue;
      this.seen.add(k);
      this.newMsgs.push(m);
      this.chatter.push({ m, t0: now });
      if (this.chatter.length > MAX_CHATTER) this.chatter.shift();
    }
    if (this.seen.size > MAX_SEEN) this.seen.clear();
  }

  pop(x, y, text, color) {
    this.floaters.push({ x, y, text, color, t0: performance.now() });
    if (this.floaters.length > MAX_FLOATERS) this.floaters.shift();
  }

  // ---- loop ----------------------------------------------------------------------------------------------
  start() {
    if (this.running) return;
    this.running = true;
    const loop = (now) => { if (!this.running) return; this.render(now); this.raf = requestAnimationFrame(loop); };
    this.raf = requestAnimationFrame(loop);
  }
  stop() { this.running = false; cancelAnimationFrame(this.raf); }
  destroy() { this.stop(); this.ro.disconnect(); }

  // ---- drawing -------------------------------------------------------------------------------------------
  actorPos(p, c, k) {
    if (!p) return c.fpos;
    const dx = c.fpos[0] - p.fpos[0], dy = c.fpos[1] - p.fpos[1];
    if (Math.abs(dx) + Math.abs(dy) > 2.5) return c.fpos;
    return [p.fpos[0] + dx * k, p.fpos[1] + dy * k];
  }

  render(now) {
    const ctx = this.ctx, cv = this.cv;
    ctx.fillStyle = this.C.void; ctx.fillRect(0, 0, cv.width, cv.height);
    if (!this.header || !this.wallPath) return;
    const f = this.cur, C = this.C, c = this.cell, L = this.on;
    const clearT = this.phase === 'cleared' ? now - this.phaseT0 : -1;
    this.drawWalls(clearT);
    if (!f) return;
    ctx.lineJoin = ctx.lineCap = 'round';
    const k = this.prev ? Math.min((now - this.t0) / this.dur, 1) : 1;
    const dying = this.phase === 'dying', hideGhosts = (dying && now - this.phaseT0 > 250) || this.phase === 'cleared';

    if (L.trail) this.drawTrail();
    // food
    ctx.fillStyle = C.dot;
    const d = c * 0.15;
    for (const [x, y] of f.food) ctx.fillRect(this.X(x) - d / 2, this.Y(y) - d / 2, d, d);
    const blink = this.reduce || Math.floor(now / 260) % 2 === 0;
    if (blink) for (const [x, y] of f.capsules) { ctx.beginPath(); ctx.arc(this.X(x), this.Y(y), c * 0.3, 0, TAU); ctx.fill(); }
    if (f.hud && f.hud.fruit) this.drawFruit(f.hud.fruit.kind, this.X(f.hud.fruit.pos[0]), this.Y(f.hud.fruit.pos[1]), c * 0.42);

    const gp = f.ghosts.map((g, i) => this.actorPos(this.prev && this.prev.ghosts[i], g, k));
    if (L.reserved) this.drawReserved(f);
    if (L.paths) this.drawPaths(f);
    if (L.pincer) this.drawPincer(f);
    if (L.predicted) this.drawPredicted(f, now);
    if (L.targets) this.drawTargets(f);

    const flashing = this.isFlashing(f, now);
    if (!hideGhosts) f.ghosts.forEach((g, i) => this.drawGhost(this.X(gp[i][0]), this.Y(gp[i][1]), c * 0.46, g, flashing, now));
    const pp = this.actorPos(this.prev && this.prev.pacman, f.pacman, k);
    if (dying) this.drawDeath(this.X(pp[0]), this.Y(pp[1]), c * 0.46, now - this.phaseT0);
    else if (this.phase !== 'cleared') this.drawPac(this.X(pp[0]), this.Y(pp[1]), c * 0.46, f.pacman.dir, pp);

    if (!hideGhosts) {
      if (L.roles) f.ghosts.forEach((g, i) => this.drawBadge(this.X(gp[i][0]), this.Y(gp[i][1]), g));
      if (L.scared) f.ghosts.forEach((g, i) => this.drawScared(this.X(gp[i][0]), this.Y(gp[i][1]), g, f));
      if (L.commander) this.drawCommander(now, gp, f);
      if (L.chatter) this.drawChatter(now, gp, f);
    }
    this.drawFloaters(now);
  }

  drawWalls(clearT) {
    const ctx = this.ctx, C = this.C, c = this.cell;
    let col = C.wall;
    if (clearT >= 0 && !this.reduce && Math.floor(clearT / 240) % 2 === 1) col = C.ink;
    ctx.lineJoin = ctx.lineCap = 'round';
    ctx.strokeStyle = col; ctx.lineWidth = c * 0.34; ctx.stroke(this.wallPath);
    ctx.strokeStyle = C.void; ctx.lineWidth = c * 0.15; ctx.stroke(this.wallPath);
    const hs = this.header.house;
    if (hs) {
      const x0 = this.ox + hs.doorXs[0] * c, x1 = this.ox + (hs.doorXs[hs.doorXs.length - 1] + 1) * c;
      const y = this.oy + (this.header.height - 1 - hs.doorY + 0.5) * c;
      ctx.strokeStyle = C.door; ctx.lineWidth = c * 0.16; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
    }
  }

  drawTrail() {
    const ctx = this.ctx, c = this.cell;
    let max = 1;
    for (const v of this.trail.values()) if (v > max) max = v;
    for (const [key, v] of this.trail) {
      const [x, y] = key.split(',').map(Number);
      ctx.fillStyle = alpha('oklch(0.8 0.17 60)', Math.min(0.55, 0.12 + 0.43 * v / max));
      ctx.fillRect(this.ox + x * c + 1, this.oy + (this.header.height - 1 - y) * c + 1, c - 2, c - 2);
    }
  }

  ghostColor(g) { return this.C.ghost[(g.index - 1) % 4]; }
  roleColor(g) { return this.C.role[g.role] || this.C.dim; }

  isFlashing(f, now) {
    if (this.reduce) return false;
    const a = f.arcade;
    const left = a ? a.frightLeftSec : Math.max(0, ...f.ghosts.map((g) => g.scaredTimer / 15));
    return left > 0 && left < 2 && Math.floor(now / 200) % 2 === 0;
  }

  drawPac(x, y, r, dir, pos) {
    const ctx = this.ctx;
    const ang = { East: 0, South: Math.PI / 2, West: Math.PI, North: -Math.PI / 2 }[dir] || 0;
    const m = dir === 'Stop' ? 0.1 : 0.04 + 0.42 * Math.abs(Math.sin((pos[0] + pos[1]) * Math.PI));
    ctx.fillStyle = this.C.pac; ctx.beginPath(); ctx.moveTo(x, y);
    ctx.arc(x, y, r, ang + m, ang + TAU - m); ctx.closePath(); ctx.fill();
  }

  drawDeath(x, y, r, t) {
    const ctx = this.ctx, p = Math.min(t / 1400, 1);
    if (p >= 1) return;
    const m = Math.PI * p;               // mouth opens until the disc is gone
    ctx.fillStyle = this.C.pac; ctx.beginPath(); ctx.moveTo(x, y);
    ctx.arc(x, y, r, -Math.PI / 2 + m, -Math.PI / 2 + TAU - m); ctx.closePath(); ctx.fill();
  }

  bodyPath(x, y, r, wob) {
    const ctx = this.ctx;
    ctx.beginPath();
    ctx.arc(x, y - r * 0.1, r, Math.PI, 0);
    ctx.lineTo(x + r, y + r * 0.95);
    const n = 3, w = 2 * r / n;
    for (let i = 0; i < n; i++) {
      ctx.lineTo(x + r - (i + 0.5) * w, y + r * (wob ? 0.62 : 0.72));
      ctx.lineTo(x + r - (i + 1) * w, y + r * 0.95);
    }
    ctx.closePath();
  }

  drawEyes(x, y, r, dir) {
    const ctx = this.ctx, off = { East: [0.16, 0], West: [-0.16, 0], North: [0, -0.18], South: [0, 0.18] }[dir] || [0, 0];
    for (const s of [-1, 1]) {
      const ex = x + s * r * 0.38, ey = y - r * 0.2;
      ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.ellipse(ex, ey, r * 0.24, r * 0.3, 0, 0, TAU); ctx.fill();
      ctx.fillStyle = this.C.pupil; ctx.beginPath(); ctx.arc(ex + off[0] * r, ey + off[1] * r, r * 0.13, 0, TAU); ctx.fill();
    }
  }

  drawGhost(x, y, r, g, flashing, now) {
    const ctx = this.ctx, C = this.C, wob = !this.reduce && Math.floor(now / 140) % 2 === 0;
    if (g.mode === 'eyes') { this.drawEyes(x, y, r, g.dir); return; }
    this.bodyPath(x, y, r, wob);
    if (g.mode === 'frightened') {
      ctx.fillStyle = flashing ? C.frightFlash : C.fright; ctx.fill();
      ctx.fillStyle = flashing ? C.fright : C.face;
      for (const s of [-1, 1]) ctx.fillRect(x + s * r * 0.36 - r * 0.1, y - r * 0.32, r * 0.2, r * 0.2);
      ctx.strokeStyle = ctx.fillStyle; ctx.lineWidth = Math.max(1, r * 0.1); ctx.beginPath();
      for (let i = 0; i <= 6; i++) { const px = x - r * 0.6 + i * r * 0.2; const py = y + r * (i % 2 ? 0.28 : 0.42); i ? ctx.lineTo(px, py) : ctx.moveTo(px, py); }
      ctx.stroke();
      return;
    }
    ctx.globalAlpha = (g.mode === 'house' || g.mode === 'exit') ? 0.75 : 1;
    ctx.fillStyle = this.ghostColor(g); ctx.fill();
    ctx.globalAlpha = 1;
    this.drawEyes(x, y, r, g.dir);
  }

  drawFruit(kind, x, y, r) {
    const ctx = this.ctx;
    const disc = (cx, cy, rr, col) => { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(cx, cy, rr, 0, TAU); ctx.fill(); };
    const stem = (x0, y0, x1, y1) => { ctx.strokeStyle = 'oklch(0.7 0.17 145)'; ctx.lineWidth = Math.max(1, r * 0.14); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); };
    switch (kind) {
      case 'cherry': stem(x - r * .45, y + r * .2, x + r * .1, y - r * .8); stem(x + r * .45, y + r * .3, x + r * .1, y - r * .8);
        disc(x - r * .45, y + r * .4, r * .4, 'oklch(0.6 0.24 25)'); disc(x + r * .45, y + r * .45, r * .4, 'oklch(0.6 0.24 25)'); break;
      case 'strawberry': disc(x, y + r * .1, r * .75, 'oklch(0.62 0.23 20)'); stem(x, y - r * .8, x, y - r * .5); break;
      case 'orange': disc(x, y + r * .1, r * .75, 'oklch(0.76 0.17 60)'); stem(x, y - r * .8, x + r * .2, y - r * .55); break;
      case 'apple': disc(x, y + r * .1, r * .75, 'oklch(0.58 0.24 28)'); stem(x, y - r * .8, x + r * .25, y - r * .5); break;
      case 'melon': disc(x, y + r * .1, r * .75, 'oklch(0.78 0.18 140)'); stem(x, y - r * .8, x, y - r * .5); break;
      case 'galaxian': ctx.fillStyle = 'oklch(0.85 0.12 200)'; ctx.beginPath(); ctx.moveTo(x - r * .8, y - r * .5); ctx.lineTo(x + r * .8, y - r * .5);
        ctx.lineTo(x, y + r * .8); ctx.closePath(); ctx.fill(); break;
      case 'bell': disc(x, y, r * .7, 'oklch(0.88 0.16 95)'); break;
      default: ctx.fillStyle = 'oklch(0.85 0.1 200)'; ctx.fillRect(x - r * .2, y - r * .8, r * .4, r * 1.5); ctx.fillRect(x - r * .6, y - r * .8, r * 1.2, r * .4);
    }
  }

  // ---- intel layers ----------------------------------------------------------------------------------------
  drawPaths(f) {
    const ctx = this.ctx, c = this.cell;
    ctx.lineWidth = Math.max(2, c * 0.14); ctx.setLineDash([0, c * 0.32]);
    for (const g of f.ghosts) {
      if (!g.path || g.path.length < 2 || g.mode === 'eyes') continue;
      ctx.strokeStyle = alpha(this.ghostColor(g), 0.7); ctx.beginPath();
      g.path.forEach(([x, y], i) => (i ? ctx.lineTo(this.X(x), this.Y(y)) : ctx.moveTo(this.X(x), this.Y(y))));
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  drawTargets(f) {
    const ctx = this.ctx, c = this.cell;
    ctx.lineWidth = Math.max(1.5, c * 0.09);
    for (const g of f.ghosts) {
      if (!g.target) continue;
      const x = this.X(g.target[0]), y = this.Y(g.target[1]), r = c * 0.36;
      ctx.strokeStyle = this.ghostColor(g);
      ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.moveTo(x - r * 1.5, y); ctx.lineTo(x - r * 0.5, y); ctx.moveTo(x + r * 0.5, y); ctx.lineTo(x + r * 1.5, y);
      ctx.moveTo(x, y - r * 1.5); ctx.lineTo(x, y - r * 0.5); ctx.moveTo(x, y + r * 0.5); ctx.lineTo(x, y + r * 1.5); ctx.stroke();
    }
  }

  drawPredicted(f, now) {
    const t = f.predictedPacman; if (!t) return;
    const ctx = this.ctx, x = this.X(t[0]), y = this.Y(t[1]), r = this.cell * 0.44;
    ctx.setLineDash([this.cell * 0.14, this.cell * 0.12]); ctx.strokeStyle = this.C.pac; ctx.lineWidth = Math.max(1.5, this.cell * 0.09);
    ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, r, 0.45, TAU - 0.45); ctx.closePath(); ctx.stroke(); ctx.setLineDash([]);
  }

  drawPincer(f) {
    if (!/Enhanced/.test(this.header.ghostTeam || '') || !f.predictedPacman) return;
    const ctx = this.ctx, c = this.cell, t = f.predictedPacman, x = this.X(t[0]), y = this.Y(t[1]);
    const px = this.X(f.pacman.fpos[0]), py = this.Y(f.pacman.fpos[1]);
    ctx.strokeStyle = this.C.order; ctx.lineWidth = Math.max(1.5, c * 0.1);
    ctx.setLineDash([c * 0.1, c * 0.14]); ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, y); ctx.stroke(); ctx.setLineDash([]);
    const w = c * 0.5, a = c * 0.2;                      // brackets: ] [ around the pincer tile
    ctx.beginPath(); ctx.moveTo(x - w, y - w); ctx.lineTo(x - w + a, y - w); ctx.moveTo(x - w, y - w); ctx.lineTo(x - w, y + w); ctx.lineTo(x - w + a, y + w);
    ctx.moveTo(x + w, y - w); ctx.lineTo(x + w - a, y - w); ctx.moveTo(x + w, y - w); ctx.lineTo(x + w, y + w); ctx.lineTo(x + w - a, y + w); ctx.stroke();
  }

  drawReserved(f) {
    const ctx = this.ctx, c = this.cell;
    for (const r of f.reservedTiles || []) {
      const g = f.ghosts.find((q) => q.index === r.ghost); if (!g) continue;
      const x = this.ox + r.tile[0] * c, y = this.oy + (this.header.height - 1 - r.tile[1]) * c;
      ctx.strokeStyle = alpha(this.ghostColor(g), 0.9); ctx.lineWidth = Math.max(1, c * 0.07);
      ctx.strokeRect(x + 2, y + 2, c - 4, c - 4);
      ctx.beginPath(); for (let i = 1; i < 4; i++) { ctx.moveTo(x + 2, y + (c * i) / 4); ctx.lineTo(x + (c * i) / 4, y + 2); } ctx.stroke();
    }
  }

  drawBadge(x, y, g) {
    if (!g.role || g.mode === 'eyes') return;
    const ctx = this.ctx, c = this.cell, w = c * 0.5, col = this.roleColor(g);
    ctx.fillStyle = this.C.void; ctx.strokeStyle = col; ctx.lineWidth = Math.max(1.2, c * 0.07);
    const bx = x - w / 2, by = y - c * 0.98;
    ctx.beginPath(); ctx.rect(bx, by, w, w); ctx.fill(); ctx.stroke();
    ctx.fillStyle = col; ctx.font = `700 ${Math.max(8, c * 0.4)}px ${this.C.data}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(ROLE_LETTER[g.role] || '?', x, by + w / 2 + 1);
  }

  drawScared(x, y, g, f) {
    if (g.mode !== 'frightened') return;
    const ctx = this.ctx, c = this.cell, a = f.arcade;
    const left = a ? a.frightLeftSec : g.scaredTimer, max = this.scaredMax.get(g.index) || left || 1;
    ctx.strokeStyle = this.C.cold; ctx.lineWidth = Math.max(1.5, c * 0.09);
    ctx.beginPath(); ctx.arc(x, y, c * 0.66, -Math.PI / 2, -Math.PI / 2 + TAU * Math.min(1, left / max)); ctx.stroke();
    ctx.fillStyle = this.C.cold; ctx.font = `700 ${Math.max(8, c * 0.36)}px ${this.C.data}`; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.fillText(a ? left.toFixed(1) : String(left), x, y + c * 0.62);
  }

  drawCommander(now, gp, f) {
    const ctx = this.ctx, C = this.C, c = this.cell;
    const rx = this.X((this.header.width - 1) / 2), ry = this.Y((this.header.height - 1) / 2), R = c * 0.62;
    this.orders = this.orders.filter((o) => now - o.t0 < ORDER_MS);
    const hot = this.orders.length > 0, col = hot ? C.order : alpha(C.dim, 0.9);
    ctx.fillStyle = C.void; ctx.beginPath(); ctx.arc(rx, ry, R * 1.35, 0, TAU); ctx.fill();
    this.bodyPath(rx, ry, R, false);
    ctx.fillStyle = alpha(col, 0.18); ctx.fill(); ctx.strokeStyle = col; ctx.lineWidth = Math.max(1.2, c * 0.07); ctx.stroke();
    this.drawEyes(rx, ry, R, 'Stop');
    ctx.beginPath();
    ctx.moveTo(rx - R * 0.5, ry - R * 1.0); ctx.lineTo(rx - R * 0.55, ry - R * 1.5); ctx.lineTo(rx - R * 0.2, ry - R * 1.22);
    ctx.lineTo(rx, ry - R * 1.58); ctx.lineTo(rx + R * 0.2, ry - R * 1.22); ctx.lineTo(rx + R * 0.55, ry - R * 1.5);
    ctx.lineTo(rx + R * 0.5, ry - R * 1.0); ctx.closePath(); ctx.stroke();
    ctx.fillStyle = col; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    ctx.font = `700 ${Math.max(8, c * 0.34)}px ${C.data}`; ctx.fillText('COMMANDER', rx, ry + R * 1.15);
    ctx.lineWidth = Math.max(1.5, c * 0.08);
    for (const o of this.orders) {
      const age = now - o.t0, p = this.reduce ? 1 : Math.min(age / 110, 1);
      const a = age < 180 ? 1 : Math.max(0, 1 - (age - 180) / (ORDER_MS - 180));
      const targets = o.ghost ? [o.ghost] : f.ghosts.map((g) => g.index);
      for (const gi of targets) {
        const i = f.ghosts.findIndex((q) => q.index === gi); if (i < 0) continue;
        const gx = this.X(gp[i][0]), gy = this.Y(gp[i][1]), ang = Math.atan2(gy - ry, gx - rx);
        const sx = rx + Math.cos(ang) * R * 1.1, sy = ry + Math.sin(ang) * R * 1.1;
        ctx.setLineDash([c * 0.26, c * 0.18]); ctx.strokeStyle = alpha(C.order, a);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.lineTo(sx + (gx - sx) * p, sy + (gy - sy) * p); ctx.stroke(); ctx.setLineDash([]);
      }
    }
  }

  /** Peer-to-peer ghost speech: curved SOLID arrow with a type chip. Visually unlike the Commander's dashes. */
  drawChatter(now, gp, f) {
    const ctx = this.ctx, C = this.C, c = this.cell;
    this.chatter = this.chatter.filter((q) => now - q.t0 < CHATTER_MS);
    for (const q of this.chatter) {
      const m = q.m, a = Math.max(0, 1 - (now - q.t0) / CHATTER_MS);
      const si = f.ghosts.findIndex((g) => g.index === Number(m.from)); if (si < 0) continue;
      const dests = m.to === 'all' || m.to == null ? f.ghosts.filter((g) => g.index !== Number(m.from)).map((g) => g.index) : [Number(m.to)];
      for (const di of dests) {
        const ti = f.ghosts.findIndex((g) => g.index === di); if (ti < 0 || ti === si) continue;
        const sx = this.X(gp[si][0]), sy = this.Y(gp[si][1]), tx = this.X(gp[ti][0]), ty = this.Y(gp[ti][1]);
        const mx = (sx + tx) / 2 - (ty - sy) * 0.18, my = (sy + ty) / 2 + (tx - sx) * 0.18;
        ctx.strokeStyle = alpha(C.chat, a); ctx.fillStyle = alpha(C.chat, a); ctx.lineWidth = Math.max(2, c * 0.12);
        ctx.beginPath(); ctx.moveTo(sx, sy); ctx.quadraticCurveTo(mx, my, tx, ty); ctx.stroke();
        const ang = Math.atan2(ty - my, tx - mx), hx = tx - Math.cos(ang) * c * 0.5, hy = ty - Math.sin(ang) * c * 0.5, s = c * 0.26;
        ctx.beginPath(); ctx.moveTo(hx + Math.cos(ang) * s, hy + Math.sin(ang) * s);
        ctx.lineTo(hx + Math.cos(ang + 2.5) * s, hy + Math.sin(ang + 2.5) * s); ctx.lineTo(hx + Math.cos(ang - 2.5) * s, hy + Math.sin(ang - 2.5) * s);
        ctx.closePath(); ctx.fill();
        const label = String(m.type);
        ctx.font = `700 ${Math.max(8, c * 0.34)}px ${C.data}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        const w = ctx.measureText(label).width + c * 0.3;
        ctx.fillStyle = alpha(C.void, 0.9 * a); ctx.fillRect(mx - w / 2, my - c * 0.26, w, c * 0.52);
        ctx.strokeRect(mx - w / 2, my - c * 0.26, w, c * 0.52);
        ctx.fillStyle = alpha(C.chat, a); ctx.fillText(label, mx, my + 1);
      }
    }
    const beliefs = readBeliefs(f);               // what each ghost last saw: a hollow diamond at its believed Pac-Man tile
    ctx.lineWidth = Math.max(1, c * 0.06);
    for (const [gi, b] of Object.entries(beliefs)) {
      if (!b || !b.pacTile) continue;
      const g = f.ghosts.find((q) => q.index === Number(gi)); if (!g) continue;
      const x = this.X(b.pacTile[0]), y = this.Y(b.pacTile[1]), r = c * 0.2;
      ctx.strokeStyle = alpha(this.ghostColor(g), 0.8);
      ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); ctx.stroke();
    }
  }

  drawFloaters(now) {
    const ctx = this.ctx, c = this.cell;
    this.floaters = this.floaters.filter((q) => now - q.t0 < 1200);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    for (const q of this.floaters) {
      const age = (now - q.t0) / 1200, rise = this.reduce ? 0 : age * c * 0.9;
      ctx.fillStyle = alpha(q.color, 1 - age * age);
      ctx.font = `${Math.max(8, Math.round(c * 0.5))}px ${this.C.pixel}`;
      ctx.fillText(q.text, this.X(q.x), this.Y(q.y) - rise);
    }
  }
}

export { roleName, payloadText };
