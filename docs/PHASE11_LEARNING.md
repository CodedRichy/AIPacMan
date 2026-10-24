# Phase 11: ghosts that learn your habits

Status: planned. Start after Phases 7 (bake-off), 9 (arcade shell) and 10 (ghost messaging) are merged,
because this edits ghost target prediction.

## Goal

Today nothing learns: ghosts are fixed heuristics and recorded plays are only replayed.
Phase 11 adds one small, honest kind of learning: an opponent model of the human player.
The ghosts remember which way you turn at each junction and aim their interception and
pincer targets at where you actually go.

## Design

- **Model.** Per layout, per junction tile, per incoming direction: counts of the outgoing
  direction taken. Decay old games (x0.9 per game) so habits can change. Laplace
  smoothing. If a junction has fewer than 3 observations, fall back to the current
  velocity extrapolation.
- **Prediction.** Roll Pac-Man forward k steps, taking the most likely turn at each
  junction. Feeds `predictPacmanPosition` and the pincer target. No other ghost logic changes.
- **Data sources.** Live play (the Phase 9 session layer), recorded games (`recorded-game*`
  pickles, via `moveHistory`), and dashboard traces.
- **Storage.** One JSON file per player profile, outside the repo
  (`~/.local/share/aipacman/profiles/<name>.json`), versioned, written atomically.
  Nothing is uploaded anywhere.
- **Switch.** `LEARN FROM ME` toggle in the play menu, default OFF. With it off, behaviour
  must be byte-identical to today (same benchmark numbers, same seeds).
- **Visibility.** HUD readout of prediction accuracy over your plays, plus a heatmap layer
  showing the learned turn preferences (a Phase 9 layer toggle).

## How we will know it works

Replaying human moves cannot measure kill time, because recorded Pac-Man actions do not
react to the ghosts. So the test has two parts:

1. **Prediction accuracy** (human data): train on games 1..k, measure next-junction top-1
   accuracy on game k+1. Baseline is velocity extrapolation.
2. **Kill time** (controlled): a scripted "habit" Pac-Man with fixed turn preferences plus
   noise, run through the benchmark with learning on vs off. Report 95% confidence intervals.

Success criteria:

- Top-1 accuracy at least 15 points above baseline after 10 games on the same layout.
- Kill time against the habit agent drops with a confidence interval that excludes zero.
- Added cost under 0.5 ms per ghost decision.
- Learning OFF reproduces the current benchmark exactly.

## Failure vectors to test before trusting it

- **Cold start:** the first games must be no worse than today (fallback covers this).
- **Overfitting to one habit:** a player who changes style, or a second player on the same
  profile. Decay handles drift; profiles are per name.
- **Exploit loop:** if the human learns that ghosts expect their habit and breaks it, the
  model must recover within a few games (test with a habit agent that flips its preference).
- **Memory and file growth:** counts are keyed by junction tiles only; cap the profile size.

## Files (planned)

- `multiagent/playerModel.py` (new): the model, load/save, accuracy tracking.
- `multiagent/coordinatedGhostAgents.py`: small hook in prediction (only touched here).
- `benchmarks/habit_pacman.py` (new): scripted habit agent for the controlled test.
- `dashboard/` (Phase 9 files): toggle, accuracy readout, heatmap layer.
