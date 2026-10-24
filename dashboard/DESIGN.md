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

Routes are hashes: `#/title #/menu #/play #/play/custom #/watch #/versus #/run?... #/levels #/levels/N #/scores #/more
#/replays #/replays/<trace> #/options #/about`. Every game URL is deep-linkable (`#/run?kind=watch&layout=...&preset=teacher`), which is how the level
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

## Phase 12: fewer choices, same capability

The owner's complaint was "so many modes, it's hard to understand the difference in the options". Nothing was deleted;
the choices were regrouped and renamed. The look, fonts, title, attract mode, level select, search visualiser, high scores
and replays are unchanged.

- **Main menu (5):** PLAY, WATCH, LEARN (level select), SCORES, MORE (replays, options, about: the only sub-menu).
- **PLAY = mode picker** (`static/play/modes.js` is the single source of truth, tested by `tests/modes_test.mjs`). A mode is a
  saved set of the same parameters CUSTOM edits: CLASSIC (original ghosts and rules, originalClassic), OUR GHOSTS
  (EnhancedCoordinatedGhostTeam, original rules), ARCADE (ArcadeGhostTeam, arcade rules), SEE HOW THEY THINK (AlphaBeta depth 2
  vs our ghosts on mediumClassic, thinking on), VERSUS. OUR GHOSTS is highlighted on first run.
- **SHOW THE THINKING: OFF / ON** is one switch (key `T`; also in the picker, CUSTOM, Options and the side panel). ON is the
  TEACHER layer preset. The presets and the eleven toggles live under **ADVANCED LAYERS** in the `L` panel (collapsed); all layer
  hotkeys still work, and old `preset=coach|teacher|classic` links still work.
- **CUSTOM** (`#/play/custom`, and WATCH `#/watch`): rows grouped BASIC (maze, ghost team) and ADVANCED (Pac-Man agent and
  look-ahead for WATCH, rules, thinking). Maze, team and agent open an inline list on Enter; experimental ghost teams sit under an
  EXPERIMENTAL heading at the bottom, each with a one-line description.
- **Mode badge** at the top of every game: name plus one line (`OUR GHOSTS  coordinated team, original rules`). A game started
  from a level demo or CUSTOM that matches no mode says CUSTOM and describes itself. Game over offers PLAY THE OTHER SIDE
  (CLASSIC <-> OUR GHOSTS, same maze and seed), PLAY AGAIN, CHOOSE A MODE.
- **VERSUS** (`dashboard/versus.py`): GreedyAgent, one maze, one seed (default originalClassic, seed 7), once against the
  original ghosts and once against ours. Both are real engine runs (`live.build_game` + `FrameDisplay`), run one after the other
  because the engine seeds the process-wide RNG and keeps rule state in module globals, so concurrent games would not be
  deterministic. The browser plays the two recordings side by side with live move counters; the verdict line is computed from the
  two finished runs (`versus.verdict`). One worker thread, at most 600 frames a side, dropped on leaving the screen
  (`POST /api/versus/stop`).

### Key presses from the title

Number keys `1` to `7` jump to and open an item in the main menu, MORE and the mode picker, so no screen costs more than before.

| screen | before | now |
|---|---|---|
| main menu | 1 | 1 (Enter) |
| start a game, first run | 4 (Enter, Enter, Enter to jump to START, Enter) | **3** (Enter, Enter, Enter on OUR GHOSTS) |
| another mode (CLASSIC, ARCADE, THINK, VERSUS) | 4 or more | 3 (Enter, `1`, then `1` to `5`) |
| CUSTOM | 4 | 3 (Enter, `1`, `7`), then START |
| WATCH setup | 3 | 3 (Enter, `2`) |
| LEARN, SCORES | 3 | 3 (Enter, `3` or `4`) |
| MORE | n/a | 3 (Enter, `5`) |
| REPLAYS | 5 (Enter, Up x3, Enter) | 3 (Enter, `5`, `1`) |
| OPTIONS | 4 | 3 (Enter, `5`, `2`) |
| ABOUT | 3 | 3 (Enter, `5`, `3`) |

Esc goes back one step everywhere (a list open inside CUSTOM closes first), Enter confirms, and the footer hints are on
every screen. Selections from the main menu: every screen is 1 or 2; CUSTOM and VERSUS are 2 (PLAY, then the item).
The picker's first Enter (title) and second Enter (PLAY) land on the mode list, so a game starts on the third Enter,
not the second: the title and menu screens cannot be skipped without removing screens the owner likes.

## Performance and leaks
One `requestAnimationFrame` loop per mounted canvas, stopped on screen exit; one `EventSource`, closed on exit (the server
session is stopped too). Capped per-frame growth: orders 24, floaters 16, chatter 24, seen-message keys 400, tickers 14 rows,
heatmap keys at most width x height. The search visualiser's loop ends itself when the animation finishes.
