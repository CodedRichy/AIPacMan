# Phase 7: Ghost algorithm bake-off

Goal: find out whether territory control (Voronoi) or a short joint-move search beats the current
Manhattan-role ghost teams. Metric: Pac-Man's average score (lower is better for the ghosts).

## Teams

| Name | Class | Idea |
|---|---|---|
| A | `VoronoiGhostTeam` | All-pairs maze-distance table (cached per layout). Ghosts own tiles they reach strictly before Pac-Man. One target per Pac-Man exit on the ghost/Pac-Man frontier, assigned by brute-force minimum total maze distance with a stickiness penalty. Scared ghosts flee until the timer is <= 3. |
| B | `VoronoiExpectimaxGhostTeam` | A, plus a depth-2 joint-move search over the nearest <= 3 ghosts when one is within 4 maze tiles. Pac-Man modelled as 50/50 pessimistic and greedy-to-food. `...GreedyTeam` / `...PessimisticTeam` are the single-model variants. |
| C | `MazeDistanceChaseTeam` | Every ghost steps along the shortest maze path to Pac-Man, small tie-break spread. |
| controls | `CoordinatedGhostTeam`, `EnhancedCoordinatedGhostTeam` (merged, fixed versions), `DirectionalGhost`, `RandomGhost` | |

All teams plan once per tick (ghost 1 plans, the others read the cached plan), return legal non-STOP actions only.

## Method

- Harness: `multiagent/bakeoff.py`. 40 games per cell, seeds 0-39, headless, <= 4 worker processes, 2 GiB address-space cap per worker.
- Pac-Man is wrapped with 10% uniformly random moves. Without noise, Expectimax/AlphaBeta/Minimax and the ghost teams are all deterministic and every seed replays one identical game (CI of 0 from n=1). The same wrapper is applied to every cell. This makes Pac-Man weaker than the raw agents, so absolute scores are not comparable with plain `pacman.py` runs.
- Games are cut off at 1000 rounds (counted as not-won, reported in the full tables).
- 95% CI = 1.96 * sd / sqrt(n). Pairwise p-values are Welch two-sided, normal approximation (full tables in `bakeoff_dev.md`, `bakeoff_holdout.md`). No multiple-comparison correction: with ~100 comparisons per grid a few p < 0.05 are expected by chance.
- Development used only seeds 1000+ and only mediumClassic, smallClassic, contestClassic with GreedyAgent/ExpectimaxAgent. The reported seeds 0-39 were not used for tuning.
- Dev grid: layouts mediumClassic, smallClassic, contestClassic, openClassic, originalClassic x GreedyAgent, ExpectimaxAgent(d2), AlphaBetaAgent(d2). Layouts openClassic and originalClassic were added late for dev too, after I saw that the small layouts saturate.
- Holdout, run once at the end: layout `trickyClassic` (4 ghosts) and Pac-Man `MinimaxAgent`(d2).

Pac-Man almost never wins (0-2% in every cell), so win rate does not discriminate; score and game length do.
Full per-cell win rate, rounds, cutoffs and ms/round are in `docs/bakeoff_dev.md` and `docs/bakeoff_holdout.md` (raw games in the `.json` files).

## Results: mean Pac-Man score +- 95% CI (bold = lowest in row)


**Dev grid (seeds 0-39)**

| Layout / Pac-Man | A Voronoi | B Vor+Expectimax | Coordinated | Enhanced | Directional | C MazeChase | Random |
|---|---|---|---|---|---|---|---|
| mediumClassic / ExpectimaxAgent | -145 ± 83 | -142 ± 81 | **-201 ± 71** | -194 ± 70 | 36 ± 75 | -93 ± 87 | 61 ± 78 |
| mediumClassic / AlphaBetaAgent | -145 ± 83 | -142 ± 81 | **-213 ± 70** | -206 ± 69 | 36 ± 75 | -92 ± 87 | 12 ± 77 |
| smallClassic / ExpectimaxAgent | **-354 ± 30** | -318 ± 62 | -342 ± 34 | -193 ± 66 | -245 ± 57 | -127 ± 67 | -155 ± 87 |
| smallClassic / AlphaBetaAgent | **-359 ± 24** | -355 ± 25 | -342 ± 34 | -215 ± 65 | -293 ± 50 | -209 ± 46 | -219 ± 76 |
| contestClassic / ExpectimaxAgent | -222 ± 52 | **-358 ± 58** | -354 ± 49 | -335 ± 56 | -117 ± 144 | 71 ± 126 | 35 ± 151 |
| contestClassic / AlphaBetaAgent | -237 ± 36 | **-372 ± 39** | -352 ± 49 | -365 ± 45 | -192 ± 101 | 66 ± 124 | 20 ± 144 |
| openClassic / ExpectimaxAgent | -318 ± 22 | -304 ± 26 | -318 ± 22 | -318 ± 22 | -251 ± 42 | -251 ± 40 | **-726 ± 62** |
| openClassic / AlphaBetaAgent | -316 ± 23 | -304 ± 26 | -316 ± 23 | -316 ± 23 | -258 ± 40 | -258 ± 39 | **-730 ± 61** |
| originalClassic / ExpectimaxAgent | **-310 ± 30** | -310 ± 30 | 91 ± 125 | -37 ± 91 | 2 ± 78 | 150 ± 88 | 52 ± 90 |
| originalClassic / AlphaBetaAgent | **-308 ± 30** | -308 ± 30 | 72 ± 121 | -37 ± 92 | 5 ± 77 | 136 ± 85 | 52 ± 90 |
| mediumClassic / GreedyAgent | -326 ± 50 | -316 ± 59 | -329 ± 46 | **-335 ± 43** | -254 ± 62 | -226 ± 75 | -96 ± 67 |
| smallClassic / GreedyAgent | **-393 ± 13** | -393 ± 14 | -380 ± 22 | -366 ± 27 | -382 ± 24 | -363 ± 23 | -257 ± 51 |
| contestClassic / GreedyAgent | -237 ± 80 | -215 ± 100 | **-400 ± 21** | -393 ± 34 | -297 ± 66 | -84 ± 145 | -193 ± 111 |
| openClassic / GreedyAgent | -324 ± 24 | -328 ± 24 | **-331 ± 23** | -331 ± 23 | -285 ± 30 | -298 ± 36 | -45 ± 128 |
| originalClassic / GreedyAgent | **-252 ± 62** | -243 ± 66 | -185 ± 106 | -186 ± 107 | -88 ± 102 | -110 ± 105 | 56 ± 110 |

**Holdout grid (seeds 0-39)**

| Layout / Pac-Man | A Voronoi | B Vor+Expectimax | Coordinated | Enhanced | Directional | C MazeChase | Random |
|---|---|---|---|---|---|---|---|
| trickyClassic / MinimaxAgent | **-262 ± 65** | -239 ± 110 | -257 ± 64 | -252 ± 64 | -23 ± 164 | -158 ± 99 | 266 ± 150 |
| mediumClassic / MinimaxAgent | -145 ± 83 | -142 ± 81 | **-213 ± 70** | -206 ± 69 | 36 ± 75 | -92 ± 87 | 12 ± 77 |
| smallClassic / MinimaxAgent | **-359 ± 24** | -355 ± 25 | -342 ± 34 | -219 ± 66 | -293 ± 50 | -209 ± 46 | -219 ± 76 |
| contestClassic / MinimaxAgent | -237 ± 36 | **-372 ± 39** | -352 ± 49 | -365 ± 45 | -192 ± 101 | 66 ± 124 | 20 ± 144 |
| openClassic / MinimaxAgent | -316 ± 23 | -304 ± 26 | -316 ± 23 | -316 ± 23 | -258 ± 40 | -258 ± 39 | **-730 ± 61** |
| originalClassic / MinimaxAgent | **-308 ± 30** | -308 ± 30 | 72 ± 121 | -37 ± 92 | 5 ± 77 | 136 ± 85 | 52 ± 90 |
| trickyClassic / GreedyAgent | -394 ± 31 | **-420 ± 6** | -290 ± 64 | -307 ± 87 | -295 ± 68 | -276 ± 84 | -15 ± 120 |
| trickyClassic / ExpectimaxAgent | **-263 ± 65** | -240 ± 110 | -237 ± 79 | -238 ± 73 | -95 ± 154 | -158 ± 99 | 304 ± 187 |
| trickyClassic / AlphaBetaAgent | **-262 ± 65** | -239 ± 110 | -257 ± 64 | -252 ± 64 | -23 ± 164 | -158 ± 99 | 266 ± 150 |

`openClassic` rows: RandomGhost "wins" the row (-726) only because search-based Pac-Man then stalls to the 1000-round cutoff and bleeds time penalty (22 of 40 games cut off, 837 rounds on average). A low score there is not a good ghost. Read the rounds column in `bakeoff_dev.md`.

## What is statistically meaningful

CI non-overlap or Welch p < 0.01, n = 40 per cell:

- A beats every control on `originalClassic` (4 ghosts, large) against Expectimax/AlphaBeta/Minimax: -310 +- 30 vs Enhanced -37 +- 91 and Coordinated +91 +- 125. The same holds in the holdout Minimax column (-308 vs -37 / +72). This is the one large, clear gap in the data.
- A beats Enhanced on `smallClassic` vs Expectimax/AlphaBeta (-354 vs -193, -359 vs -215). A vs Coordinated there is a tie.
- A is clearly worse than Coordinated/Enhanced on `contestClassic` (3 ghosts): -237 +- 36 vs -352 +- 49 (AlphaBeta), -237 vs -400 (Greedy).
- Everywhere else (mediumClassic, openClassic vs search agents, trickyClassic holdout) A, Coordinated and Enhanced are statistically tied. mediumClassic leans to Coordinated (-213 +- 70 vs -145 +- 83) but the intervals overlap.
- A, B, Coordinated and Enhanced are all far better than Directional, MazeChase and Random in almost every cell. MazeChase (C) is the weakest "smart" team: simple shortest-path chasing, no coordination, loses to every coordinated team; on originalClassic it is the worst (+137 to +150).
- B vs A: no significant difference in any dev cell. B is better on contestClassic (-372 vs -237, p < 0.001) and worse on openClassic/smallClassic by a small, non-significant margin. B's search overrode A's move in roughly 1 call in 25-50 (checked on 12 sample games). The Pac-Man model choice (greedy / pessimistic / mix) changed nothing measurable.

## Winner

There is no single winner. By pooled dev score (equal weight per cell, not a tested quantity): B -294, A -284, Coordinated -260, Enhanced -256. Holdout pooled: B -291, A -283, Coordinated -244, Enhanced -244. The pooled ordering is driven by `originalClassic` and `smallClassic`; on `contestClassic` it reverses. On the genuinely unseen `trickyClassic` layout A is tied with Coordinated/Enhanced against the search agents (-263 vs -237/-238 vs Expectimax, CI ~ +-70) and better only against the Greedy agent (-394/-420 vs -290/-307).

## Capsule problem

No team lets any Pac-Man agent win more than 2% of games, and with the 10% noise every Pac-Man dies within 11-80 rounds, which is mostly before it reaches a capsule, so this benchmark barely exercises the capsule problem. Where the known weak spot does show (Expectimax Pac-Man on `originalClassic`, positive scores: Coordinated +91, MazeChase +150, Directional +2) A scores -310 +- 30. A has no capsule logic; I tried a "guard threatened capsules" bonus in the assignment during development and it made things worse (contestClassic/Expectimax, seeds 1000+: -272 to -81), so it was removed. I did not establish why A does better on that layout (shorter games from earlier territory-based interception is the likely, untested explanation). Treat "A handles capsules better" as an untested hypothesis supported by one layout.

## Cost

Ghost-team time per round, wall clock inside `getAction`, 4 parallel workers (so slightly inflated): A 0.2-0.8 ms on the small layouts, 1-2.5 ms on `originalClassic`; B 0.3-0.9 ms, up to ~2.1 ms on `originalClassic`; Coordinated 0.05-0.3 ms (0.7 ms `originalClassic`); Enhanced 0.1-0.5 ms. B stays far below the 20 ms budget. Peak RSS of a worker playing `originalClassic` with A or B: about 23 MB (all-pairs table cached once per layout in the process; ~400 cells -> ~160k entries). The machine OOMs earlier today were not from the ghost teams: they came from search Pac-Man agents retaining every generated GameState (fixed on main).

## Honest limits

- The 10% Pac-Man noise is my choice. A different noise level, or none, can change the ranking; I did not sweep it.
- Pac-Man agents are all depth-2 search or greedy with the default score evaluation. Nothing smarter (learned agents, depth >= 3, ghost-aware evaluation) and no human player.
- `MinimaxAgent` returned exactly the same moves as `AlphaBetaAgent` (identical scores in every shared cell), so the held-out Pac-Man agent is not independent of a dev agent. The only truly unseen conditions are the `trickyClassic` layout (4 agents) and Minimax's duplication of AlphaBeta. Honest holdout count: one new layout.
- Dev games are short (10-70 rounds). All teams win nearly always; the data compares how fast, not whether. Layouts where Pac-Man can survive long (the cutoff case) are barely covered.
- Voronoi's frontier-blocking is slower than direct rushing at close range, which is probably why it loses on `contestClassic`, where ghosts start next to Pac-Man. Variants I tried and dropped on dev seeds 1000+: nearest-ghost-chases-directly (worse), ties-go-to-ghost territory (no gain), capsule guard (worse). No parameter sweep beyond that.
- Dev scores were produced before main's GameState-leak fix; that changes memory and speed only, not game outcomes (the fix does not touch game rules). Holdout was run after it.
- Only the 2-4 ghost classic layouts, no scared-ghost-heavy layouts such as `powerClassic`/`capsuleClassic`, no `-k` ghost-count variations, no arcade-mode rules, no comparison with `ChatterGhostTeam` or other later teams.
- Per-round ms is measured under 4-way parallel load; do not quote it as single-core latency.

## Recommendation

Do not replace the project's default with the Voronoi team on this evidence. Keep `CoordinatedGhostTeam` (cheapest, tied-best on 4 of 5 dev layouts, best on contestClassic and mediumClassic) as the default ghost team. Ship `VoronoiGhostTeam` as an opt-in team for large, 4-ghost layouts, where it is the only team with a clear, replicated advantage (originalClassic dev and holdout, roughly 300 points). Do not adopt `VoronoiExpectimaxGhostTeam`: the extra search adds no significant gain over A. Do not adopt `MazeDistanceChaseTeam`: coordination clearly matters (Coordinated/Voronoi beat it in most cells). The most useful follow-up is a capsule-aware, survival-heavy benchmark (no Pac-Man noise, `powerClassic`, `capsuleClassic`) before deciding on any default change.

## Reproduce

```
cd multiagent
../tools/capped -m 4G -- python3 bakeoff.py --phase dev --games 40 --jobs 4 --out ../docs/bakeoff_dev.json > ../docs/bakeoff_dev.md
../tools/capped -m 4G -- python3 bakeoff.py --phase holdout --games 40 --jobs 4 --out ../docs/bakeoff_holdout.json > ../docs/bakeoff_holdout.md
python3 bakeoff_table.py ../docs/bakeoff_dev.json "Dev grid"
python3 pacman.py -p GreedyAgent -g VoronoiGhostTeam -l mediumClassic -n 20 -q -f
```
Dev takes ~35 min at 4 jobs (run it per Pac-Man agent with `--agents` if your tool has a command time limit; `--merge a.json,b.json` re-reports saved runs).
The shipped dev and holdout results were run with the 7-team list (without the two single-model B variants for holdout; dev includes them).
