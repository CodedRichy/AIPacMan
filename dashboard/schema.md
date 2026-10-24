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

## Schema v2 (written by `live.py`, additive)
Header `schema: 2` adds `arcade` (bool), `live`, `tickRate`, and for arcade games `level`, `framesPerRound`
and `house` (`y,x0,x1,doorY,doorXs,exitTile`, or null). Frames add `schema: 2`, `dt` (seconds per tick) and:

| field | note |
|---|---|
| pacman.fpos, ghosts[].fpos | exact `[x, y]` in tiles (fractional between tile centres); `pos` stays the nearest tile, so v1 readers keep working |
| ghosts[].mode | `active`, `frightened`, `eyes`, `house`, `exit` (non-arcade: `active`/`frightened`) |
| arcade | null, or `{level, mode (scatter/chase/frightened), phase, phaseLeftSec, frightLeftSec, combo, dots, elroy, ghostModes[], events[]}`; events are `["mode","chase"]`, `["fright",secs]`, `["fright_end",0]`, `["eaten",ghost,points]` for that tick only |
| commander | `{source: "getTelemetry"\|"attributes"\|"none", messages: [{id,tick,ghost (0 = all),src,text,target,kind}]}` new orders this tick, derived from coordinator state diffs |

Live SSE (`/live/stream`) events: `header`, `frame`, `status` (`state`, `paused`, `tickRate`), `end`.

### Phase 9 additions (campaign sessions, `POST /api/live/start` with `campaign: true`)
Frames from a `CampaignSession` (dashboard/session.py) add, additively:

| field | note |
|---|---|
| hud | `{lives, level, phase, events, fruit, fruitHistory}`. `lives` counts the Pac-Man in play. `phase`: `ready`, `playing`. `events`: `["fruit",kind,points]`, `["extra"]` (extra life at 10,000) for that tick only. `fruit`: null or `{kind, points, pos}` |
| ai | present when an AI plays: `{name, depth, decisions, lastMs, avgMs, maxMs, lastNodes, avgNodes}`. Nodes = `GameState.generateSuccessor` calls made while choosing the move |

`status` events add `phase` (`ready`, `playing`, `dying`, `cleared`, `gameover`), `lives`, `level`, `score`. A new game (one
per life, one per cleared maze) starts with a new `header`; the dots eaten before a death stay eaten.

### Optional telemetry fields for ghost chatter (Phase 10 contract, not emitted until that phase merges)
Read defensively by the layers panel from `frame.telemetry`; when absent the chatter layer stays empty.

| field | shape |
|---|---|
| telemetry.messages | list of `{tick?, from, to ("all" or ghost index), type, payload?, ackOf?}`; `type` is one of SPOTTED, CLAIM, REQUEST_SUPPORT, ACK, HANDOFF, YIELD, WARN (others are drawn as-is). May be the full history each frame: the client de-duplicates on `tick|from|to|type|payload` |
| telemetry.beliefs | `{ghostIndex: {pacTile: [x, y], age}}`: where each ghost believes Pac-Man is, and how stale that is |

Note on `ghosts[].path`: it is a BFS route computed by the recorder from the ghost's tile to its target, not the route the
ghost's own planner chose.
