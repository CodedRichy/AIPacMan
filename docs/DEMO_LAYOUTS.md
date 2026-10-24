# Demo layouts

Six hand-built scenarios in `multiagent/layouts/demo_*.lay`. Each loads with `layout.getLayout`, is
rectangular with a wall border, has one Pac-Man and every dot/ghost reachable (`python3
tests/layout_check.py`), and was played to completion by every ghost team
(`tests/test_integration.py`).

Play one, from `multiagent/`:

```bash
python pacman.py -p GreedyAgent -g EnhancedCoordinatedGhostTeam -l demo_pincer_arena
python pacman.py -p KeyboardAgent -g CoordinatedGhostTeam -l demo_corridor_trap -n 1
```

| Layout | Size | Ghosts | Shape | Intended to show |
|---|---|---|---|---|
| `demo_corridor_trap` | 21x12 | 4 | Long vertical shaft joining two horizontal corridors; ghosts at both ends of both | Choke points and two-sided containment. Pac-Man starts in the shaft; a team that seals both exits wins fast. Tests the blocker's choke-point choice and the TRAP_AMBUSH condition (corridor tiles have 2 exits). |
| `demo_pincer_arena` | 21x12 | 3 | Plus-shaped cross: a long horizontal hall and a vertical hall, capsules in the top corners | The velocity-based pincer: Pac-Man runs along a hall and the interceptor's "ahead" tile is straight down that hall. Also the capsules sit on the far corners so DEFEND_CAPSULE triggers when Pac-Man heads to them. |
| `demo_capsule_corner` | 21x11 | 2 | Winding maze; the only capsule is at the end of a dead-end alcove in the top-right, entrance guarded by a ghost | DEFEND_CAPSULE and scared coordination: a guard should contest the pellet, and if Pac-Man eats it the team should scatter instead of running into him. |
| `demo_open_field` | 23x14 | 4 | Walled box, no inner walls, one capsule | The case where corridor tactics (chokepoints, pincers along halls) give no advantage; shows pure pursuit/spread. Search-based Pac-Man agents are extremely slow here (branching), so the benchmark runs only `GreedyAgent` on it. |
| `demo_long_loop` | 23x12 | 2 | One big ring around a solid block, 2-wide bottom lane, ghosts on opposite sides | Chasing on a cycle: a single chaser can never catch a runner, two ghosts on opposite arcs trivially can. Shows whether the team uses its second ghost to cut off, or just follows. |
| `demo_dead_end_comb` | 21x13 | 2 | Two open lanes joined by many one-tile-wide dead-end spurs | Dead-end trapping and the cost of greedy food eating: Pac-Man gets cornered when it dives into spurs. |

## Honest notes

* These are scenarios, not tuned fairness tests. Measured: `GreedyAgent` dies in 4 moves on
  `demo_corridor_trap` and about 10 moves on `demo_long_loop` and `demo_dead_end_comb` against every
  chasing team, because the ghosts start close and Greedy walks toward them (those layouts do not
  separate the teams). Layouts that do separate them: `demo_capsule_corner` (Greedy survives and wins
  35-45% against the coordinated teams but only 5% against DirectionalGhost) and `demo_open_field`
  (DirectionalGhost beats both coordinated teams). Use a stronger Pac-Man or the keyboard to see more.
* Expectimax and AlphaBeta against `EnhancedCoordinatedGhostTeam` on `demo_capsule_corner` never
  finish: 20 of 20 games hit the 1500-move cap with no win or loss, a standoff worth investigating.
* Because the coordinated teams are deterministic, many matchups give the same outcome for every seed;
  seeds only affect `GreedyAgent` tie-breaking and the random ghosts.
* Results per layout are in the benchmark table in `benchmarks/BASELINE.md`.
