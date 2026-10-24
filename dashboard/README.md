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
