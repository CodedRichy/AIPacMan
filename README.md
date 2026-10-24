# AI Pac-Man

Built on the Berkeley CS188 Pac-Man framework. The original part is phase 3: ghosts that work as a coordinated team instead of chasing independently. For students and anyone curious about multi-agent search.

## What it does

- Search (phase 1): DFS, BFS, UCS and A*, a corners problem and food-search heuristics. `PENDING_TASKS.md` records all search tests passing.
- Multi-agent (phase 2): reflex, minimax, alpha-beta and expectimax Pac-Man agents with a custom evaluation function (25 of 25 tests per `PENDING_TASKS.md`).
- Ghost coordination (phase 3): a `GhostCoordinator` in `multiagent/coordinatedGhostAgents.py` ranks ghosts by distance to Pac-Man and gives them roles. The nearest ghost is the chaser. The next ones are an interceptor aimed at Pac-Man's predicted position, a blocker sent to a choke point, and a sweeper.
- `multiagent/enhancedGhostAgents.py` subclasses the coordinator and adds velocity-based trajectory prediction, a pincer target for the interceptor, tile reservation, a shared-perception layer, a tactical state machine (SCATTER, DEFEND_CAPSULE, TRAP_AMBUSH, COORDINATED_HUNT), dynamic strategy switching on food remaining (EARLY_SPREAD, MID_PRESSURE, ENDGAME_COLLAPSE) and scared-ghost scatter. Details and the places where the code does less than its comments say are in `docs/ARCHITECTURE.md`.
- Tooling: a headless benchmark (`benchmarks/run_benchmark.py`), a profiler (`benchmarks/profile_ghosts.py`), integration tests (`tests/test_integration.py`), six demo layouts (`multiagent/layouts/demo_*.lay`, see `docs/DEMO_LAYOUTS.md`) and a not-yet-wired tunable-parameter module (`multiagent/ghostConfig.py`, see `docs/CONFIG_WIRING.md`).

## Status

Phases 1 to 4 are implemented and checked off in `PENDING_TASKS.md`. Implemented is not the same as effective. Measured against `GreedyAgent` on `mediumClassic` (200 games per team, `benchmarks/BASELINE.md`), a lower Pac-Man score means a better ghost team:

| Ghost team | Pac-Man avg score |
|---|---|
| CoordinatedGhostTeam (base roles) | about -225 |
| DirectionalGhost (course baseline) | about -103 |
| EnhancedCoordinatedGhostTeam | about -14 |
| RandomGhost | about +61 |

The enhanced team, which has the tactical state machine, strategy switching, pincer and reservation, is a weaker hunter than the plain base coordinator and than the course's `DirectionalGhost`. So the phase 4 features are not an improvement as built, and the numbers are negative for them. Instrumented runs show why in part: path reservation never fires (the table is cleared whenever any ghost has moved), and the TRAP_AMBUSH state is the most common state but changes no behavior. Small samples mislead here: a 20-game run gave very different averages from the 200-game run because score variance is large.

Phase 5 (a FastAPI and WebSocket backend, a canvas dashboard) is being built separately and is not part of this branch. Phase 6: integration tests, a benchmark harness, profiling, demo layouts and the config module exist; the config module is not connected to the ghost code. The course files are unmodified framework code.

## Stack

Python 3 and the CS188 Pac-Man framework. The benchmark, tests and config module use only the standard library.

## Benchmarks and tests

From the repo root:

```bash
python3 benchmarks/run_benchmark.py --games 20 --pacman GreedyAgent --layouts mediumClassic
python3 benchmarks/run_benchmark.py --quick
python3 benchmarks/profile_ghosts.py --games 5
python3 -m unittest discover -s tests -v
```

## Run it

Search agents, from the repo root:

```bash
python pacman.py
python pacman.py -l tinyMaze -p SearchAgent
python pacman.py -l mediumMaze -p SearchAgent -a fn=bfs
python pacman.py -l bigMaze -z .5 -p SearchAgent -a fn=astar,heuristic=manhattanHeuristic
```

Coordinated ghosts, from inside `multiagent/` (the usage comment at the top of `enhancedGhostAgents.py`):

```bash
python pacman.py -p GreedyAgent -g EnhancedCoordinatedGhostTeam -l mediumClassic
python pacman.py -p KeyboardAgent -g EnhancedCoordinatedGhostTeam -l mediumClassic -n 1
```

## License

All rights reserved. The Berkeley CS188 framework files remain under their original terms.
