# Arcade mode

Opt-in rules that follow the real Pac-Man. The default game is still the Berkeley framework
(both autograders unchanged: root 26/25, multiagent 25/25). Nothing here runs without `--arcade`.

Source: the Pac-Man Dossier, <https://pacman.holenet.info/> (fetched for this phase: speed table A.1,
scatter/chase schedule, ghost targeting, house/release rules, scoring, movement/turning rules).
Where the Dossier is silent this document says so and the code marks it `NOT IN DOSSIER`.

## Run

```bash
cd multiagent
python3 pacman.py --arcade -l originalClassic -p GreedyAgent -g ArcadeGhostTeam --frameTime 0.03
python3 pacman.py --arcade --arcadeLevel 5 -l originalClassic -p KeyboardAgent -g ArcadeGhostTeam
python3 tests_arcade.py                                 # unit tests
cd .. && python3 dashboard/live.py                      # then open http://127.0.0.1:8765/live.html
python3 dashboard/live.py record -l originalClassic -p GreedyAgent --arcade --seed 3   # v2 trace
```

Flags added to `multiagent/pacman.py`: `--arcade`, `--arcadeLevel N` (default 1), `--arcadeFrames N`
(default 4). `--ghostRespawnDelay` still exists and is ignored in arcade mode (eyes travel home instead).

## What is implemented (and where the Dossier says it)

| Behaviour | Implementation | Dossier |
|---|---|---|
| Eaten ghost becomes eyes, runs to the tile above the left side of the pen door, enters, is revived and leaves at once | `ghostCollide`, `_scriptDir`, `_arrive` | Ghost house section (eyes target, Blinky leaves again immediately) |
| Escalating ghost score 200/400/800/1600, reset per energizer | `ghostCollide`, `_frighten` | Scoring |
| Dots 10, energizers 50, no bonus for clearing, no time penalty, no death penalty | `_consume`, `install` | Scoring |
| Scatter/chase schedule per level group (7/20/7/20/5/20/5 on level 1; 1033 s / 1037 s third chase, 1/60 s fourth scatter on later levels) | `scheduleSeconds`, `_clock` | Table of scatter/chase periods |
| Schedule timer pauses while frightened | `_clock` | "pauses during frightened mode" |
| Forced reversal on scatter<->chase and when frightened starts; none when frightened ends | `_clock`, `_frighten`, `ghostLegalActions` | Movement and reversal rules |
| Frightened ghosts: pseudo-random start direction, then clockwise until legal | `frightenedChoice` | Frightened movement |
| Fright time per level, speeds per level (Pac-Man, Pac-Man fright, ghost, ghost fright, tunnel, Elroy) | `levelRow`, `frightSeconds` | Table A.1 |
| Blinky targets Pac-Man; Pinky 4 ahead; Inky doubles Blinky->2-ahead vector; Clyde chases from 8+ tiles, else corner | `*Target`, `Arcade*` | Targeting |
| Up-direction overflow bug (Pinky 4 up + 4 left, Inky pivot 2 up + 2 left) | `aheadTile(bug=True)` | Targeting (option `overflowBug`) |
| Turn choice: neighbour tile closest to target, ties up, left, down, right; no voluntary reversal | `chooseExit` | Movement rules |
| Decide one tile ahead | `ArcadeGhost._planAhead` | "looks one tile ahead" |
| Pen release: personal dot limits (Pinky 0, Inky 30 on L1, Clyde 60/50), forced-exit timer 4 s (3 s from L5), exit left, right after a mode change inside | `_onDot`, `_releaseByCounters`, `_clock`, `_arrive` | Ghost house rules |
| Pac-Man loses 1 frame per dot and 3 per energizer | `pacApply`, `_consume` | Table A.1 notes |
| Cruise Elroy 1/2 (dots-left thresholds and speeds; keeps chasing in scatter) | `elroyLevel`, `_pct` | Table A.1, Blinky text |
| Slow ghosts in side tunnels | `_isTunnel`, `_pct` | Table A.1 (tunnel column) |

## How speed fits the framework

A framework round is `--arcadeFrames` arcade frames (default 4 = 1/15 s). One tile is 8 px, and 100 % speed is
1.25 px per frame (Dossier: 75.75757625 px/s at 60.606 Hz). Each agent gets a pixel budget per round
(`1.25 * pct/100 * frames`), moves continuously (fractional tile coordinates, the same mechanism Berkeley
uses for half-speed scared ghosts) and stops at the next tile centre; leftover budget carries over, so the
average speed is exact (Pac-Man 80 % on level 1 is exactly 1 px per frame). Turns happen only at tile
centres, which is where `Actions.getPossibleActions` already allows them. Ghosts always return one of
`state.getLegalActions(i)`; scripted phases (eyes, pen exit, pen waiting) expose exactly one legal action,
so any ghost agent (even `RandomGhost`) works. Per-agent state lives on `AgentState.arcade` (copied with
the state, so lookahead agents are safe). `--arcade` patches the `pacman` module's rules at start-up
(`arcadeRules.install`); `uninstall()` restores the Berkeley rules.

Berkeley-style teams that assume whole-tile positions (`EnhancedCoordinatedGhostTeam`) run under arcade
rules through `dashboard/live.py`'s `SnapGhost` adapter, which shows them a tile-snapped copy of the state.
From the command line use `ArcadeGhostTeam`/`DirectionalGhost`/`RandomGhost`.

## Deviations and gaps (honest list)

- **Not in the Dossier, assumed:** exact scatter-corner tiles (it only says "dead space near each corner";
  `scatterCorner` uses tiles outside the four maze corners), eaten-eye speed (`EYES_PCT = 200`), ghost speed
  inside the pen (set to normal ghost speed), pen door and tunnel coordinates (detected from the layout),
  PRNG algorithm and seed (Python's `random`), no-upward-turn zone coordinates (**not implemented**),
  eye-revive freeze and ghost-eaten freeze (**not implemented**), extra-life thresholds.
- **Not implemented:** fruit, lives (one life), level progression after clearing the maze, the global
  dot counter after a lost life, Elroy suspension after a death (there is no second life), the
  ghost-leaves-pen-through-walls bug, the 8-pixel cornering pre-turn. Pac-Man may reverse between tiles
  (the arcade allows it); he cannot corner early.
- **Whole-tile decision timing:** a ghost chooses at tile centres using the plan made one tile earlier. The
  arcade decides with sub-tile timing we do not model.
- **Mazes:** the Berkeley mazes have no wrap-around tunnel (border walls), so the tunnel slow-zone is the
  1-wide corridor within six columns of each border. Mazes without a detectable pen (most Berkeley layouts)
  start all ghosts active and eyes return to the ghost start tile. `originalClassic` and `mediumClassic`
  have a pen. Pen door width follows the layout (2 tiles in `originalClassic`); eyes use the left door cell.
- **Levels at 0 s fright (17, 19, 20, 21+):** ghosts still reverse when an energizer is eaten but do not
  turn blue. The fetched Dossier text confirms "ghosts stop turning blue at level 19" and a "none"
  fright time; the reversal on those levels was not independently confirmed in the fetched text.
- **Elroy** is switched off on mazes with fewer than 150 dots (the thresholds are absolute).
- Time units: seconds are converted at 60.606 frames/s; a "tick" in the dashboard is one round = 4 frames.

## Live play and commander (dashboard)

See `dashboard/README.md`. The commander ring is a display element, not an agent. Its ticker prints diffs
of `getTelemetry()` (or `roles`/`assignedTargets`/`currentTacticalState` when there is none); for
`ArcadeGhostTeam` the telemetry is the arcade director (mode changes and personality targets).
