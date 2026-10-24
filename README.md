# AI Pac-Man

Built on the Berkeley CS188 Pac-Man framework. The original part is the ghosts: a team that coordinates (roles, prediction, pincer, messaging) instead of chasing independently, plus an arcade-style browser front end that lets you play against them and see what they are doing. For students and anyone curious about multi-agent search.

## How to run

You need Python 3 (tested on 3.14). The browser version needs nothing else. The old terminal window needs `tkinter`.

### 1. Play in the browser (recommended)

From the repo root:

```bash
python3 dashboard/live.py --port 8765
```

Then open <http://127.0.0.1:8765/play>. The server only listens on your own machine and loads nothing from the internet.

- **Arrow keys or W/A/S/D** steer Pac-Man. **Enter** confirms, **Esc** goes back, number keys jump to a menu item.
- **PLAY** asks you to pick a mode:
  - **CLASSIC**: Berkeley's original ghosts and rules. The baseline.
  - **OUR GHOSTS**: same game against our coordinated ghost team. Try to beat them.
  - **ARCADE**: closer to the real Pac-Man: four ghost personalities, scatter and chase phases, real speeds, 3 lives.
  - **SEE HOW THEY THINK**: an AI Pac-Man against our ghosts with the thinking overlay on.
  - **VERSUS**: the same AI Pac-Man and seed against the stock ghosts and ours, side by side, with a verdict built from the two real results. `N` tries a new seed, `M` changes the maze.
- **WATCH** lets you pick the AI (greedy, minimax, alpha-beta, expectimax). **LEARN** is the project map, one level per phase, with demos and real numbers (level 1 has a search visualiser). **SCORES** ranks the ghost teams from the newest benchmark. **MORE** has replays, options and about.
- **T** switches "show the thinking" on or off (ghost roles, targets, planned paths and the Commander's orders). **L** opens the full layers panel. **C** hides the Commander.

### 2. Run the classic terminal game

Search agents, from the repo root:

```bash
python3 pacman.py
python3 pacman.py -l tinyMaze -p SearchAgent
python3 pacman.py -l mediumMaze -p SearchAgent -a fn=bfs
python3 pacman.py -l bigMaze -z .5 -p SearchAgent -a fn=astar,heuristic=manhattanHeuristic
```

Ghost teams, from inside `multiagent/`:

```bash
cd multiagent
python3 pacman.py -p KeyboardAgent -g EnhancedCoordinatedGhostTeam -l originalClassic   # you play
python3 pacman.py -p GreedyAgent -g CoordinatedGhostTeam -l mediumClassic                # AI plays
python3 pacman.py --arcade -l originalClassic -g ArcadeGhostTeam -p GreedyAgent          # arcade rules
python3 pacman.py -p ExpectimaxAgent -a depth=2 -g DirectionalGhost -l smallClassic      # AI vs stock ghosts
python3 pacman.py -p GreedyAgent -g EnhancedCoordinatedGhostTeam -l mediumClassic -n 20 -q -f   # 20 games, no window, fixed seed
```

Other ghost teams you can pass to `-g`: `DirectionalGhost` and `RandomGhost` (course), `VoronoiGhostTeam`, `ChatterGhostTeam`, `SilentFogGhostTeam`, `LossyChatterGhostTeam`. Add `-r` to record a game (saved as `recorded-game-*`), and `--replay <file>` to watch it again.

### 3. Check that everything works

From the repo root:

```bash
python3 autograder.py --no-graphics                  # search: expect 26/25
(cd multiagent && python3 autograder.py --no-graphics)   # multi-agent: expect 25/25
python3 -m unittest discover -s tests                # integration and messaging tests
python3 dashboard/tests/test_dashboard.py            # dashboard tests (also test_live.py, test_arcade.py)
python3 multiagent/tests_arcade.py                   # arcade rule tests
```

### 4. Benchmarks

```bash
python3 benchmarks/run_benchmark.py --quick
python3 benchmarks/run_benchmark.py --games 200 --pacman GreedyAgent --layouts mediumClassic
python3 benchmarks/chatter_ablation.py --games 100   # does ghost messaging help?
cd multiagent && python3 bakeoff.py --phase dev --games 40 --jobs 4   # about 35 minutes
```

Results go to `benchmarks/results/`. Lower Pac-Man score means a stronger ghost team.

### Keep a runaway job from taking the desktop down

Early on, a leaking search job exhausted RAM and the kernel killed VS Code. The leak is fixed, but long benchmarks should still run under a memory cap:

```bash
tools/capped -m 4G -- python3 benchmarks/run_benchmark.py --games 200
```

A job that goes over its cap dies alone.

## What it does

- **Search (phase 1):** DFS, BFS, UCS and A*, a corners problem and food-search heuristics.
- **Multi-agent (phase 2):** reflex, minimax, alpha-beta and expectimax Pac-Man agents with a custom evaluation function.
- **Ghost coordination (phases 3 and 4):** `multiagent/coordinatedGhostAgents.py` and `multiagent/enhancedGhostAgents.py`. A shared coordinator gives ghosts roles (chaser, interceptor, blocker, sweeper), predicts Pac-Man, sets a pincer target, claims tiles per tick, and runs a tactical state machine with scared-ghost fleeing. Details: `docs/ARCHITECTURE.md`.
- **Dashboard (phase 5):** record-and-replay dashboard in `dashboard/` (stdlib server with Server-Sent Events).
- **Arcade mode and the Commander (phase 8):** `--arcade` adds eyes returning to the ghost house, scatter and chase timers, 200/400/800/1600 scoring and four ghost personalities (`docs/ARCADE_MODE.md`). The Commander is a stationary crowned ghost that shows the coordinator's real orders; it is a display element, not a game agent.
- **Arcade front end (phases 9 and 12):** the `/play` interface above.
- **Ghost messaging (phase 10):** ghosts pass real messages on a bus under partial visibility ("fog") (`docs/GHOST_MESSAGING.md`).
- **Bake-off (phase 7):** other ghost designs compared (`docs/BAKEOFF.md`).

## Results (measured)

GreedyAgent on `mediumClassic`, 200 games per team, `benchmarks/BASELINE.md`. Lower Pac-Man average score means a stronger ghost team:

| Ghost team | Pac-Man avg score | Avg moves until caught |
|---|---|---|
| EnhancedCoordinatedGhostTeam | -284 | 22 |
| CoordinatedGhostTeam | -273 | 23 |
| DirectionalGhost (course baseline) | -103 | 58 |
| RandomGhost | +61 | 139 |

Both coordinated teams beat the course's ghosts by a wide margin against this Pac-Man, and the two are statistically tied. Honest limits:

- Against expectimax Pac-Man the ghosts are still weak: it grabs a capsule and hunts the scared ghosts, and the score stays above zero on `mediumClassic`.
- Ghost messaging does not reliably help. The gain with 2 ghosts is marginal and there is none with 4. It is a demonstration of coordination, not the default team.
- The Voronoi team is clearly better only on `originalClassic` and worse on `contestClassic`. `CoordinatedGhostTeam` stays the default (`docs/BAKEOFF.md`).
- Pac-Man agents are only as strong as the course reference; the ghost side is where the new work is.
- Nothing learns from play yet. `docs/PHASE11_LEARNING.md` is a plan for ghosts that learn a player's habits.

`PENDING_TASKS.md` has the per-phase status and what is verified versus reported.

## Repo map

| Path | What is there |
|---|---|
| `search.py`, `searchAgents.py` | Phase 1 search |
| `multiagent/` | Phase 2 agents, ghost teams, arcade rules, bake-off, demo layouts |
| `dashboard/` | Server, recorder, arcade front end (`static/`), design notes in `DESIGN.md` |
| `benchmarks/`, `tests/` | Benchmark harness, profiler, integration and messaging tests |
| `docs/` | Architecture, arcade mode, ghost messaging, bake-off, config wiring, demo layouts |
| `tools/capped` | Runs a command under a hard memory cap |

The repo currently has the framework files at the root and again inside `multiagent/`; reorganising that is on the to-do list. `multiagent/ghostConfig.py` (tunable parameters) is written and tested but not yet wired into the ghost code.

## License

All rights reserved. The Berkeley CS188 framework files remain under their original terms.
