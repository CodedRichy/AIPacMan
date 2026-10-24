# Wiring `multiagent/ghostConfig.py` into the ghost files

`ghostConfig.GhostConfig` is **not wired in yet**. Defaults equal today's hard-coded values, so a
correct wiring with default config must leave behaviour (and benchmark numbers for a given seed)
unchanged. Line numbers are from this branch before the concurrent ghost-file edits merge; re-grep
after merging.

Suggested plumbing: give `GhostCoordinator.__init__` / `EnhancedGhostCoordinator.__init__` a
`config=None` argument (`self.cfg = config or ghostConfig.load_config()`), and have the team
classes pass one in when they create the singleton.

| Constant (current value) | File:line | Config field |
|---|---|---|
| `predictPacmanPosition(steps=4)` (base) | coordinatedGhostAgents.py:42 | `base_prediction_horizon` |
| choke tile: `exits <= 2` | coordinatedGhostAgents.py:70 | `choke_max_exits` |
| choke score `(3 - exits) * 10 / (dist + 1)` (the `10`) | coordinatedGhostAgents.py:72 | `choke_weight` |
| `HISTORY_LEN = 6` | enhancedGhostAgents.py:81 | `history_len` |
| `predictPacmanPosition(steps=5)` (enhanced) | enhancedGhostAgents.py:116 | `prediction_horizon` |
| pincer look-ahead `range(5)` | enhancedGhostAgents.py:244 | `pincer_distance` |
| `ghostsAreScared = any(gs.scaredTimer > 0 ...)` (the `0`) | enhancedGhostAgents.py:335 | `scared_flee_threshold` (`> threshold`) |
| EARLY_SPREAD: `foodRatio > 0.50` | enhancedGhostAgents.py:374 | `early_food_ratio` |
| `currentFood > 5` (two places) | enhancedGhostAgents.py:374, 376 | `endgame_food_count` |
| MID_PRESSURE: `foodRatio > 0.20` | enhancedGhostAgents.py:376 | `endgame_food_ratio` |
| capsule threat `distToPacman <= 4` | enhancedGhostAgents.py:445 | `capsule_threat_distance` |
| trap test `openExits <= 2` | enhancedGhostAgents.py:482 | `trap_max_exits` |
| flee corner inset `width - 3`, `2`, `height - 3` | enhancedGhostAgents.py:526-532 | `flee_corner_inset` (corner = `inset` from edge; `width-1-inset`) |
| flee diagonal search `range(0, 4)` | enhancedGhostAgents.py:537 | `flee_search_span` |
| reservation reset on state-hash change | enhancedGhostAgents.py:586 | `use_reservation` (skip reserve/check calls when False; see note) |
| reservation check in `getAction` | enhancedGhostAgents.py:763 | `use_reservation` |
| `priority_map = {chaser:1, interceptor:2, blocker:3, sweeper:4}` | enhancedGhostAgents.py:696 | `role_priority` |
| `priority_map.get(role, 4)` | enhancedGhostAgents.py:697 | `default_priority` |
| whole tactical-state evaluation `_evaluateTacticalState()` call | enhancedGhostAgents.py:341 (`_updatePerception`) | `use_tactical_states` (False -> state stays COORDINATED_HUNT) |
| macro strategy `_evaluateMacroStrategy()` call | enhancedGhostAgents.py:338 | `use_strategy_switching` (False -> EARLY_SPREAD) |
| SCATTER branch in `assignRoles` | enhancedGhostAgents.py:600 | `use_scared_scatter` |
| interceptor pincer override in `assignRoles` | enhancedGhostAgents.py:621 | `use_pincer` |

## Fields with no current constant

* `state_dwell_ticks` is a **new** knob. Today the state is re-evaluated every call with no
  hysteresis, equivalent to `0`. Implementation sketch: store `(state, tick_entered)`; only accept a
  new state if `tick - tick_entered >= state_dwell_ticks`, except that SCATTER always preempts.
  "Tick" must be counted per game tick (positions change after each ghost, so count `getAction`
  calls modulo number of ghosts, or use `state.data.score` deltas), not per call.
* `default_priority`, `trap_max_exits`, `flee_corner_inset`, `flee_search_span` are split out for
  completeness; they are literals today.

## Caveats found while mapping

* `use_reservation=False` is the cheap A/B for the reservation feature, but measurements show it is
  already a no-op (`isTileReservedByHigherPriority` returned True 0/4302 times) because the table is
  cleared whenever any ghost has moved. Wire the flag, then fix the reset key (e.g. key on the
  *tick number*, not on positions) if reservation is meant to work.
* TRAP_AMBUSH has no behaviour to configure; `trap_max_exits` only changes how often the (inert)
  state is reported. Do not read tuning results for it as meaningful until it does something.
* The hard-coded `('blocker', 'sweeper', 'interceptor')` capsule-guard candidate list
  (enhancedGhostAgents.py, DEFEND_CAPSULE branch of `assignRoles`) is not in the config; add a
  `capsule_guard_roles` list if you want it tunable.
* Env override format: `GHOST_<FIELD_UPPER>=value`, `GHOST_CONFIG=/path/cfg.json`; booleans accept
  `1/0/true/false/yes/no/on/off`; `role_priority` takes a JSON object.
