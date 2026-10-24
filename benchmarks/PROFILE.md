# Ghost profiling

Command: `python3 benchmarks/profile_ghosts.py --games 5 --seed 1` (GreedyAgent on mediumClassic, cProfile,
sorted by own time). Profiler overhead inflates every number, and the harness itself (layout parsing in
`play_game`, `GameState.__hash__`, `asList`) shows up because GreedyAgent evaluates all successors.
Read the "Ghost-code" tables for the ghost-owned cost.

Takeaways
* Ghost decision cost is small: about 0.2 ms per decision unprofiled for both coordinated teams (see
  `BASELINE.md`), versus 0.02-0.03 ms for the course ghosts. At 4 ghosts that is under 1 ms per tick.
  Nothing here blocks real-time play.
* CoordinatedGhostTeam: `getAction` own time dominates (its BFS runs inside `getAction`, 274 calls).
* EnhancedCoordinatedGhostTeam: `_bfsFirstAction` is the top ghost hotspot (0.24 s cumulative of 0.38 s
  in `getAction`), then `assignRoles` (0.11 s, re-run once per ghost per tick, 4x redundant) and
  `_findDenseFoodCluster` (called only in MID_PRESSURE, 116 calls, 0.03 s).
* The cheapest optimizations, if ever needed: compute `assignRoles` once per tick instead of once per
  ghost, and replace per-ghost BFS with one distance map from each target. Neither is worth doing
  before the features are effective.

Raw output (single run, numbers vary a little between runs):


### CoordinatedGhostTeam  (GreedyAgent vs mediumClassic, seed 1, 5 game(s), 138 Pac-Man moves)
total profiled time 0.961s; mean ghost decision 1.167 ms (incl. profiler overhead)

| tottime s | % | calls | function |
|---|---|---|---|
| 0.1790 | 18.6 | 274 | `coordinatedGhostAgents.py:93(getAction)` |
| 0.0682 | 7.1 | 245051 | `game.py:193(__getitem__)` |
| 0.0672 | 7.0 | 3089 | `game.py:181(__init__)` |
| 0.0628 | 6.5 | 422 | `game.py:237(asList)` |
| 0.0585 | 6.1 | 92840 | `layout.py:123(processLayoutChar)` |
| 0.0549 | 5.7 | 1456 | `game.py:210(__hash__)` |
| 0.0530 | 5.5 | 422 | `layout.py:102(processLayoutText)` |
| 0.0374 | 3.9 | 65520 | `~:0(<built-in method builtins.hash>)` |
| 0.0270 | 2.8 | 53322 | `game.py:347(directionToVector)` |
| 0.0259 | 2.7 | 55970 | `~:0(<method 'append' of 'list' objects>)` |
| 0.0165 | 1.7 | 8736 | `game.py:103(__hash__)` |
| 0.0165 | 1.7 | 2236 | `game.py:352(getPossibleActions)` |

Ghost-code functions by cumulative time:

| cumtime s | calls | function |
|---|---|---|
| 0.3230 | 274 | `coordinatedGhostAgents.py:93(getAction)` |
| 0.0454 | 274 | `coordinatedGhostAgents.py:12(assignRoles)` |
| 0.0372 | 274 | `coordinatedGhostAgents.py:42(predictPacmanPosition)` |
| 0.0029 | 1 | `enhancedGhostAgents.py:1(<module>)` |
| 0.0002 | 548 | `coordinatedGhostAgents.py:22(<lambda>)` |
| 0.0001 | 1 | `ghostAgents.py:1(<module>)` |

### EnhancedCoordinatedGhostTeam  (GreedyAgent vs mediumClassic, seed 1, 5 game(s), 281 Pac-Man moves)
total profiled time 1.424s; mean ghost decision 0.684 ms (incl. profiler overhead)

| tottime s | % | calls | function |
|---|---|---|---|
| 0.1559 | 10.9 | 558 | `enhancedGhostAgents.py:779(_bfsFirstAction)` |
| 0.1282 | 9.0 | 965 | `game.py:237(asList)` |
| 0.1069 | 7.5 | 6104 | `game.py:181(__init__)` |
| 0.1047 | 7.4 | 186780 | `layout.py:123(processLayoutChar)` |
| 0.0987 | 6.9 | 849 | `layout.py:102(processLayoutText)` |
| 0.0949 | 6.7 | 2954 | `game.py:210(__hash__)` |
| 0.0898 | 6.3 | 463105 | `game.py:193(__getitem__)` |
| 0.0671 | 4.7 | 132930 | `~:0(<built-in method builtins.hash>)` |
| 0.0381 | 2.7 | 110422 | `~:0(<method 'append' of 'list' objects>)` |
| 0.0272 | 1.9 | 17724 | `game.py:103(__hash__)` |
| 0.0257 | 1.8 | 17724 | `game.py:152(__hash__)` |
| 0.0249 | 1.7 | 2954 | `game.py:451(__hash__)` |

Ghost-code functions by cumulative time:

| cumtime s | calls | function |
|---|---|---|
| 0.3818 | 558 | `enhancedGhostAgents.py:736(getAction)` |
| 0.2382 | 558 | `enhancedGhostAgents.py:779(_bfsFirstAction)` |
| 0.1118 | 558 | `enhancedGhostAgents.py:549(assignRoles)` |
| 0.0330 | 558 | `enhancedGhostAgents.py:287(_updatePerception)` |
| 0.0291 | 558 | `coordinatedGhostAgents.py:12(assignRoles)` |
| 0.0285 | 116 | `enhancedGhostAgents.py:383(_findDenseFoodCluster)` |

### DirectionalGhost  (GreedyAgent vs mediumClassic, seed 1, 5 game(s), 209 Pac-Man moves)
total profiled time 0.727s; mean ghost decision 0.088 ms (incl. profiler overhead)

| tottime s | % | calls | function |
|---|---|---|---|
| 0.0699 | 9.6 | 637 | `game.py:237(asList)` |
| 0.0668 | 9.2 | 2228 | `game.py:210(__hash__)` |
| 0.0660 | 9.1 | 4583 | `game.py:181(__init__)` |
| 0.0619 | 8.5 | 140140 | `layout.py:123(processLayoutChar)` |
| 0.0563 | 7.7 | 637 | `layout.py:102(processLayoutText)` |
| 0.0543 | 7.5 | 283882 | `game.py:193(__getitem__)` |
| 0.0415 | 5.7 | 100260 | `~:0(<built-in method builtins.hash>)` |
| 0.0252 | 3.5 | 78959 | `~:0(<method 'append' of 'list' objects>)` |
| 0.0178 | 2.5 | 13368 | `game.py:103(__hash__)` |
| 0.0155 | 2.1 | 13368 | `game.py:152(__hash__)` |
| 0.0142 | 2.0 | 1741 | `game.py:352(getPossibleActions)` |
| 0.0139 | 1.9 | 2228 | `game.py:451(__hash__)` |

Ghost-code functions by cumulative time:

| cumtime s | calls | function |
|---|---|---|
| 0.0412 | 418 | `ghostAgents.py:27(getAction)` |
| 0.0359 | 418 | `ghostAgents.py:58(getDistribution)` |
| 0.0000 | 20 | `ghostAgents.py:53(__init__)` |

### RandomGhost  (GreedyAgent vs mediumClassic, seed 1, 5 game(s), 723 Pac-Man moves)
total profiled time 2.291s; mean ghost decision 0.057 ms (incl. profiler overhead)

| tottime s | % | calls | function |
|---|---|---|---|
| 0.2366 | 10.3 | 7626 | `game.py:210(__hash__)` |
| 0.2309 | 10.1 | 479380 | `layout.py:123(processLayoutChar)` |
| 0.2239 | 9.8 | 2179 | `game.py:237(asList)` |
| 0.2037 | 8.9 | 15355 | `game.py:181(__init__)` |
| 0.1919 | 8.4 | 2179 | `layout.py:102(processLayoutText)` |
| 0.1559 | 6.8 | 970323 | `game.py:193(__getitem__)` |
| 0.1285 | 5.6 | 343170 | `~:0(<built-in method builtins.hash>)` |
| 0.0748 | 3.3 | 269434 | `~:0(<method 'append' of 'list' objects>)` |
| 0.0662 | 2.9 | 45756 | `game.py:103(__hash__)` |
| 0.0493 | 2.2 | 45756 | `game.py:152(__hash__)` |
| 0.0464 | 2.0 | 7626 | `game.py:451(__hash__)` |
| 0.0412 | 1.8 | 2836 | `game.py:221(copy)` |

Ghost-code functions by cumulative time:

| cumtime s | calls | function |
|---|---|---|
| 0.0752 | 1446 | `ghostAgents.py:27(getAction)` |
| 0.0563 | 1446 | `ghostAgents.py:42(getDistribution)` |
| 0.0000 | 20 | `ghostAgents.py:24(__init__)` |
