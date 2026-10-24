# Baseline (measured on this branch)

Environment: Python 3.14.8, Linux, 16 CPUs, 15 parallel workers, one game per subprocess, headless.
Pac-Man lower score = better ghost team. Seeds: game i uses `seed + i`. Ghost code and Pac-Man agents
are the versions in this worktree (c99976f) at measurement time; the concurrent branches may change them.

## Headline: GreedyAgent vs each team on mediumClassic

```
python3 benchmarks/run_benchmark.py --games 200 --pacman GreedyAgent --layouts mediumClassic
python3 benchmarks/run_benchmark.py --games 200 --seed 5000 --pacman GreedyAgent --layouts mediumClassic
```

| Ghost team | Pac-Man avg score, 200 games, seeds 1000+ | same, seeds 5000+ | 20 games, seeds 1000+ | Previously quoted (20 games) |
|---|---|---|---|---|
| CoordinatedGhostTeam | -225 (sd 319) | -230 | -0 | -162 |
| EnhancedCoordinatedGhostTeam | -14 (sd 481) | -12 | +131 | +181 |
| DirectionalGhost | -103 (sd 302) | -84 | -113 | -103 |
| RandomGhost | +61 (sd 419) | +62 | +82 | +63 |

Reading it:
* Pac-Man dies in essentially every game against the three chasing teams (win rate 0-2%), so score
  (food eaten before death) and survival time are the useful signals. Average moves survived:
  Coordinated about 30, Enhanced about 49, Directional about 58, Random about 120.
* The 20-game numbers are noise: score sd is 300-480, so the standard error at n=20 is 70-110. The
  quoted "+181 for Enhanced" is a 20-game artifact; at 200 games (two independent seed sets agree) it is
  about -13. The ordering that holds is **Coordinated (strongest) < Directional < Enhanced < Random
  (weakest)**. The enhanced team is a weaker hunter than the base team it extends and than the course's
  DirectionalGhost. Its extra machinery has not paid for itself.
* Cost: both coordinated teams take about 0.2-0.5 ms per ghost decision (higher when the CPU is
  saturated by parallel workers) against 0.03-0.05 for course ghosts.

## Full matrix (20 games per cell)

```
python3 benchmarks/run_benchmark.py --games 20 --timeout 120
```

Raw data: `benchmarks/results/full-matrix-20.json` (per-game records). Table below. Caveats:

* Search Pac-Man agents (Expectimax/AlphaBeta depth 2) and the two coordinated teams are all
  deterministic, so all 20 seeds give the same game (sd 0). Those cells are one sample, not twenty.
  Only GreedyAgent tie-breaking and the Random/Directional ghosts use the seed.
* `demo_open_field` is run with GreedyAgent only; depth-2 search against 4 ghosts on an open grid takes
  minutes per game (`SEARCH_SKIP_LAYOUTS` in the script).
* `originalClassic` vs RandomGhost with search agents: most games exceed the 120 s per-game timeout
  and are counted as failed (the "Games (failed)" column); averages use only the finished games.
* "Capped" = Pac-Man hit the 1500-move cap without a win or loss. Expectimax and AlphaBeta vs
  EnhancedCoordinatedGhostTeam on `demo_capsule_corner` capped 20/20: a permanent standoff where
  neither side makes progress (ghosts keep moving, so this is not a freeze). Not diagnosed further.
* Wall-clock ms/ghost decision is inflated in this table because 15 games ran in parallel.
* The engine's `game.numMoves` never increments (its condition `agentIndex == numAgents + 1` is never
  true), so "moves" here is counted by wrapping Pac-Man's `getAction`.
* The 100% win cells (Expectimax smallClassic vs Enhanced, AlphaBeta smallClassic vs Coordinated) are a
  single deterministic game each, not a rate.

| Pac-Man | Layout | Ghosts | Games (failed) | Win % | Loss % | Capped | Avg score (sd) | Avg moves | Avg kill time | ms/ghost decision |
|---|---|---|---|---|---|---|---|---|---|---|
| GreedyAgent | mediumClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -0.2 (434) | 50 | 50 | 0.72 |
| GreedyAgent | mediumClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 130.8 (348) | 58 | 58 | 0.63 |
| GreedyAgent | mediumClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -113.0 (279) | 60 | 60 | 0.12 |
| GreedyAgent | mediumClassic | RandomGhost | 20 (0) | 5 | 95 | 0 | 81.9 (434) | 111 | 105 | 0.05 |
| GreedyAgent | smallClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -219.9 (175) | 38 | 38 | 0.57 |
| GreedyAgent | smallClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -391.8 (73) | 13 | 13 | 0.48 |
| GreedyAgent | smallClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -304.1 (186) | 24 | 24 | 0.08 |
| GreedyAgent | smallClassic | RandomGhost | 20 (0) | 10 | 90 | 0 | -182.2 (391) | 59 | 44 | 0.05 |
| GreedyAgent | originalClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -164.5 (317) | 36 | 36 | 3.13 |
| GreedyAgent | originalClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 161.2 (436) | 70 | 70 | 3.01 |
| GreedyAgent | originalClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | 119.9 (352) | 101 | 101 | 0.06 |
| GreedyAgent | originalClassic | RandomGhost | 20 (0) | 0 | 100 | 0 | 270.3 (397) | 237 | 237 | 0.05 |
| GreedyAgent | demo_corridor_trap | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -466.2 (21) | 4 | 4 | 0.75 |
| GreedyAgent | demo_corridor_trap | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -466.2 (21) | 4 | 4 | 0.83 |
| GreedyAgent | demo_corridor_trap | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -466.2 (21) | 4 | 4 | 0.07 |
| GreedyAgent | demo_corridor_trap | RandomGhost | 20 (0) | 0 | 100 | 0 | -453.2 (26) | 8 | 8 | 0.06 |
| GreedyAgent | demo_pincer_arena | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -246.4 (368) | 22 | 22 | 0.77 |
| GreedyAgent | demo_pincer_arena | EnhancedCoordinatedGhostTeam | 20 (0) | 5 | 95 | 0 | -147.4 (634) | 24 | 17 | 0.84 |
| GreedyAgent | demo_pincer_arena | DirectionalGhost | 20 (0) | 5 | 95 | 0 | -249.8 (516) | 21 | 15 | 0.08 |
| GreedyAgent | demo_pincer_arena | RandomGhost | 20 (0) | 5 | 95 | 0 | -127.3 (496) | 44 | 39 | 0.06 |
| GreedyAgent | demo_capsule_corner | CoordinatedGhostTeam | 20 (0) | 35 | 65 | 0 | 511.6 (547) | 132 | 95 | 0.46 |
| GreedyAgent | demo_capsule_corner | EnhancedCoordinatedGhostTeam | 20 (0) | 45 | 55 | 0 | 684.1 (483) | 149 | 113 | 0.44 |
| GreedyAgent | demo_capsule_corner | DirectionalGhost | 20 (0) | 5 | 95 | 0 | 93.0 (365) | 93 | 89 | 0.08 |
| GreedyAgent | demo_capsule_corner | RandomGhost | 20 (0) | 25 | 75 | 0 | 307.4 (634) | 152 | 145 | 0.04 |
| GreedyAgent | demo_open_field | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -76.8 (533) | 54 | 54 | 2.19 |
| GreedyAgent | demo_open_field | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -254.1 (257) | 27 | 27 | 2.10 |
| GreedyAgent | demo_open_field | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -361.0 (38) | 16 | 16 | 0.13 |
| GreedyAgent | demo_open_field | RandomGhost | 20 (0) | 0 | 100 | 0 | 369.2 (498) | 121 | 121 | 0.05 |
| GreedyAgent | demo_long_loop | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -418.8 (10) | 10 | 10 | 0.44 |
| GreedyAgent | demo_long_loop | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -418.8 (10) | 10 | 10 | 0.42 |
| GreedyAgent | demo_long_loop | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -404.0 (26) | 12 | 12 | 0.07 |
| GreedyAgent | demo_long_loop | RandomGhost | 20 (0) | 0 | 100 | 0 | -319.1 (107) | 34 | 34 | 0.06 |
| GreedyAgent | demo_dead_end_comb | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -441.1 (15) | 10 | 10 | 0.54 |
| GreedyAgent | demo_dead_end_comb | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -441.1 (15) | 10 | 10 | 0.73 |
| GreedyAgent | demo_dead_end_comb | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -434.9 (29) | 17 | 17 | 0.16 |
| GreedyAgent | demo_dead_end_comb | RandomGhost | 20 (0) | 0 | 100 | 0 | -209.6 (165) | 157 | 157 | 0.05 |
| ExpectimaxAgent:2 | mediumClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 506.0 (0) | 94 | 94 | 0.55 |
| ExpectimaxAgent:2 | mediumClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 500.0 (0) | 100 | 100 | 0.42 |
| ExpectimaxAgent:2 | mediumClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | 411.8 (188) | 151 | 151 | 0.07 |
| ExpectimaxAgent:2 | mediumClassic | RandomGhost | 20 (0) | 5 | 40 | 11 | -292.9 (471) | 1175 | 786 | 0.05 |
| ExpectimaxAgent:2 | smallClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -376.0 (0) | 16 | 16 | 0.39 |
| ExpectimaxAgent:2 | smallClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 100 | 0 | 0 | 1320.0 (0) | 130 | - | 0.38 |
| ExpectimaxAgent:2 | smallClassic | DirectionalGhost | 20 (0) | 20 | 80 | 0 | 302.4 (580) | 101 | 84 | 0.10 |
| ExpectimaxAgent:2 | smallClassic | RandomGhost | 20 (0) | 20 | 80 | 0 | 105.2 (605) | 337 | 325 | 0.05 |
| ExpectimaxAgent:2 | originalClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 1715.0 (0) | 295 | 295 | 2.85 |
| ExpectimaxAgent:2 | originalClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 767.0 (0) | 263 | 263 | 3.18 |
| ExpectimaxAgent:2 | originalClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | 455.8 (520) | 176 | 176 | 0.10 |
| ExpectimaxAgent:2 | originalClassic | RandomGhost | 20 (15) | 0 | 100 | 0 | 23.0 (199) | 419 | 419 | 0.07 |
| ExpectimaxAgent:2 | demo_corridor_trap | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -438.0 (0) | 8 | 8 | 0.55 |
| ExpectimaxAgent:2 | demo_corridor_trap | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -438.0 (0) | 8 | 8 | 0.48 |
| ExpectimaxAgent:2 | demo_corridor_trap | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -438.2 (0) | 8 | 8 | 0.08 |
| ExpectimaxAgent:2 | demo_corridor_trap | RandomGhost | 20 (0) | 0 | 100 | 0 | -429.9 (19) | 14 | 14 | 0.03 |
| ExpectimaxAgent:2 | demo_pincer_arena | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -476.0 (0) | 6 | 6 | 0.65 |
| ExpectimaxAgent:2 | demo_pincer_arena | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 620.0 (0) | 130 | 130 | 0.79 |
| ExpectimaxAgent:2 | demo_pincer_arena | DirectionalGhost | 20 (0) | 5 | 95 | 0 | 10.1 (665) | 50 | 45 | 0.08 |
| ExpectimaxAgent:2 | demo_pincer_arena | RandomGhost | 20 (0) | 35 | 65 | 0 | 829.1 (717) | 172 | 148 | 0.04 |
| ExpectimaxAgent:2 | demo_capsule_corner | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -284.0 (0) | 24 | 24 | 0.44 |
| ExpectimaxAgent:2 | demo_capsule_corner | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 0 | 20 | -620.0 (0) | 1501 | - | 0.36 |
| ExpectimaxAgent:2 | demo_capsule_corner | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -225.3 (151) | 32 | 32 | 0.08 |
| ExpectimaxAgent:2 | demo_capsule_corner | RandomGhost | 20 (0) | 10 | 90 | 0 | -7.4 (363) | 211 | 189 | 0.05 |
| ExpectimaxAgent:2 | demo_long_loop | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 124.0 (0) | 96 | 96 | 0.30 |
| ExpectimaxAgent:2 | demo_long_loop | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -211.0 (0) | 41 | 41 | 0.31 |
| ExpectimaxAgent:2 | demo_long_loop | DirectionalGhost | 20 (0) | 50 | 50 | 0 | 564.5 (561) | 99 | 82 | 0.10 |
| ExpectimaxAgent:2 | demo_long_loop | RandomGhost | 20 (0) | 70 | 30 | 0 | 715.5 (565) | 164 | 183 | 0.04 |
| ExpectimaxAgent:2 | demo_dead_end_comb | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -403.0 (0) | 13 | 13 | 0.79 |
| ExpectimaxAgent:2 | demo_dead_end_comb | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -403.0 (0) | 13 | 13 | 0.50 |
| ExpectimaxAgent:2 | demo_dead_end_comb | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -379.5 (25) | 18 | 18 | 0.10 |
| ExpectimaxAgent:2 | demo_dead_end_comb | RandomGhost | 20 (0) | 0 | 100 | 0 | -502.4 (216) | 198 | 198 | 0.06 |
| AlphaBetaAgent:2 | mediumClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 506.0 (0) | 94 | 94 | 0.56 |
| AlphaBetaAgent:2 | mediumClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 500.0 (0) | 100 | 100 | 0.42 |
| AlphaBetaAgent:2 | mediumClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | 391.8 (161) | 146 | 146 | 0.06 |
| AlphaBetaAgent:2 | mediumClassic | RandomGhost | 20 (0) | 5 | 85 | 2 | -179.3 (436) | 761 | 685 | 0.05 |
| AlphaBetaAgent:2 | smallClassic | CoordinatedGhostTeam | 20 (0) | 100 | 0 | 0 | 949.0 (0) | 101 | - | 0.37 |
| AlphaBetaAgent:2 | smallClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -384.0 (0) | 24 | 24 | 0.45 |
| AlphaBetaAgent:2 | smallClassic | DirectionalGhost | 20 (0) | 10 | 90 | 0 | -26.2 (499) | 72 | 64 | 0.08 |
| AlphaBetaAgent:2 | smallClassic | RandomGhost | 20 (0) | 15 | 85 | 0 | -107.4 (460) | 196 | 185 | 0.04 |
| AlphaBetaAgent:2 | originalClassic | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 1715.0 (0) | 295 | 295 | 2.49 |
| AlphaBetaAgent:2 | originalClassic | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | 767.0 (0) | 263 | 263 | 2.76 |
| AlphaBetaAgent:2 | originalClassic | DirectionalGhost | 20 (0) | 0 | 100 | 0 | 458.1 (522) | 177 | 177 | 0.07 |
| AlphaBetaAgent:2 | originalClassic | RandomGhost | 20 (11) | 0 | 100 | 0 | 112.1 (426) | 557 | 557 | 0.05 |
| AlphaBetaAgent:2 | demo_corridor_trap | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -438.0 (0) | 8 | 8 | 0.82 |
| AlphaBetaAgent:2 | demo_corridor_trap | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -438.0 (0) | 8 | 8 | 0.64 |
| AlphaBetaAgent:2 | demo_corridor_trap | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -438.2 (0) | 8 | 8 | 0.07 |
| AlphaBetaAgent:2 | demo_corridor_trap | RandomGhost | 20 (0) | 0 | 100 | 0 | -429.9 (19) | 14 | 14 | 0.04 |
| AlphaBetaAgent:2 | demo_pincer_arena | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -465.0 (0) | 5 | 5 | 0.69 |
| AlphaBetaAgent:2 | demo_pincer_arena | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -465.0 (0) | 5 | 5 | 0.83 |
| AlphaBetaAgent:2 | demo_pincer_arena | DirectionalGhost | 20 (0) | 5 | 95 | 0 | 13.8 (661) | 50 | 45 | 0.05 |
| AlphaBetaAgent:2 | demo_pincer_arena | RandomGhost | 20 (0) | 30 | 70 | 0 | 745.8 (708) | 162 | 139 | 0.04 |
| AlphaBetaAgent:2 | demo_capsule_corner | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -284.0 (0) | 24 | 24 | 0.39 |
| AlphaBetaAgent:2 | demo_capsule_corner | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 0 | 20 | -620.0 (0) | 1501 | - | 0.36 |
| AlphaBetaAgent:2 | demo_capsule_corner | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -225.3 (151) | 32 | 32 | 0.06 |
| AlphaBetaAgent:2 | demo_capsule_corner | RandomGhost | 20 (0) | 10 | 90 | 0 | -7.3 (363) | 211 | 189 | 0.05 |
| AlphaBetaAgent:2 | demo_long_loop | CoordinatedGhostTeam | 20 (0) | 100 | 0 | 0 | 1132.0 (0) | 108 | - | 0.31 |
| AlphaBetaAgent:2 | demo_long_loop | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -201.0 (0) | 41 | 41 | 0.35 |
| AlphaBetaAgent:2 | demo_long_loop | DirectionalGhost | 20 (0) | 50 | 50 | 0 | 564.3 (560) | 99 | 82 | 0.07 |
| AlphaBetaAgent:2 | demo_long_loop | RandomGhost | 20 (0) | 70 | 30 | 0 | 717.4 (564) | 164 | 183 | 0.05 |
| AlphaBetaAgent:2 | demo_dead_end_comb | CoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -403.0 (0) | 13 | 13 | 0.76 |
| AlphaBetaAgent:2 | demo_dead_end_comb | EnhancedCoordinatedGhostTeam | 20 (0) | 0 | 100 | 0 | -403.0 (0) | 13 | 13 | 0.63 |
| AlphaBetaAgent:2 | demo_dead_end_comb | DirectionalGhost | 20 (0) | 0 | 100 | 0 | -379.5 (25) | 18 | 18 | 0.09 |
| AlphaBetaAgent:2 | demo_dead_end_comb | RandomGhost | 20 (0) | 0 | 100 | 0 | -502.4 (216) | 198 | 198 | 0.04 |

