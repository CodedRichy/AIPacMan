# AI Pac-Man - Status Checklist

Legend: [x] done and verified by running it, [~] done but with a stated gap, [ ] not done.
Numbers marked "(agent)" were reported by a build agent and not re-measured by the lead.
Last full check (merged `main`): search autograder 26/25, multiagent autograder 25/25, `python3 -m unittest discover -s tests` 27 pass, dashboard / live / arcade tests pass.

## Phase 1: Search (Completed)
- [x] DFS, BFS, UCS, A*, corners problem and heuristic, food heuristic, closest dot
- [x] Autograder 26/25
- [x] A* skips stale queue entries; shared cached corners/food bound. A* expansions at equal cost, mediumCorners 357 -> 249, trickySearch 410 -> 255 (agent)

## Phase 2: Multi-Agent (Completed)
- [x] Reflex, Minimax, AlphaBeta, Expectimax agents and the better evaluation function; autograder 25/25
- [ ] A cleanup refactor of `multiAgents.py` exists on branch `worktree-agent-a531992b31a03fcb1` (no strength gain, speed not re-timed). Not merged.

## Phase 3: Ghost Coordination (Completed)
- [x] Coordinator, roles, maze-distance path planning, trajectory prediction, pincer, per-tick reservations (the original reservation table never fired; fixed)
- [x] Measured on merged `main` (GreedyAgent, mediumClassic, 200 games, Pac-Man average score, lower = stronger ghosts): Enhanced -284, Coordinated -273, stock DirectionalGhost -103, RandomGhost +61. See `benchmarks/BASELINE.md`.
- [~] Against Expectimax depth 2, Pac-Man still scores above zero on mediumClassic (it takes a capsule, then hunts scared ghosts). Better than stock but not solved.

## Phase 4: Advanced Coordination (Completed)
- [x] Shared perception, tactical state machine, strategy switching, scared-ghost fleeing, `getTelemetry()`
- [x] Fixed: state leaked between games, roles recomputed per ghost per tick, whole team scattering when one ghost was scared, state flapping
- [~] Ablation: fleeing and the tactical state help; macro strategy and sticky roles show no measurable effect

## Phase 5: Visualization & Dashboard (Completed, with deviations)
- [x] Record-and-replay dashboard (`dashboard/`): recorder, server, canvas UI, tests
- [~] Deviation: stdlib server with Server-Sent Events plus a key POST, not FastAPI/WebSocket (neither is installed; one-way telemetry needs only SSE)

## Phase 6: Integration & Polish (In progress)
- [x] Integration tests, benchmark harness, demo layouts, profile, architecture docs
- [~] `multiagent/ghostConfig.py` is written and tested but NOT wired into the ghost files (`docs/CONFIG_WIRING.md`)
- [ ] Performance optimization: profiled only; ghost decisions cost about 0.2 ms each

## Phase 7: Ghost algorithm bake-off (Completed)
- [x] Voronoi, Voronoi+expectimax and maze-distance-chase teams compared with 95% CIs, with a held-out layout and agent (`docs/BAKEOFF.md`)
- Result: no clear winner. `VoronoiGhostTeam` is clearly better only on originalClassic (4 ghosts); worse on contestClassic; tied elsewhere. Recommendation: keep `CoordinatedGhostTeam` as default.

## Phase 8: Arcade mode, live play, Commander (Completed, partly unverified)
- [x] `--arcade`: eyes and ghost-house revival, scatter/chase timers, 200/400/800/1600 scores, four personalities, speed ratios (`docs/ARCADE_MODE.md`)
- [x] Browser live play with key POSTs; Commander ghost with real order messages
- [~] Not verified: real-time feel. Not built: lives and level progression inside the engine (done in the Phase 9 session layer), no-upward-turn zones, ghost freeze on eating

## Phase 9: Arcade front end (Completed, partly unverified)
- [x] `/play`: title, menu, play and watch-AI setup, level select with 7 level pages, search visualiser, high scores, replays, layers panel with CLASSIC / COACH / TEACHER presets
- [~] Not verified: input latency, death and level-clear animations, initials entry, RUN BENCHMARK click

## Phase 10: Ghost messaging (Completed)
- [x] Message bus with fog mode; eight message types that change receiver behaviour (`docs/GHOST_MESSAGING.md`)
- [~] Honest result: communication does not reliably help (marginal gain on 2 ghosts, none on 4). Keep as a demonstration feature, not the default team.

## Phase 11: Ghosts that learn player habits (Planned)
- [ ] See `docs/PHASE11_LEARNING.md`

## Other
- [x] Memory leak fixed: `GameState.explored` kept every generated state (multi-GB per search game). Tracking now starts only when the grader asks.
- [x] `tools/capped` runs a job under a hard memory cap
- [ ] Repo reorganisation (framework duplicated at root and in `multiagent/`)
- [ ] Nothing is pushed to GitHub
