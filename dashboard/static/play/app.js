// Router, persistent footer (breadcrumb + key hints), attract-mode background, and shared state.
import { h, $, api, store } from './util.js';
import * as LY from './layers.js';
import { mountGame } from './game.js';
import * as scr from './screens.js';

const root = $('#screen'), bgEl = $('#bg'), crumbEl = $('#crumb'), hintEl = $('#hints');

export const app = {
  meta: null, traces: null,
  layers: LY.sanitize(store.get('pac.layers', null), store.get('pac.opts', {}).intel || 'classic'),
  opts() { return { speed: 15, smooth: true, scan: true, intel: 'classic', ...store.get('pac.opts', {}) }; },
  setOpts(o) { store.set('pac.opts', { ...app.opts(), ...o }); applyOpts(); },
  async getMeta() { return app.meta || (app.meta = await api('/api/meta')); },
  async getTraces() { return app.traces || (app.traces = await api('/api/traces')); },
  go(hash) { if (location.hash === hash) route(); else location.hash = hash; },
};

function applyOpts() {
  document.body.classList.toggle('scan', !!app.opts().scan);
}

// ---- attract mode background: a real recorded AI-vs-ghosts trace, looped, dimmed ---------------------------
let bgGame = null;
async function bgOn(on) {
  document.body.classList.toggle('bg-on', on);
  if (!on) { if (bgGame) { bgGame.destroy(); bgGame = null; bgEl.replaceChildren(); } return; }
  if (bgGame) return;
  try {
    const list = (await app.getTraces()).filter((t) => /_v2\.jsonl$/.test(t.name));
    const pick = list.find((t) => /Arcade/.test(t.ghostTeam) && t.layout === 'originalClassic') || list[0];
    if (!pick || !document.body.classList.contains('bg-on') || bgGame) return;
    const inner = h('div', { class: 'bg-inner' });
    bgEl.replaceChildren(inner);
    bgGame = mountGame(inner, { kind: 'attract', trace: pick.name, loop: true, layers: LY.stateFromPreset('coach'), tickRate: 15 });
  } catch (e) { /* no traces: the background stays black */ }
}

// ---- router --------------------------------------------------------------------------------------------------
let current = null;
function parse() {
  const raw = location.hash.replace(/^#/, '') || '/title';
  const [path, qs] = raw.split('?');
  return { parts: path.split('/').filter(Boolean), q: Object.fromEntries(new URLSearchParams(qs || '')) };
}

async function route() {
  if (current && current.destroy) current.destroy();
  current = null;
  root.replaceChildren();
  const { parts, q } = parse();
  const ctx = { app, q, parts, go: app.go };
  let s;
  try {
    switch (parts[0]) {
      case 'menu': s = await scr.menu(root, ctx); break;
      case 'play': s = await scr.setup(root, ctx, 'play'); break;
      case 'watch': s = await scr.setup(root, ctx, 'watch'); break;
      case 'run': s = await scr.run(root, ctx); break;
      case 'levels': s = parts[1] ? await scr.level(root, ctx, Number(parts[1])) : await scr.levels(root, ctx); break;
      case 'scores': s = await scr.scores(root, ctx); break;
      case 'replays': s = parts[1] ? await scr.replay(root, ctx, decodeURIComponent(parts[1])) : await scr.replays(root, ctx); break;
      case 'options': s = await scr.options(root, ctx); break;
      case 'about': s = await scr.about(root, ctx); break;
      default: s = await scr.title(root, ctx);
    }
  } catch (e) {
    root.replaceChildren(h('div', { class: 'panel' }, h('h2', {}, 'SOMETHING BROKE'), h('p', {}, String(e.message || e)), h('a', { class: 'btn', href: '#/menu' }, 'BACK TO MENU')));
    s = { back: '#/menu', crumb: ['ERROR'], hints: [['Esc', 'MENU']] };
  }
  current = s || {};
  bgOn(!!current.bg);
  document.body.dataset.screen = parts[0] || 'title';
  drawFooter(current);
  const focus = root.querySelector('[data-autofocus]') || root;
  if (focus.focus) focus.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function drawFooter(s) {
  const trail = [['#/menu', 'MENU'], ...(s.crumb || []).map((c) => (Array.isArray(c) ? c : [null, c]))];
  const items = (s.crumb && s.crumb.length) ? trail : [[null, 'TITLE']];
  crumbEl.replaceChildren(...items.flatMap(([href, label], i) => [
    i ? h('span', { class: 'sep', 'aria-hidden': 'true' }, '>') : null,
    href && i < items.length - 1 ? h('a', { href }, label) : h('span', { 'aria-current': i === items.length - 1 ? 'page' : null }, label)].filter(Boolean)));
  hintEl.replaceChildren(...(s.hints || []).map(([k, v]) => h('span', { class: 'hint' }, h('kbd', {}, k), ' ' + v)));
}

document.addEventListener('keydown', (e) => {
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === 'Escape' && current && current.back) { e.preventDefault(); app.go(current.back); }
});
addEventListener('hashchange', route);
applyOpts();
route();
