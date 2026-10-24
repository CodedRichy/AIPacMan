# Trace schema (v1)

One game = one JSONL file in `dashboard/traces/`. Line 1 is the header, the
last line is the footer, everything between is one frame per tick.
Coordinates are `[x, y]` maze tiles, `y` counted from the bottom (framework
convention). `walls` rows are listed top row first.

A tick = one full round (Pac-Man moved, then every ghost moved). Tick 0 is the
initial state. Roles/targets/reservations describe the coordinator's most
recent decision (the last ghost to act that round); `path` is a BFS route from
the ghost's current tile to its target, computed by the recorder.

## Header (`type: "header"`)
| field | type | note |
|---|---|---|
| schema | int | 1 |
| layout, pacmanAgent, ghostTeam | str | run parameters |
| seed, game, maxTicks | int | |
| recordedAt | str | local ISO time |
| width, height | int | |
| walls | str[height] | `%` wall, space open; top row first |
| numGhosts, foodTotal | int | |

## Frame (`type: "frame"`)
```json
{"type":"frame","tick":38,"score":492,
 "pacman":{"pos":[1,5],"dir":"South"},
 "ghosts":[{"index":1,"pos":[6,7],"dir":"West","scaredTimer":0,
            "role":"interceptor","target":[3,9],"path":[[6,7],[5,7],[3,9]]}],
 "food":[[1,1]], "capsules":[[18,1]],
 "tacticalState":"COORDINATED_HUNT", "macroStrategy":"EARLY_SPREAD",
 "predictedPacman":[3,9],
 "reservedTiles":[{"ghost":2,"tile":[3,6]}],
 "telemetry":{}}
```
| field | note |
|---|---|
| tick, score | int |
| pacman.pos / dir | dir in North/South/East/West/Stop |
| ghosts[].role | `chaser` `interceptor` `blocker` `sweeper` `capsule_guard`, or null (non-coordinated team) |
| ghosts[].target, path | null / `[]` when the team has no coordinator |
| scaredTimer | int, `>0` = frightened |
| tacticalState | `COORDINATED_HUNT` `DEFEND_CAPSULE` `TRAP_AMBUSH` `SCATTER`; null for the base team |
| macroStrategy | `EARLY_SPREAD` `MID_PRESSURE` `ENDGAME_COLLAPSE`; null for the base team |
| predictedPacman | interceptor's target (the coordinator's forward projection); null in SCATTER |
| reservedTiles | per-ghost next-tile reservations |
| telemetry | optional: raw `coordinator.getTelemetry()` dict, when the class provides one. Its `tacticalState` / `macroStrategy` keys, if present, override the attribute values |

## Footer (`type: "end"`)
`ticks`, `score`, `win`, `lose`, `truncated` (hit `maxTicks`).

## SSE (`/stream`)
Events: `header` (header plus `frames` count), `frame` (id = tick), `end`.
Query: `trace`, `speed` (0.1 to 64, 1x = 8 ticks/s), `start` (first tick).
