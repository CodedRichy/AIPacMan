# Hunt Table: ghost-team dashboard

Record a headless game, then replay it in the browser with the coordinator's
decisions overlaid: roles, targets, planned paths, predicted Pac-Man,
reserved tiles, tactical state and macro strategy.

Design: record and replay first (no live sync). The framework is untouched;
`record.py` passes a recording display to `ClassicGameRules` and reads the
coordinator's attributes (and `getTelemetry()` when it exists).

## Run

```bash
# from the repo root
python3 dashboard/record.py -l mediumClassic -p GreedyAgent -g EnhancedCoordinatedGhostTeam --seed 12 -n 1 --max-ticks 300
python3 dashboard/server.py --port 8765        # then open http://127.0.0.1:8765/
python3 dashboard/tests/test_dashboard.py       # tests (pytest also works if installed)
```

`server.py` uses only the standard library (FastAPI and uvicorn are not
installed in this environment). The page can also record games itself via
"Record game" (`POST /api/run`).

## Files

| path | purpose |
|---|---|
| `schema.md` | trace format (JSONL: header, frames, footer) and SSE contract |
| `record.py` | recorder CLI and `record_game()` |
| `server.py` | static files, `/api/traces`, `/api/traces/<name>`, `/stream` (SSE), `/api/run` |
| `static/` | `index.html`, `style.css`, `app.js` (canvas, no build step) |
| `tests/` | recorder, schema and server smoke tests |
| `traces/` | recorded games |

## Controls

`Space` play/pause, `Left`/`Right` step (`Shift` = 10), `Home`/`End`, `[` `]` speed,
`1`-`5` toggle layers (paths, targets, reserved, predicted, food), `T` focus trace list.

Scrubbing works on the whole downloaded trace; playback is driven by the SSE
stream (`speed` 0.25x to 16x, 1x = 8 ticks/s).

## Notes

- A tick is one full round. Roles and targets are the coordinator's latest
  decision; paths are BFS routes computed by the recorder.
- `predictedPacman` is the interceptor's target (the forward projection); it is hidden in SCATTER.
- Set `PACMAN_GAME_DIR` to record from a different game directory.

## Live play, arcade mode and the commander (Phase 8)

```bash
python3 dashboard/live.py                      # same server as server.py plus /live; localhost only
#   open http://127.0.0.1:8765/live.html, "New game", Start; steer with arrows or WASD, Space pauses, C hides the commander
python3 dashboard/live.py record -l originalClassic -p GreedyAgent --arcade --seed 3     # headless v2 trace
python3 dashboard/tests/test_live.py           # live server, frames, commander tests
```

- `live.py` runs the game in-process on a worker thread. Frames leave over SSE (`/live/stream`), keys come
  back as `POST /api/key`. `BrowserKeyboardAgent` is also the metronome (tick rate 2-60/s, default 15).
  `server.py` is reused by subclassing, not edited. Requests with a non-loopback `Host`/`Origin` are refused.
- `static/live.js` interpolates every actor between ticks on `requestAnimationFrame` (`fpos`); the
  `Smooth` toggle and `prefers-reduced-motion` turn that off. All animations are under 2 s, no bounce.
- Commander: a stationary crowned ghost (same size as the hunters) labelled COMMANDER at the maze centre (not a game agent) and a side ticker. Each line is a diff of
  real coordinator state (`getTelemetry()` first, else `roles`/`assignedTargets`/`currentTacticalState`),
  computed in `commander.py`; a dashed line runs from the Commander to the ghost for 300 ms on a new order.
  `C` or the Commander button hides it (remembered in localStorage). Ghost teams without a coordinator
  (RandomGhost) produce no messages.
- `live.html?trace=<name>_v2.jsonl&t=120&pause=1` replays a v2 trace with the same renderer.
- Fonts (Space Grotesk, Space Mono; SIL OFL 1.1, licences in `static/fonts/`) are bundled: the page makes no
  external requests. The only `http://` string left in `static/` is the SVG namespace inside the favicon data URI.
- Contrast: `--ink-faint` raised to `oklch(0.68 0.018 130)`: at least 5.5:1 on every surface (it was 4.76:1 on `--surface-2`).
