# DESIGN: AI Pac-Man arcade front end (`/play`)

Decision (fixed): **an arcade cabinet on the outside, a surveyor's intel overlay on the inside.**
The owner's complaint was "the interface is nothing like the game". The old pages (`/`, `/live.html`) stay as the
replay desk; `/play` is the front door.

References read before building: vault `_wiki/concepts/{typography-pairings, color-palettes, layout-patterns,
design-aesthetics-catalog}.md`. The catalog's warning for Retro is "cliche = just a pixel font on a modern layout", so the
pixel font is used for the cabinet only (marquee, HUD, menus, splashes, deck) and the page itself is built as a machine:
marquee, glass, control deck.

## Structure

| region | job |
|---|---|
| marquee (top bar) | name, "FREE PLAY", link to the replay desk |
| glass (`#stage`) | one screen at a time; scrolls inside the bezel, never the page |
| control deck (footer) | persistent breadcrumb (`MENU > LEVEL SELECT > LEVEL 2`) and key hints for the current screen |

Routes are hashes: `#/title #/menu #/play #/watch #/run?... #/levels #/levels/N #/scores #/replays #/replays/<trace>
#/options #/about`. Every game URL is deep-linkable (`#/run?kind=watch&layout=...&preset=teacher`), which is how the level
pages launch their demos. Keyboard first: arrows/WASD, Enter, Esc everywhere; every control is also a real button for
mouse and touch; the game screen has a D-pad on coarse pointers.

## Type
- **Press Start 2P** (SIL OFL, bundled, `static/fonts/`): wordmark, menus, HUD, splashes, deck, high-score tables.
  Sizes are fluid `clamp()` tokens (`--px-0` to `--px-4`), kept near multiples of 8 px where it matters.
- **Space Mono** (kept from the surveyor pages): everything in the intel overlay, readouts, source paths.
- **Space Grotesk**: running prose (level explainers, captions). Pixel type is never used for paragraphs.
- No Inter, Roboto or Arial. No font loads from the network (a test greps for external URLs).

## Colour (all OKLCH tokens in `arcade.css :root`)
- Field: near-black blue `--void`, classic wall blue `--wall`, peach dots `--dot`, Pac-Man `--pac`.
- Ghosts by index like the arcade: `--g-blinky` red, `--g-pinky` pink, `--g-inky` cyan, `--g-clyde` orange.
  Frightened: `--fright` blue with a pale face, flashing white near the end; eaten: eyes only.
- Intel: teal-black panel (`--panel`), `--order` (Commander dashes, pincer), `--cold` (scared timers, popups),
  `--chat` (ghost chatter, a green no other mark uses), role colours from the surveyor palette.
- No gradients on type or surfaces other than the bezel shading; no purple-to-blue; no three-card grids (menus are
  lists, the level map is a list plus a detail pane, high scores are leaderboards).

## Motion
Blink (steps, 1.1 s) for `1UP`, `PRESS ENTER`; sprite interpolation between ticks; death wedge (1.4 s); maze flash on
clear; order lines (0.3 s) and chatter arrows (1.4 s fade). No bounce or spring anywhere. `prefers-reduced-motion`:
blink off, no interpolation, no flash, static popups, no fades, power pellets stay lit.

## The one aesthetic risk
**Attract mode plays a real recorded AI-vs-ghosts trace behind the title and menu** (the newest arcade trace in
`dashboard/traces`, looped, COACH layers on, dimmed to 42 %). It is not an animation made for the page: it is the
project's own data (roles, targets, Commander) playing as wallpaper, so the first thing a visitor sees is the thing the
project does. Secondary: static scanlines (Options toggle, never animated, so reduced motion needs nothing).

## Intel layers (key `L` panel, per-layer hotkeys)
Eleven independent layers (`static/play/layers.js`, pure logic, unit-tested under node):

| key | layer | source field |
|---|---|---|
| 1 | planned paths | `ghosts[].path` (BFS route computed by the recorder, **not** the ghost's own route; the legend says so) |
| 2 | ghost targets | `ghosts[].target` |
| 3 | roles + colours | `ghosts[].role` |
| 4 | predicted Pac-Man | `predictedPacman` |
| 5 | pincer target | `predictedPacman` of the Enhanced team (the interceptor's cut-off tile); drawn only for `EnhancedCoordinatedGhostTeam` |
| 6 | reserved tiles | `reservedTiles` |
| 7 | tactical state | `tacticalState`, `macroStrategy` |
| 8 | scared timers | `ghosts[].scaredTimer` or `arcade.frightLeftSec` |
| 9 / C | Commander + orders + ticker | `commander.messages` |
| 0 | ghost chatter | `telemetry.messages`, `telemetry.beliefs` (optional; empty until a team publishes them) |
| H | Pac-Man heatmap | client-side tile counts, capped at the number of tiles |

Not built: the Voronoi territory map (no `voronoiGhostAgents.py` on this branch; `/api/meta` reports `voronoi: false` and
the layer is not listed). Presets: **CLASSIC** (all off), **COACH** (paths, targets, roles, Commander), **TEACHER**
(all on, plus legend and live captions). Choices persist in `localStorage` (try/catch). Captions are generated from frame
fields only (`captions()`); a chatter caption claims a behaviour change only when the receiving ghost's role or target
really changed between two frames.

Chatter is drawn as a curved **solid** green arrow with a type chip, the Commander as **dashed** yellow lines from the
centre, so the two never read alike. Chatter and Commander have separate ticker lanes.

## Performance and leaks
One `requestAnimationFrame` loop per mounted canvas, stopped on screen exit; one `EventSource`, closed on exit (the server
session is stopped too). Capped per-frame growth: orders 24, floaters 16, chatter 24, seen-message keys 400, tickers 14 rows,
heatmap keys at most width x height. The search visualiser's loop ends itself when the animation finishes.
