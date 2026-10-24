# AI Pac-Man

Built on the Berkeley CS188 Pac-Man framework. The original part is phase 3: ghosts that work as a coordinated team instead of chasing independently. For students and anyone curious about multi-agent search.

## What it does

- Search (phase 1): DFS, BFS, UCS and A*, a corners problem and food-search heuristics. `PENDING_TASKS.md` records all search tests passing.
- Multi-agent (phase 2): reflex, minimax, alpha-beta and expectimax Pac-Man agents with a custom evaluation function (25 of 25 tests per `PENDING_TASKS.md`).
- Ghost coordination (phase 3): a `GhostCoordinator` in `multiagent/coordinatedGhostAgents.py` ranks ghosts by distance to Pac-Man and gives them roles. The nearest ghost is the chaser. The next ones are an interceptor aimed at Pac-Man's predicted position, a blocker sent to a choke point, and a sweeper.
- `multiagent/enhancedGhostAgents.py` subclasses the coordinator for the later phase 3 tasks (about 500 lines).

## Status

Phases 1 and 2 are done. Phase 3 code exists, but the checklist in `PENDING_TASKS.md` still lists it as pending. How well the ghosts play is not verified. Phases 4 to 6 (shared tactical state machine, a FastAPI and WebSocket backend, a canvas dashboard) are not started. The course files are unmodified framework code.

## Stack

Python 3 and the CS188 Pac-Man framework.

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
